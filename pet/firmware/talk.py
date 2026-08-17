#!/usr/bin/env python3
"""Packet harness for the pet servo console.

Speaks the FlatBuffer wire protocol (pet/pet.fbs): text commands typed here are
encoded into Packets, responses/events are rendered human-readably. Tries the
serial port first, then falls back to the websocket server (ws://bug.local:81)
if the port isn't available. Unless --no-stop is given, always sends a stop
(disable motors) before exiting so a test can't leave a motor running.

Usage:
  ./talk.py [-w SECS] "cmd" ["cmd" ...]     send commands, watch SECS after each
  ./talk.py -w 0.5 "s"                      quick status check
  ./talk.py "o 1 80 200"                    open-loop pulse test
  ./talk.py -w 6 "v 2" "g 1 2" "s"          closed-loop move, watch 6s per cmd
  ./talk.py -w 12 "wifi MySSID mypass"      join wifi (saved to flash on the bot)
  ./talk.py "wifi"                          wifi status
  ./talk.py "help"                          list of board commands

A command of the form 'sleep N' is handled locally (waits N seconds while
still printing whatever the robot sends) rather than sent to the board.
"""
import argparse
import os
import shlex
import struct
import sys
import time

import serial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flatbuffers  # noqa: E402
from petproto import pet_generated as pw  # noqa: E402

DEFAULT_PORT = "/dev/cu.usbmodem2101"
DEFAULT_HOST = "bug.local"
WS_PORT = 81
MAGIC = b"\xbe\xef"
FILE_ID = b"PET1"
# Robot->host frames can exceed the firmware's 512-byte *inbound* cap (the help
# text alone is ~1.1 KB); this only bounds resync sanity on our side.
MAX_PACKET = 4096

_next_id = 0


def next_id():
    global _next_id
    _next_id = (_next_id % 0xFFFFFFFF) + 1  # wraps, never 0
    return _next_id


# --- transports -------------------------------------------------------------
# Both expose whole Packet buffers; framing differs. poll() yields packets as
# they arrive until `seconds` elapses, so output streams like the old console.

