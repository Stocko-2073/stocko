"""Talking to the bench firmware over USB serial."""

import queue
import struct
import threading
import time

import numpy as np

from . import protocol as p

RASPBERRY_PI_VID = 0x2E8A


class BenchError(RuntimeError):
    pass


def find_port():
    """The first USB serial port that belongs to an RP2040."""
    from serial.tools import list_ports

    ports = list(list_ports.comports())
    for port in ports:
        if port.vid == RASPBERRY_PI_VID:
            return port.device
    names = ", ".join(port.device for port in ports) or "none"
    raise BenchError(f"no RP2040 found (ports: {names}); pass --port")


class Recording:
    """Everything the board streamed during one run, kept as raw payloads until
    the end so the reader thread does no per-sample work."""

    def __init__(self):
        self.payloads = {p.TICK: bytearray(), p.FRAME: bytearray(), p.STATUS: bytearray(),
                         p.LOAD: bytearray(), p.RUN_DONE: bytearray()}
        self.taps = []
        self.markers = []

    def add(self, kind, payload):
        if kind == p.TAPS:
            head = np.frombuffer(payload, p.TAPS_HEAD_DTYPE, count=1)[0]
            self.taps.append((int(head["first_idx"]), payload[p.TAPS_HEAD_DTYPE.itemsize:]))
        elif kind in self.payloads:
            self.payloads[kind] += payload

    def mark(self, t_us, label):
        """A host-side marker such as "pin in hole 3", at a board time."""
        self.markers.append((int(t_us), label))

    def arrays(self):
        out = {
            "ticks": np.frombuffer(bytes(self.payloads[p.TICK]), p.TICK_DTYPE),
            "frames": np.frombuffer(bytes(self.payloads[p.FRAME]), p.FRAME_DTYPE),
            "status": np.frombuffer(bytes(self.payloads[p.STATUS]), p.STATUS_DTYPE),
            "loads": np.frombuffer(bytes(self.payloads[p.LOAD]), p.LOAD_DTYPE),
            "run_done": np.frombuffer(bytes(self.payloads[p.RUN_DONE]), p.RUN_DONE_DTYPE),
        }
        if self.taps:
            out["taps_first"] = np.array([first for first, _ in self.taps], np.uint32)
            out["taps_n"] = np.array([len(data) // 2 for _, data in self.taps], np.uint32)
            out["taps"] = np.frombuffer(b"".join(data for _, data in self.taps), "<u2")
        return out


class Bench:
    """The bench as Python calls. ``transport`` is anything with ``write(bytes)``,
    ``read(n)`` and ``in_waiting``: a pyserial port, or a fake in the tests."""

    def __init__(self, transport):
        self.transport = transport
        self.decoder = p.Decoder()
        self.replies = queue.Queue()
        self.events = queue.Queue()
        self.recording = None
        self.on_message = None
        self.last_tick_us = 0
        self.closed = False
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()

    @classmethod
    def open(cls, port=None):
        import serial

        return cls(serial.Serial(port or find_port(), 115200, timeout=0.05))

    def close(self):
        self.closed = True
        self.reader.join(timeout=1)
        self.transport.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _read_loop(self):
        while not self.closed:
            try:
                data = self.transport.read(max(1, self.transport.in_waiting))
            except Exception as exc:   # port unplugged mid-run
                self.events.put((p.TEXT, f"serial error: {exc}".encode()))
                return
            if not data:
                continue
            for kind, payload in self.decoder.feed(data):
                self._dispatch(kind, payload)

    def _dispatch(self, kind, payload):
        if kind == p.REPLY:
            self.replies.put(p.decode_one(kind, payload))
            return
        if kind == p.TICK:
            self.last_tick_us = struct.unpack_from("<I", payload)[0]
        rec = self.recording
        if rec is not None:
            rec.add(kind, payload)
        if kind in (p.HELLO, p.SELFTEST, p.RUN_DONE, p.TEXT):
            self.events.put((kind, payload))
        if self.on_message is not None:
            self.on_message(kind, payload)

    # --- commands ---

    def command(self, cmd, payload=b"", timeout=1.0):
        while not self.replies.empty():
            self.replies.get_nowait()
        self.transport.write(p.encode(cmd, payload))
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise BenchError(f"no reply to command 0x{cmd:02X} within {timeout} s")
            try:
                reply = self.replies.get(timeout=left)
            except queue.Empty:
                continue
            if reply["cmd"] == cmd:
                break
        code = int(reply["code"])
        if code != p.OK:
            raise BenchError(f"command 0x{cmd:02X}: {p.ERRORS.get(code, code)}")

    def wait_event(self, kind, timeout):
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise BenchError(f"timed out waiting for message 0x{kind:02X}")
            try:
                got, payload = self.events.get(timeout=left)
            except queue.Empty:
                continue
            if got == kind:
                return payload

    def _flush_events(self):
        while not self.events.empty():
            self.events.get_nowait()

    def ping(self):
        self._flush_events()
        self.command(p.CMD_PING)
        hello = p.decode_one(p.HELLO, self.wait_event(p.HELLO, 1.0))
        if hello["version"] != p.VERSION:
            raise BenchError(f"firmware speaks protocol {hello['version']}, host {p.VERSION}")
        return hello

    def selftest(self):
        self._flush_events()
        self.command(p.CMD_SELFTEST)
        return p.decode_one(p.SELFTEST, self.wait_event(p.SELFTEST, 2.0))

    def set_frame(self, frame_us):
        self.command(p.CMD_SET_FRAME, struct.pack("<H", frame_us))

    def set_idle(self, width_us):
        self.command(p.CMD_SET_IDLE, struct.pack("<H", width_us))

    def stream(self, on):
        self.command(p.CMD_STREAM, bytes([bool(on)]))

    def raw_taps(self, on):
        self.command(p.CMD_RAW_TAPS, bytes([bool(on)]))

    def loadcell(self, on):
        self.command(p.CMD_LOADCELL, bytes([bool(on)]))

    def stop(self):
        self.command(p.CMD_STOP)

    def upload(self, widths):
        widths = np.asarray(widths, "<u2")
        self.command(p.CMD_SCHED_CLEAR)
        for offset in range(0, len(widths), p.SCHED_CHUNK):
            chunk = widths[offset:offset + p.SCHED_CHUNK]
            self.command(p.CMD_SCHED_DATA, struct.pack("<IH", offset, len(chunk)) + chunk.tobytes())

    def run(self, widths, frame_us, end_us=None, raw=False, loadcell=False,
            settle_s=1.0, pre_s=0.5, post_s=0.5):
        """Play one schedule and return everything streamed around it.

        The servo first moves to the schedule's first width and settles there
        unrecorded; recording starts ``pre_s`` before the first scheduled frame
        and ends ``post_s`` after the last. After the run every frame carries
        ``end_us`` (default: hold the last width; 0 leaves the servo limp).
        """
        widths = np.asarray(widths, "<u2")
        if end_us is None:
            end_us = int(widths[-1])
        self.stream(False)
        self.set_frame(frame_us)
        self.upload(widths)
        self.set_idle(int(widths[0]))
        time.sleep(settle_s)

        rec = Recording()
        self._flush_events()
        self.recording = rec
        try:
            self.raw_taps(raw)
            self.loadcell(loadcell)
            self.stream(True)
            time.sleep(pre_s)
            self.command(p.CMD_RUN, struct.pack("<IH", len(widths), end_us))
            self.wait_event(p.RUN_DONE, len(widths) * frame_us / 1e6 + 5.0)
            time.sleep(post_s)
        finally:
            self.stream(False)
            self.raw_taps(False)
            self.loadcell(False)
            time.sleep(0.1)
            self.recording = None
        return rec
