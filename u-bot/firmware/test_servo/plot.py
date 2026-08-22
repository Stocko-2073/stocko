#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["pyserial>=3.5", "matplotlib>=3.8"]
# ///
"""Live scope for the closed-loop stepper servo sketch (test_servo.ino).

Four measures, four panels, one series each: where the shaft is against where it
was told to go, the error between them, the step rate the loop is asking for, and
the slip between commanded pulses and observed motion. Slip is the one to watch
-- it is the only panel that can tell you the motor didn't do as it was told.

Keys in the plot window are sent to the board:

  e  driver on/off       z  zero here          , .  nudge -/+0.05 turn
  l  loop on/off         f  clear fault        < >  nudge -/+0.25 turn
  c  calibrate           x  stop + disable     w    wiggle demo
  d  flip DIR            i  info banner        space pause stream   q quit

Usage:
  ./plot.py                             # /dev/cu.usbmodem2101 at 115200
  ./plot.py -p /dev/cu.usbmodem1101
  ./plot.py --log run.csv               # tee the raw stream to a file
  ./plot.py --replay run.csv            # plot a capture instead of the board
"""
import argparse
import sys
import threading
import time
from collections import deque

import matplotlib.pyplot as plt
import serial
from matplotlib.gridspec import GridSpec

DEFAULT_PORT = "/dev/cu.usbmodem2101"
BAUD = 115200
COUNTS_PER_REV = 4096

# STATUS bits and the flags byte, both matching test_servo.ino.
MAGNET_HIGH, MAGNET_LOW, MAGNET_DETECT = 0x08, 0x10, 0x20
F_DRIVER, F_LOOP, F_AT, F_FAULT, F_WIGGLE = 0x01, 0x02, 0x04, 0x08, 0x10

# Dark chart surface, same palette as test_encoder/plot.py: categorical slots
# 1-4 stepped for a dark surface. Each panel holds one series and its title
# names it, so the hue never has to carry identity on its own.
SURFACE, PLANE = "#1a1a19", "#0d0d0d"
INK, INK_2, MUTED = "#ffffff", "#c3c2b7", "#898781"
GRID, AXIS = "#2c2c2a", "#383835"
POS_C = "#3987e5"    # slot 1, blue
ERR_C = "#d95926"    # slot 2, orange
RATE_C = "#199e70"   # slot 3, aqua
SLIP_C = "#c98500"   # slot 4, yellow
GOOD, WARNING, CRITICAL = "#0ca30c", "#fab219", "#d03b3b"


def magnet_state(status):
    if not status & MAGNET_DETECT:
        return "no magnet", CRITICAL
    if status & MAGNET_LOW:
        return "too weak", WARNING
    if status & MAGNET_HIGH:
        return "too strong", WARNING
    return "ok", GOOD


class SerialSource:
    """Line reader for the board, with a key-command channel back to it."""

    def __init__(self, port, baud=BAUD):
        self.port = port
        self.ser = serial.Serial(port, baud, timeout=0.2)

    def lines(self):
        buf = bytearray()
        while True:
            chunk = self.ser.read(max(1, self.ser.in_waiting))
            if not chunk:
                continue
            buf.extend(chunk)
            while b"\n" in buf:
                raw, _, rest = buf.partition(b"\n")
                buf = bytearray(rest)
                yield raw.decode("utf-8", "replace").strip()

    def send(self, key):
        self.ser.write(key.encode())

    def close(self):
        self.ser.close()


class ReplaySource:
    """Replays a captured CSV at its recorded pace, for testing without hardware."""

    def __init__(self, path, speed=1.0):
        self.path = path
        self.speed = speed

    def lines(self):
        handle = sys.stdin if self.path == "-" else open(self.path)
        try:
            prev_ms = None
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                if not line.startswith("#"):
                    try:
                        t_ms = int(line.split(",")[0])
                    except (ValueError, IndexError):
                        t_ms = None
                    if t_ms is not None:
                        if prev_ms is not None and self.speed > 0:
                            time.sleep(min(0.2, max(0.0, (t_ms - prev_ms) / 1000.0 / self.speed)))
                        prev_ms = t_ms
                yield line
        finally:
            if handle is not sys.stdin:
                handle.close()

    def send(self, key):
        pass

    def close(self):
        pass