class SerialTransport:
    """0xBE 0xEF + u16 LE length framing over the USB CDC port."""

    def __init__(self, ser):
        self.ser = ser
        self.buf = b""

    def send(self, payload):
        self.ser.write(MAGIC + struct.pack("<H", len(payload)) + payload)

    def poll(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            chunk = self.ser.read(4096)  # returns fast: port opened with timeout
            if chunk:
                self.buf += chunk
                yield from self._extract()

    def _extract(self):
        while True:
            i = self.buf.find(MAGIC)
            if i < 0:
                # keep a trailing 0xBE in case its 0xEF is in the next chunk
                self.buf = self.buf[-1:] if self.buf.endswith(MAGIC[:1]) else b""
                return
            self.buf = self.buf[i:]
            if len(self.buf) < 4:
                return
            (length,) = struct.unpack_from("<H", self.buf, 2)
            if length < 12 or length > MAX_PACKET:
                self.buf = self.buf[2:]  # implausible: skip this magic, rescan
                continue
            if len(self.buf) < 4 + length:
                return
            payload = self.buf[4 : 4 + length]
            self.buf = self.buf[4 + length :]
            if payload[4:8] == FILE_ID:
                yield payload
            # else: bytes that happened to look like a frame; keep scanning

    def close(self):
        self.ser.close()


class WsTransport:
    """One Packet per binary websocket message; no extra framing."""

    def __init__(self, ws):
        self.ws = ws

    def send(self, payload):
        self.ws.send(payload)

    def poll(self, seconds):
        end = time.monotonic() + seconds
        while True:
            remain = end - time.monotonic()
            if remain <= 0:
                return
            try:
                msg = self.ws.recv(timeout=remain)
            except TimeoutError:
                return
            if isinstance(msg, bytes) and msg[4:8] == FILE_ID:
                yield msg

    def close(self):
        self.ws.close()


def open_transport(args):
    try:
        ser = serial.Serial(args.port, 115200, timeout=0.05)
        return SerialTransport(ser)
    except serial.SerialException as e:
        print(f"[serial {args.port} unavailable ({e.__class__.__name__}); trying ws://{args.host}:{WS_PORT}]")
    try:
        from websockets.sync.client import connect
        # Resolve IPv4 ourselves: the default unspecified-family lookup stalls
        # ~5s on an AAAA query the robot's mDNS responder never answers.
        import socket
        ip = socket.getaddrinfo(args.host, WS_PORT, socket.AF_INET,
                                socket.SOCK_STREAM)[0][4][0]
        ws = connect(f"ws://{ip}:{WS_PORT}", open_timeout=5)
        return WsTransport(ws)
    except Exception as e:
        print(f"[could not reach robot on serial or ws://{args.host}:{WS_PORT}: {e}]")
        return None


def closed_exceptions():
    from websockets.exceptions import ConnectionClosed
    return (serial.SerialException, ConnectionClosed, OSError)


# --- command encoding -------------------------------------------------------

CHANNELS = {1: pw.Channel.ONE, 2: pw.Channel.TWO}


def finish(b, msg_type, msg, req_id):
    pw.PacketStart(b)
    pw.PacketAddReqId(b, req_id)
    pw.PacketAddMsgType(b, msg_type)
    pw.PacketAddMsg(b, msg)
    b.Finish(pw.PacketEnd(b), file_identifier=FILE_ID)
    return bytes(b.Output())


def number_cmd(cmd, channel, value):
    b = flatbuffers.Builder(64)
    pw.NumberCmdStart(b)
    pw.NumberCmdAddCmd(b, cmd)
    pw.NumberCmdAddChannel(b, channel)
    pw.NumberCmdAddValue(b, value)
    return finish(b, pw.Msg.NumberCmd, pw.NumberCmdEnd(b), next_id())


def simple_action(cmd):
    b = flatbuffers.Builder(64)
    pw.SimpleActionStart(b)
    pw.SimpleActionAddCmd(b, cmd)
    return finish(b, pw.Msg.SimpleAction, pw.SimpleActionEnd(b), next_id())


def encode(cmd_str):
    """Translate one console command into a Packet buffer.

    Raises ValueError for a known command with bad arguments; unknown commands
    encode as HELP so the board answers with usage.
    """
    parts = cmd_str.split()
    op, args = parts[0], parts[1:]

    servo_num_cmds = {"g": pw.NumCmd.GOTO, "r": pw.NumCmd.MOVE_BY}
    global_num_cmds = {"v": pw.NumCmd.MAX_SPEED, "vg": pw.NumCmd.GROUND_SPEED,
                       "va": pw.NumCmd.AIR_SPEED, "pwm": pw.NumCmd.MAX_PWM,
                       "minpwm": pw.NumCmd.MIN_PWM, "kp": pw.NumCmd.KP,
                       "ki": pw.NumCmd.KI, "kd": pw.NumCmd.KD}
    simples = {"stand": pw.SimpleCmd.STAND, "z": pw.SimpleCmd.ZERO,
               "x": pw.SimpleCmd.STOP, "enc": pw.SimpleCmd.ENC_HEALTH,
               "s": pw.SimpleCmd.STATUS, "reset": pw.SimpleCmd.RESET,
               "help": pw.SimpleCmd.HELP}

    if op in servo_num_cmds:
        ch = CHANNELS[int(args[0])]
        return number_cmd(servo_num_cmds[op], ch, float(args[1]))
    if op in global_num_cmds:
        return number_cmd(global_num_cmds[op], pw.Channel.BOTH, float(args[0]))
    if op == "dir":
        return number_cmd(pw.NumCmd.SET_DIR, CHANNELS[int(args[0])], float(args[1]))
    if op in simples:
        return simple_action(simples[op])
    if op == "o":
        b = flatbuffers.Builder(64)
        pw.PulseCmdStart(b)
        pw.PulseCmdAddChannel(b, CHANNELS[int(args[0])])
        pw.PulseCmdAddPwm(b, int(args[1]))
        pw.PulseCmdAddMs(b, int(args[2]))
        return finish(b, pw.Msg.PulseCmd, pw.PulseCmdEnd(b), next_id())
    if op == "cal":
        b = flatbuffers.Builder(64)
        pw.CalibrateStart(b)
        pw.CalibrateAddChannel(b, CHANNELS[int(args[0])] if args else pw.Channel.BOTH)
        return finish(b, pw.Msg.Calibrate, pw.CalibrateEnd(b), next_id())
    if op == "walk":
        # walk <n> [phase_deg]: crank offset between the legs, default 180.
        b = flatbuffers.Builder(64)
        pw.WalkCmdStart(b)
        pw.WalkCmdAddSteps(b, int(args[0]))
        if len(args) > 1:
            pw.WalkCmdAddPhaseDeg(b, float(args[1]))
        return finish(b, pw.Msg.WalkCmd, pw.WalkCmdEnd(b), next_id())
    if op in ("watch", "raw"):
        b = flatbuffers.Builder(64)
        pw.ToggleCmdStart(b)
        pw.ToggleCmdAddWhich(b, pw.Toggle.STATUS_STREAM if op == "watch" else pw.Toggle.RAW_STREAM)
        return finish(b, pw.Msg.ToggleCmd, pw.ToggleCmdEnd(b), next_id())
    if op == "wifi":
        # `wifi` -> status; `wifi <ssid...> <pass>` -> connect. shlex respects
        # quotes; unquoted multi-word SSIDs take everything before the last
        # token (the password).
        toks = shlex.split(cmd_str[len("wifi"):].strip())
        ssid = password = None
        if len(toks) == 1:
            raise ValueError("usage: wifi  |  wifi <ssid> <password>")
        if len(toks) >= 2:
            ssid, password = " ".join(toks[:-1]), toks[-1]
        b = flatbuffers.Builder(128)
        ssid_off = b.CreateString(ssid) if ssid else None
        pass_off = b.CreateString(password) if password else None
        pw.WifiCmdStart(b)
        if ssid_off:
            pw.WifiCmdAddSsid(b, ssid_off)
        if pass_off:
            pw.WifiCmdAddPassword(b, pass_off)
        return finish(b, pw.Msg.WifiCmd, pw.WifiCmdEnd(b), next_id())
    # Unknown command: let the board reply with its help text.
    return simple_action(pw.SimpleCmd.HELP)


# --- response rendering -----------------------------------------------------

def _s(v):
    return v.decode(errors="replace") if isinstance(v, (bytes, bytearray)) else (v or "")


def _union(pkt, cls):
    obj = cls()
    tab = pkt.Msg()
    obj.Init(tab.Bytes, tab.Pos)
    return obj


SERVO_STATE = lambda st: "FAULT" if st.Fault() else ("on" if st.Enabled() else "off")

WALK_PHRASES = {
    pw.WalkPhase.START: "walk: starting, servo{servo} leads",
    pw.WalkPhase.LEADIN: "walk: lead-in servo{servo}",
    pw.WalkPhase.STEPPING: "walk: stepping x{steps}",
    pw.WalkPhase.LEADOUT: "walk: lead-out servo{servo}",
    pw.WalkPhase.DONE: "walk: done ({steps} steps), standing; servo{servo} leads next",
    pw.WalkPhase.ABORTED: "walk: aborted",
}

WIFI_STATES = {pw.WifiState.UNCONFIGURED: "unconfigured", pw.WifiState.CONNECTING: "connecting",
               pw.WifiState.CONNECTED: "connected", pw.WifiState.FAILED: "failed"}


def render(payload):
    pkt = pw.Packet.GetRootAs(payload, 0)
    t = pkt.MsgType()
    if t == pw.Msg.Ack:
        a = _union(pkt, pw.Ack)
        detail = _s(a.Detail())
        print(detail if a.Ok() else f"[error] {detail or 'command failed'}")
    elif t == pw.Msg.Log:
        log = _union(pkt, pw.Log)
        prefix = {pw.LogLevel.WARN: "[warn] ", pw.LogLevel.ERROR: "[error] "}.get(log.Level(), "")
        print(prefix + _s(log.Text()))
    elif t == pw.Msg.Status:
        st = _union(pkt, pw.Status)
        cols = []
        for i in range(st.ServosLength()):
            s = st.Servos(i)
            cols.append(f"{s.Channel()}[{SERVO_STATE(s)}]: pos {s.PositionTurns():.3f} "
                        f"tgt {s.TargetTurns():.3f} vel {s.VelocityTps():.2f} pwm {s.Pwm()}")
        print(" | ".join(cols))
    elif t == pw.Msg.EncoderHealth:
        h = _union(pkt, pw.EncoderHealth)
        for i in range(h.EncodersLength()):
            e = h.Encoders(i)
            if not e.Connected():
                print(f"encoder{e.Channel()}: NOT RESPONDING on I2C")
                continue
            print(f"encoder{e.Channel()}: magnet {'YES' if e.MagnetDetected() else 'NO'}"
                  f"{' (too weak/far)' if e.MagnetTooWeak() else ''}"
                  f"{' (too strong/close)' if e.MagnetTooStrong() else ''}"
                  f"  agc {e.Agc()}  magnitude {e.Magnitude()}  angle {e.AngleDeg():.2f} deg")
    elif t == pw.Msg.PulseResult:
        r = _union(pkt, pw.PulseResult)
        print(f"pulse motor{r.Channel()} pwm {r.Pwm()} for {r.Ms()}ms: "
              f"enc1 delta {r.Enc1DeltaCounts()} counts ({r.Enc1DeltaTurns():.3f} turns), "
              f"enc2 delta {r.Enc2DeltaCounts()} counts ({r.Enc2DeltaTurns():.3f} turns)")
        if r.CrossWired():
            print("  note: the other encoder responded — encoders look CROSS-WIRED")
    elif t == pw.Msg.WalkEvent:
        ev = _union(pkt, pw.WalkEvent)
        phrase = WALK_PHRASES.get(ev.Phase(), "walk: phase {phase}?")
        print(phrase.format(servo=ev.LeadServo(), steps=ev.Steps(), phase=ev.Phase()))
    elif t == pw.Msg.WifiStatus:
        w = _union(pkt, pw.WifiStatus)
        line = f"wifi: {WIFI_STATES.get(w.State(), '?')}"
        if _s(w.Ssid()):
            line += f" ssid={_s(w.Ssid())}"
        if _s(w.Ip()):
            line += f" ip={_s(w.Ip())} ({_s(w.Hostname())}.local) rssi={w.Rssi()}dBm clients={w.WsClients()}"
        print(line)
    else:
        print(f"[unhandled packet type {t}]")
    sys.stdout.flush()


def drain(transport, seconds):
    """Render whatever the robot sends for `seconds`."""
    for payload in transport.poll(seconds):
        render(payload)


# --- main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--port", default=DEFAULT_PORT)
    ap.add_argument("--host", default=DEFAULT_HOST,
                    help=f"websocket fallback host (default {DEFAULT_HOST})")
    ap.add_argument("-w", "--watch", type=float, default=2.0,
                    help="seconds of output to watch after each command (default 2)")
    ap.add_argument("--no-stop", action="store_true",
                    help="don't send stop (disable motors) on exit")
    ap.add_argument("cmds", nargs="+")
    args = ap.parse_args()

    transport = open_transport(args)
    if transport is None:
        return 1

    try:
        drain(transport, 0.5)  # boot banner replay / leftovers
        for cmd in args.cmds:
            if cmd.startswith("sleep "):
                drain(transport, float(cmd.split()[1]))
                continue
            print(f">>> {cmd}")
            try:
                transport.send(encode(cmd))
            except (ValueError, KeyError, IndexError) as e:
                print(f"[bad command {cmd!r}: {e}]")
                continue
            drain(transport, args.watch)
    except closed_exceptions():
        print("[connection closed mid-session (board reset?)]")
        return 0
    finally:
        if not args.no_stop:
            try:
                transport.send(simple_action(pw.SimpleCmd.STOP))
                drain(transport, 0.3)
            except closed_exceptions():
                pass
        transport.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
