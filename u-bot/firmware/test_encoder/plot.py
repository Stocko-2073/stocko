#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["pyserial>=3.5", "matplotlib>=3.8"]
# ///
"""Live scope for the AS5600 encoder test sketch (test_encoder.ino).

Reads the sketch's CSV stream and draws the angle within one turn (dial + strip
chart), the accumulated turns, and the speed -- plus a magnet health readout.
Each measure gets its own panel rather than sharing a y-axis.

Keys in the plot window are sent back to the board:

  z      zero the cumulative count      i  reprint the board's info banner
  d      flip the counting direction    q  quit
  space  pause/resume the stream

Usage:
  ./plot.py                             # /dev/cu.usbmodem2101 at 115200
  ./plot.py -p /dev/cu.usbmodem1101
  ./plot.py --log run.csv               # tee the raw stream to a file
  ./plot.py --replay run.csv            # plot a capture instead of the board

Opening the port resets the board, so the run always starts from its banner.
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

# STATUS register bits, matching test_encoder.ino.
MAGNET_HIGH = 0x08
MAGNET_LOW = 0x10
MAGNET_DETECT = 0x20

# Dark chart surface. Each panel holds a single series, so the panel title names
# it and no legend is needed; hues are categorical slots 1-3.
SURFACE = "#1a1a19"
PLANE = "#0d0d0d"
INK = "#ffffff"
INK_2 = "#c3c2b7"
MUTED = "#898781"
GRID = "#2c2c2a"
AXIS = "#383835"
ANGLE_C = "#3987e5"  # slot 1, blue
TURNS_C = "#d95926"  # slot 2, orange
SPEED_C = "#199e70"  # slot 3, aqua
GOOD = "#0ca30c"
WARNING = "#fab219"
CRITICAL = "#d03b3b"


def magnet_state(status):
    """(label, color) for a STATUS byte. The label carries the meaning; the
    color only reinforces it."""
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
    """The plot window: holds the rolling buffers and the artists."""

    def __init__(self, source, window=10.0, sample_hz=50):
        self.source = source
        self.window = window
        size = int(window * sample_hz * 1.5)
        self.t = deque(maxlen=size)
        self.deg = deque(maxlen=size)
        self.turns = deque(maxlen=size)
        self.dps = deque(maxlen=size)
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
                # Column header and help are noise in the UI; real notes aren't.
                if text and not text.startswith("t_ms,"):
                    self.note = text
                continue
            parts = line.split(",")
            if len(parts) != 8:
                self.bad_lines += 1
                continue
            try:
                t_ms, raw, deg, cum, dps = (
                    int(parts[0]), int(parts[1]), float(parts[2]), int(parts[3]), float(parts[4]),
                )
                agc, magnitude, status = int(parts[5]), int(parts[6]), int(parts[7], 16)
            except ValueError:
                self.bad_lines += 1
                continue
            self.t.append(t_ms / 1000.0)
            self.deg.append(deg)
            self.turns.append(cum / COUNTS_PER_REV)
            self.dps.append(dps)
            self.latest = dict(raw=raw, deg=deg, cum=cum, dps=dps, agc=agc,
                               magnitude=magnitude, status=status)

    def _rate(self):
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
        self.fig = plt.figure(figsize=(11, 6.5))
        self.fig.canvas.manager.set_window_title("AS5600 encoder scope")
        gs = GridSpec(3, 2, width_ratios=[1, 2.1], hspace=0.35, wspace=0.18,
                      left=0.04, right=0.97, top=0.93, bottom=0.09)

        self.ax_dial = self.fig.add_subplot(gs[0:2, 0], polar=True)
        self.ax_read = self.fig.add_subplot(gs[2, 0])
        self.ax_deg = self.fig.add_subplot(gs[0, 1])
        self.ax_turns = self.fig.add_subplot(gs[1, 1], sharex=self.ax_deg)
        self.ax_dps = self.fig.add_subplot(gs[2, 1], sharex=self.ax_deg)

        self._build_dial()
        for ax, title, color in ((self.ax_deg, "angle (deg)", ANGLE_C),
                                 (self.ax_turns, "turns", TURNS_C),
                                 (self.ax_dps, "speed (deg/s)", SPEED_C)):
            self._style_strip(ax, title, color)
        self.line_deg, = self.ax_deg.plot([], [], lw=1.8, color=ANGLE_C, solid_capstyle="round")
        self.line_turns, = self.ax_turns.plot([], [], lw=1.8, color=TURNS_C, solid_capstyle="round")
        self.line_dps, = self.ax_dps.plot([], [], lw=1.8, color=SPEED_C, solid_capstyle="round")
        self.ax_deg.set_ylim(0, 360)
        self.ax_deg.set_yticks([0, 90, 180, 270, 360])
        self.ax_dps.set_xlabel("seconds ago", color=MUTED)
        self.ax_deg.set_xlim(-self.window, 0)

        self.ax_read.axis("off")
        # Magnet health is the headline, so it sits above the numbers.
        self.magnet_dot = self.ax_read.text(0.0, 0.97, "", transform=self.ax_read.transAxes,
                                            va="center", ha="left", fontsize=13, color=MUTED)
        self.magnet_txt = self.ax_read.text(0.075, 0.97, "", transform=self.ax_read.transAxes,
                                            va="center", ha="left", fontsize=10, color=INK)
        self.readout = self.ax_read.text(0.0, 0.76, "", transform=self.ax_read.transAxes,
                                         va="top", ha="left", family="monospace",
                                         fontsize=9.5, color=INK_2, linespacing=1.7)
        self.note_txt = self.fig.text(0.04, 0.015, "", color=MUTED, fontsize=8.5,
                                      family="monospace")
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)

    def _build_dial(self):
        ax = self.ax_dial
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_ylim(0, 1)
        ax.set_yticklabels([])
        ax.set_xticks([0, 1.5707963, 3.1415927, 4.712389])
        ax.set_xticklabels(["0", "90", "180", "270"], color=MUTED, fontsize=8)
        ax.grid(color=GRID, lw=0.6)
        ax.spines["polar"].set_color(AXIS)
        ax.tick_params(pad=1)
        self.needle, = ax.plot([0, 0], [0, 0.86], lw=2, color=ANGLE_C, solid_capstyle="round")
        self.needle_tip, = ax.plot([0], [0.86], marker="o", ms=8, color=ANGLE_C)
        # The hub sits on the surface color so the needle passes behind the value
        # instead of striking through it.
        self.dial_hero = ax.text(0.5, 0.5, "--", transform=ax.transAxes, ha="center",
                                 va="center", fontsize=20, color=INK, zorder=5,
                                 bbox=dict(facecolor=SURFACE, edgecolor="none", pad=5))

    def _style_strip(self, ax, title, color):
        ax.set_title(title, color=INK_2, fontsize=10, loc="left", pad=6)
        ax.grid(True, color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(AXIS)
        ax.tick_params(colors=MUTED, labelsize=8, length=3)
        if ax is not self.ax_dps:
            ax.tick_params(labelbottom=False)

    # ---- redraw ----------------------------------------------------------
    def update(self, _frame=None):
        self._drain()
        if not self.t:
            self.note_txt.set_text(self.note)
            return ()
        now = self.t[-1]
        rel = [t - now for t in self.t]
        first = 0
        for i, r in enumerate(rel):
            if r >= -self.window:
                first = i
                break
        x = rel[first:]
        deg = list(self.deg)[first:]
        turns = list(self.turns)[first:]
        dps = list(self.dps)[first:]

        # Break the line at wraps instead of drawing a vertical streak across
        # the panel every time the angle rolls over 360 -> 0.
        wx, wy = [], []
        for i, (xi, yi) in enumerate(zip(x, deg)):
            if i and abs(yi - deg[i - 1]) > 180:
                wx.append(xi)
                wy.append(float("nan"))
            wx.append(xi)
            wy.append(yi)

        self.line_deg.set_data(wx, wy)
        self.line_turns.set_data(x, turns)
        self.line_dps.set_data(x, dps)
        self.ax_deg.set_xlim(-self.window, 0)
        self._fit(self.ax_turns, turns, floor=0.05)
        self._fit(self.ax_dps, dps, floor=20.0, symmetric=True)

        s = self.latest
        theta = s["deg"] * 3.14159265 / 180.0
        self.needle.set_data([theta, theta], [0, 0.86])
        self.needle_tip.set_data([theta], [0.86])
        self.dial_hero.set_text(f"{s['deg']:.1f}\N{DEGREE SIGN}")

        label, color = magnet_state(s["status"])
        self.readout.set_text(
            f"raw        {s['raw']:>5} / 4096\n"
            f"turns      {s['cum'] / COUNTS_PER_REV:>+8.3f}\n"
            f"speed      {s['dps']:>+8.1f} deg/s\n"
            f"agc        {s['agc']:>5}   (0-128 @3V3)\n"
            f"magnitude  {s['magnitude']:>5}\n"
            f"rate       {self._rate():>5.1f} Hz  bad {self.bad_lines}"
        )
        self.magnet_dot.set_text("●")
        self.magnet_dot.set_color(color)
        self.magnet_txt.set_text(f"magnet {label}")
        self.note_txt.set_text(self.note)
        return ()

    @staticmethod
    def _fit(ax, values, floor, symmetric=False):
        lo, hi = min(values), max(values)
        if symmetric:
            span = max(abs(lo), abs(hi), floor)
            ax.set_ylim(-span * 1.15, span * 1.15)
            return
        mid, span = (lo + hi) / 2, max(hi - lo, floor)
        ax.set_ylim(mid - span * 0.65, mid + span * 0.65)

    # ---- input -----------------------------------------------------------
    def _on_key(self, event):
        if event.key in ("z", "d", "i", " "):
            try:
                self.source.send("p" if event.key == " " else event.key)
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
    args = ap.parse_args()

    if args.replay:
        source = ReplaySource(args.replay, args.speed)
    else:
        try:
            source = SerialSource(args.port, args.baud)
        except serial.SerialException as exc:
            sys.exit(f"cannot open {args.port}: {exc}\n"
                     f"(close any serial monitor holding the port, or pass --port)")

    scope = Scope(source, window=args.window)
    log = open(args.log, "w") if args.log else None

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

    threading.Thread(target=reader, daemon=True).start()

    # Held in a local so the animation isn't garbage collected mid-run.
    from matplotlib.animation import FuncAnimation
    anim = FuncAnimation(scope.fig, scope.update, interval=50,
                         cache_frame_data=False, blit=False)
    try:
        plt.show()
    finally:
        del anim
        source.close()
        if log:
            log.close()


if __name__ == "__main__":
    main()