class Scope:
    """The plot window: rolling buffers and the artists over them."""

    def __init__(self, source, window=10.0, sample_hz=50, maxslip=200):
        self.source = source
        self.window = window
        self.maxslip = maxslip
        size = int(window * sample_hz * 1.5)
        self.t = deque(maxlen=size)
        self.pos = deque(maxlen=size)
        self.target = deque(maxlen=size)
        self.err = deque(maxlen=size)
        self.rate = deque(maxlen=size)
        self.slip = deque(maxlen=size)
        self.latest = None
        self.note = "waiting for data..."
        self.bad_lines = 0
        self._pending = []
        self._lock = threading.Lock()
        self._build()

    # ---- data ------------------------------------------------------------
    def feed(self, line):
        """Called from the reader thread; parked until the next redraw."""
        with self._lock:
            self._pending.append(line)

    def _drain(self):
        with self._lock:
            pending, self._pending = self._pending, []
        for line in pending:
            if line.startswith("#"):
                text = line.lstrip("# ").strip()
                print(line, flush=True)
                # The board reports its slip limit in the info banner; track it
                # so the threshold drawn on the slip panel is the real one.
                if "maxslip " in text:
                    try:
                        self.maxslip = int(text.split("maxslip ")[1].split()[0])
                    except (ValueError, IndexError):
                        pass
                if text and not text.startswith("t_ms,"):
                    self.note = text
                continue
            parts = line.split(",")
            if len(parts) != 12:
                self.bad_lines += 1
                continue
            try:
                t_ms = int(parts[0])
                pos, target = float(parts[1]), float(parts[2])
                err, vel = int(parts[3]), float(parts[4])
                steps, rate, slip = int(parts[5]), float(parts[6]), int(parts[7])
                enc, agc = int(parts[8]), int(parts[9])
                status, flags = int(parts[10], 16), int(parts[11], 16)
            except ValueError:
                self.bad_lines += 1
                continue
            self.t.append(t_ms / 1000.0)
            self.pos.append(pos)
            self.target.append(target)
            self.err.append(err)
            self.rate.append(rate)
            self.slip.append(slip)
            self.latest = dict(pos=pos, target=target, err=err, vel=vel, steps=steps,
                               rate=rate, slip=slip, enc=enc, agc=agc,
                               status=status, flags=flags)

    def _rate_hz(self):
        if len(self.t) < 2:
            return 0.0
        span = self.t[-1] - self.t[0]
        return (len(self.t) - 1) / span if span > 0 else 0.0

    # ---- figure ----------------------------------------------------------
    def _build(self):
        plt.rcParams.update({
            "figure.facecolor": PLANE, "axes.facecolor": SURFACE,
            "font.family": "sans-serif", "font.size": 9,
        })
        # The board owns these keys; matplotlib's defaults would eat l, p, f, x.
        for key in [k for k in plt.rcParams if k.startswith("keymap.")]:
            plt.rcParams[key] = []

        self.fig = plt.figure(figsize=(11.5, 7.5))
        self.fig.canvas.manager.set_window_title("stepper servo scope")
        gs = GridSpec(4, 2, width_ratios=[1, 2.2], hspace=0.40, wspace=0.16,
                      left=0.04, right=0.97, top=0.92, bottom=0.07)

        self.ax_dial = self.fig.add_subplot(gs[0:2, 0], polar=True)
        self.ax_read = self.fig.add_subplot(gs[2:4, 0])
        self.ax_pos = self.fig.add_subplot(gs[0, 1])
        self.ax_err = self.fig.add_subplot(gs[1, 1], sharex=self.ax_pos)
        self.ax_rate = self.fig.add_subplot(gs[2, 1], sharex=self.ax_pos)
        self.ax_slip = self.fig.add_subplot(gs[3, 1], sharex=self.ax_pos)

        self._build_dial()
        for ax, title in ((self.ax_pos, "position (output turns)"),
                          (self.ax_err, "error (encoder counts)"),
                          (self.ax_rate, "step rate (steps/s)"),
                          (self.ax_slip, "slip (steps commanded but not moved)")):
            self._style_strip(ax, title, bottom=(ax is self.ax_slip))

        # Position panel carries two marks, so both are named rather than left
        # to colour: the target is a reference, drawn dashed and recessive.
        self.line_target, = self.ax_pos.plot([], [], lw=1.4, color=MUTED, ls="--",
                                             label="target")
        self.line_pos, = self.ax_pos.plot([], [], lw=2, color=POS_C,
                                          solid_capstyle="round", label="position")
        leg = self.ax_pos.legend(loc="upper left", frameon=False, fontsize=8,
                                 labelcolor=INK_2, handlelength=1.6, ncols=2,
                                 borderpad=0, handletextpad=0.5, columnspacing=1.2)
        leg.set_zorder(6)

        self.line_err, = self.ax_err.plot([], [], lw=2, color=ERR_C, solid_capstyle="round")
        self.line_rate, = self.ax_rate.plot([], [], lw=2, color=RATE_C, solid_capstyle="round")
        self.line_slip, = self.ax_slip.plot([], [], lw=2, color=SLIP_C, solid_capstyle="round")
        for ax in (self.ax_err, self.ax_rate, self.ax_slip):
            ax.axhline(0, color=AXIS, lw=0.8, zorder=1)
        # Slip has a hard meaning: cross it and the board faults out.
        self.slip_hi = self.ax_slip.axhline(self.maxslip, color=WARNING, lw=1,
                                           ls=":", zorder=1)
        self.slip_lo = self.ax_slip.axhline(-self.maxslip, color=WARNING, lw=1,
                                           ls=":", zorder=1)
        # Pinned to the line it names (x in axes coords, y in data coords) with
        # a surface-coloured backing, so it reads over the trace instead of
        # colliding with whatever the newest sample happens to be doing.
        from matplotlib.transforms import blended_transform_factory
        self.slip_label = self.ax_slip.text(
            0.995, self.maxslip, "", ha="right", va="bottom", fontsize=7.5,
            color=WARNING, zorder=6,
            transform=blended_transform_factory(self.ax_slip.transAxes,
                                                self.ax_slip.transData),
            bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1.5))

        self.ax_slip.set_xlabel("seconds ago", color=MUTED)
        self.ax_pos.set_xlim(-self.window, 0)

        self.ax_read.axis("off")
        self.state_txt = self.ax_read.text(0.0, 0.99, "", transform=self.ax_read.transAxes,
                                           va="top", ha="left", fontsize=9.5, color=INK)
        self.fault_dot = self.ax_read.text(0.0, 0.87, "", transform=self.ax_read.transAxes,
                                           va="center", ha="left", fontsize=13, color=MUTED)
        self.fault_txt = self.ax_read.text(0.075, 0.87, "", transform=self.ax_read.transAxes,
                                           va="center", ha="left", fontsize=10, color=INK)
        self.magnet_dot = self.ax_read.text(0.0, 0.79, "", transform=self.ax_read.transAxes,
                                            va="center", ha="left", fontsize=13, color=MUTED)
        self.magnet_txt = self.ax_read.text(0.075, 0.79, "", transform=self.ax_read.transAxes,
                                            va="center", ha="left", fontsize=10, color=INK)
        self.readout = self.ax_read.text(0.0, 0.69, "", transform=self.ax_read.transAxes,
                                         va="top", ha="left", family="monospace",
                                         fontsize=9.5, color=INK_2, linespacing=1.75)
        self.note_txt = self.fig.text(0.04, 0.012, "", color=MUTED, fontsize=8.5,
                                      family="monospace")
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)

    def _build_dial(self):
        ax = self.ax_dial
        ax.set_title("shaft angle within the turn", color=INK_2, fontsize=10, pad=14)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_ylim(0, 1)
        ax.set_yticklabels([])
        ax.set_xticks([0, 1.5707963, 3.1415927, 4.712389])
        ax.set_xticklabels(["0", "90", "180", "270"], color=MUTED, fontsize=8)
        ax.grid(color=GRID, lw=0.6)
        ax.spines["polar"].set_color(AXIS)
        ax.tick_params(pad=1)
        self.needle_t, = ax.plot([0, 0], [0, 0.86], lw=1.4, color=MUTED, ls="--")
        self.needle, = ax.plot([0, 0], [0, 0.86], lw=2, color=POS_C, solid_capstyle="round")
        self.needle_tip, = ax.plot([0], [0.86], marker="o", ms=8, color=POS_C)
        # The hub sits on the surface colour so the needle passes behind the
        # value rather than striking through it.
        self.dial_hero = ax.text(0.5, 0.5, "--", transform=ax.transAxes, ha="center",
                                 va="center", fontsize=19, color=INK, zorder=5,
                                 bbox=dict(facecolor=SURFACE, edgecolor="none", pad=5))

    def _style_strip(self, ax, title, bottom):
        ax.set_title(title, color=INK_2, fontsize=10, loc="left", pad=6)
        ax.grid(True, color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(AXIS)
        ax.tick_params(colors=MUTED, labelsize=8, length=3)
        if not bottom:
            ax.tick_params(labelbottom=False)

    # ---- redraw ----------------------------------------------------------
    def update(self, _frame=None):
        self._drain()
        if not self.t:
            self.note_txt.set_text(self.note)
            return ()
        now = self.t[-1]
        rel = [t - now for t in self.t]
        first = next((i for i, r in enumerate(rel) if r >= -self.window), 0)
        x = rel[first:]
        pos = list(self.pos)[first:]
        target = list(self.target)[first:]
        err = list(self.err)[first:]
        rate = list(self.rate)[first:]
        slip = list(self.slip)[first:]

        self.line_pos.set_data(x, pos)
        self.line_target.set_data(x, target)
        self.line_err.set_data(x, err)
        self.line_rate.set_data(x, rate)
        self.line_slip.set_data(x, slip)
        self.ax_pos.set_xlim(-self.window, 0)
        self._fit(self.ax_pos, pos + target, floor=0.05)
        self._fit(self.ax_err, err, floor=20.0, symmetric=True)
        self._fit(self.ax_rate, rate, floor=100.0, symmetric=True)
        self._fit(self.ax_slip, slip + [self.maxslip * 1.1, -self.maxslip * 1.1],
                  floor=float(self.maxslip), symmetric=True)
        self.slip_hi.set_ydata([self.maxslip, self.maxslip])
        self.slip_lo.set_ydata([-self.maxslip, -self.maxslip])
        self.slip_label.set_position((0.995, self.maxslip))
        self.slip_label.set_text(f"±{self.maxslip} = fault")

        s = self.latest
        # Dial in the same zeroed frame as the target, so both needles agree.
        theta = (s["pos"] % 1.0) * 2 * 3.14159265
        theta_t = (s["target"] % 1.0) * 2 * 3.14159265
        self.needle.set_data([theta, theta], [0, 0.86])
        self.needle_tip.set_data([theta], [0.86])
        self.needle_t.set_data([theta_t, theta_t], [0, 0.86])
        self.dial_hero.set_text(f"{s['pos']:+.3f}")

        f = s["flags"]
        chips = [("driver", f & F_DRIVER), ("loop", f & F_LOOP),
                 ("at target", f & F_AT), ("wiggle", f & F_WIGGLE)]
        self.state_txt.set_text("   ".join(
            f"{'●' if on else '○'} {name}" for name, on in chips))

        faulted = bool(f & F_FAULT)
        self.fault_dot.set_text("●")
        self.fault_dot.set_color(CRITICAL if faulted else GOOD)
        self.fault_txt.set_text("FAULT: slip" if faulted else "no fault")

        label, color = magnet_state(s["status"])
        self.magnet_dot.set_text("●")
        self.magnet_dot.set_color(color)
        self.magnet_txt.set_text(f"magnet {label}  (agc {s['agc']})")

        self.readout.set_text(
            f"position   {s['pos']:>+9.4f} turns\n"
            f"target     {s['target']:>+9.4f} turns\n"
            f"error      {s['err']:>+9} counts ({s['err'] * 360.0 / COUNTS_PER_REV:+.2f}\N{DEGREE SIGN})\n"
            f"speed      {s['vel']:>+9.3f} turns/s\n"
            f"step rate  {s['rate']:>+9.0f} steps/s\n"
            f"steps      {s['steps']:>+9}\n"
            f"slip       {s['slip']:>+9} steps\n"
            f"raw angle  {s['enc']:>9} / 4096\n"
            f"stream     {self._rate_hz():>9.1f} Hz  bad {self.bad_lines}"
        )
        self.note_txt.set_text(self.note)
        return ()

    @staticmethod
    def _fit(ax, values, floor, symmetric=False):
        if not values:
            return
        lo, hi = min(values), max(values)
        if symmetric:
            span = max(abs(lo), abs(hi), floor)
            ax.set_ylim(-span * 1.15, span * 1.15)
            return
        mid, span = (lo + hi) / 2, max(hi - lo, floor)
        ax.set_ylim(mid - span * 0.65, mid + span * 0.65)

    # ---- input -----------------------------------------------------------
    KEYS = set("elcdzfxwi,.<>")

    def _on_key(self, event):
        if event.key == "q":
            plt.close(self.fig)
            return
        key = "p" if event.key == " " else event.key
        if key not in self.KEYS and key != "p":
            return
        try:
            self.source.send(key)
        except Exception as exc:  # port yanked mid-run
            self.note = f"send failed: {exc}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-p", "--port", default=DEFAULT_PORT)
    ap.add_argument("-b", "--baud", type=int, default=BAUD)
    ap.add_argument("-w", "--window", type=float, default=10.0,
                    help="seconds of history on the strip charts (default 10)")
    ap.add_argument("--log", metavar="FILE", help="tee every received line to FILE")
    ap.add_argument("--replay", metavar="FILE", help="plot a capture ('-' for stdin)")
    ap.add_argument("--speed", type=float, default=1.0, help="replay speed multiplier")
    ap.add_argument("--save", metavar="FILE",
                    help="render one frame to FILE after the stream ends and exit")
    args = ap.parse_args()

    if args.replay:
        source = ReplaySource(args.replay, args.speed)
    else:
        try:
            source = SerialSource(args.port, args.baud)
        except serial.SerialException as exc:
            sys.exit(f"cannot open {args.port}: {exc}\n"
                     f"(close any serial monitor holding the port, or pass --port)")

    if args.save:
        import matplotlib
        matplotlib.use("Agg")

    scope = Scope(source, window=args.window)
    log = open(args.log, "w") if args.log else None
    done = threading.Event()

    def reader():
        try:
            for line in source.lines():
                if log:
                    log.write(line + "\n")
                    log.flush()
                scope.feed(line)
        except Exception as exc:
            scope.note = f"stream ended: {exc}"
        else:
            scope.note = "stream ended"
        done.set()

    threading.Thread(target=reader, daemon=True).start()

    try:
        if args.save:
            done.wait(120)
            scope.update()
            scope.fig.savefig(args.save, facecolor=PLANE, dpi=110)
            print(f"wrote {args.save}")
            return
        # Held in a local so the animation isn't garbage collected mid-run.
        from matplotlib.animation import FuncAnimation
        anim = FuncAnimation(scope.fig, scope.update, interval=50,
                             cache_frame_data=False, blit=False)
        plt.show()
        del anim
    finally:
        source.close()
        if log:
            log.close()


if __name__ == "__main__":
    main()
