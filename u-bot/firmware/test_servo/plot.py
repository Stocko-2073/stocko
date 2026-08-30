#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["pyserial>=3.5", "matplotlib>=3.8"]
# ///
"""Live scope for the closed-loop stepper servo sketch (test_servo.ino).

Two wheels, one driver so far. Wheel A is the servo -- driver, encoder and the
whole loop. Wheel B is an encoder only, on the bit-banged bus, so it reads as a
dial and a trace and nothing more until it gets a driver of its own.

Four measures, four panels: where wheel A is against where it was told to go,
the error between them, the step rate the loop is asking for, and the slip
between commanded pulses and observed motion. Slip is the one to watch -- it is
the only panel that can tell you the motor didn't do as it was told. Wheel B
rides along on the position panel, which is the only measure it has.

Columns come from the header line the sketch prints at boot, indexed by name --
so the board can grow columns without this needing a matching edit. Attaching to
a board that booted before the port was opened means that line has long gone, so
the scope asks for it ('i') rather than guessing from the field count.

A control bar runs along the bottom for driving the axis by hand. Everything
on it is a shortcut for a line the sketch already parses, so the bar cannot ask
for a state the serial console couldn't: buttons for the toggles, a nudge pad,
a target slider you can drag to jog the axis live, a vmax slider, and a cmd box
that takes any word command (spin 400, jog 1000, kp 12, amp 0.5, ratio ...).

Keys in the plot window are sent to the board:

  e  driver on/off       z  zero here          , .  nudge -/+0.05 turn
  l  loop on/off         f  clear fault        < >  nudge -/+0.25 turn
  c  calibrate           x  stop + disable     w    wiggle demo
  d  flip DIR            i  info banner        space pause stream   q quit
  left/right nudge -/+0.05 turn, up/down -/+0.25 turn

Usage:
  ./plot.py                             # /dev/cu.usbmodem2101 at 115200
  ./plot.py -p /dev/cu.usbmodem1101
  ./plot.py --span 6                    # target slider reaches +/-6 turns
  ./plot.py --log run.csv               # tee the raw stream to a file
  ./plot.py --replay run.csv            # plot a capture instead of the board
"""
import argparse
import math
import sys
import threading
import time
from collections import deque

import matplotlib.pyplot as plt
import serial
from matplotlib.gridspec import GridSpec
from matplotlib.widgets import Button, Slider, TextBox

DEFAULT_PORT = "/dev/cu.usbmodem2101"
BAUD = 115200
COUNTS_PER_REV = 4096
# The sketch clamps vmax here (measured on this axis: clean to 1.0 turns/s,
# shedding steps by 2.76), so the slider stops where the board would anyway.
VMAX_LIMIT = 2.0

# STATUS bits and the flags byte, both matching test_servo.ino.
MAGNET_HIGH, MAGNET_LOW, MAGNET_DETECT = 0x08, 0x10, 0x20
F_DRIVER, F_LOOP, F_AT, F_FAULT, F_WIGGLE, F_ENCB = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20

# What a stream that never named its columns is assumed to be sending: captures
# taken before the header line existed. A live board is asked instead.
LEGACY_COLUMNS = "t_ms,pos,target,err,vel,steps,rate,slip,enc,agc,status,flags".split(",")

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
WHEEL_B = "#9d6ee8"  # slot 5, violet -- the second wheel, wherever both appear
GOOD, WARNING, CRITICAL = "#0ca30c", "#fab219", "#d03b3b"
# Controls sit a step off the surface so the bar reads as chrome, not data.
CTRL, CTRL_HOVER, TRACK = "#262623", "#35352f", "#212120"


def mix(a, b, t):
    """Blend two #rrggbb colours; t=0 is all a, t=1 is all b."""
    ai = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    bi = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ai, bi))


def num(row, name, cast=float, default=0):
    """One named field, or `default` if this firmware doesn't send it."""
    text = row.get(name)
    return default if text is None else cast(text)


def hexint(text):
    return int(text, 16)


def magnet_state(status):
    if not status & MAGNET_DETECT:
        return "no magnet", CRITICAL
    if status & MAGNET_LOW:
        return "magnet too weak", WARNING
    if status & MAGNET_HIGH:
        return "magnet too strong", WARNING
    return "magnet ok", GOOD


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

    def __init__(self, source, window=10.0, sample_hz=50, maxslip=200, span=3.0):
        self.source = source
        self.window = window
        self.maxslip = maxslip
        self.span = span
        size = int(window * sample_hz * 1.5)
        self.t = deque(maxlen=size)
        self.pos = deque(maxlen=size)
        self.target = deque(maxlen=size)
        self.err = deque(maxlen=size)
        self.rate = deque(maxlen=size)
        self.slip = deque(maxlen=size)
        self.bpos = deque(maxlen=size)
        self.columns = LEGACY_COLUMNS
        self.header_seen = False
        self._header_asked = 0.0
        self._header_tries = 0
        self.latest = None
        self.note = "waiting for data..."
        self.bad_lines = 0
        self.paused = False
        self.vmax = None       # learned from the board's banner
        self._pending = []
        self._lock = threading.Lock()
        # Slider bookkeeping: _echo suppresses the callback while we are the
        # ones moving the handle, _sent_at throttles the stream of commands a
        # drag would otherwise produce, and _queued is the value a throttled
        # move still owes the board when the mouse comes up.
        self._echo = False
        self._sent_at = 0.0
        self._queued = None
        self.cmd = None         # the cmd box, once _build_controls has run
        self._entered = False
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
                # Same trick for vmax, so the speed slider starts where the
                # board actually is rather than at some guess of ours.
                if "vmax " in text:
                    try:
                        self.vmax = float(text.split("vmax ")[1].split()[0])
                    except (ValueError, IndexError):
                        pass
                if text in ("paused", "streaming"):
                    self.paused = text == "paused"
                # The sketch names its own columns; take it at its word rather
                # than counting on a fixed order that is about to change again.
                if text.startswith("t_ms,"):
                    columns = text.split(",")
                    # Lines dropped before this arrived were dropped for want of
                    # it, and are now explained -- don't leave them on the tally
                    # looking like line noise.
                    if columns != self.columns:
                        self.bad_lines = 0
                    self.columns, self.header_seen = columns, True
                    continue
                if text:
                    self.note = text
                continue
            parts = line.split(",")
            if len(parts) != len(self.columns):
                self.bad_lines += 1
                # Say which way the mismatch runs. Silently dropping every line
                # is what made this look like a dead port rather than a parser
                # reading the stream against the wrong header.
                self.note = (
                    f"stream has {len(parts)} columns, header says"
                    f" {len(self.columns)}" if self.header_seen else
                    f"stream has {len(parts)} columns and has not named them"
                    " -- asking the board (i)")
                continue
            row = dict(zip(self.columns, parts))
            try:
                s = dict(
                    pos=num(row, "pos"), target=num(row, "target"),
                    err=num(row, "err", int), vel=num(row, "vel"),
                    steps=num(row, "steps", int), rate=num(row, "rate"),
                    slip=num(row, "slip", int), enc=num(row, "enc", int),
                    agc=num(row, "agc", int), status=num(row, "status", hexint),
                    flags=num(row, "flags", hexint),
                    bpos=num(row, "bpos"), bvel=num(row, "bvel"),
                    benc=num(row, "benc", int), bagc=num(row, "bagc", int),
                    bstatus=num(row, "bstatus", hexint),
                    busus=num(row, "busus", int),
                )
                t_ms = int(row["t_ms"])
            except (KeyError, ValueError):
                self.bad_lines += 1
                continue
            self.t.append(t_ms / 1000.0)
            self.pos.append(s["pos"])
            self.target.append(s["target"])
            self.err.append(s["err"])
            self.rate.append(s["rate"])
            self.slip.append(s["slip"])
            self.bpos.append(s["bpos"])
            self.latest = s

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

        # Taller than the panels need: the bottom eighth is the control bar,
        # and the note line moves up top so nothing sits under the widgets.
        self.fig = plt.figure(figsize=(12.2, 8.8))
        self.fig.canvas.manager.set_window_title("u-bot wheel scope")
        gs = GridSpec(4, 2, width_ratios=[1.2, 2.2], hspace=0.40, wspace=0.16,
                      left=0.035, right=0.97, top=0.905, bottom=0.195)

        # The two dials share the cell the single one used to have. They are the
        # per-wheel readout now: magnet health belongs under the dial it
        # describes, because with two encoders one shared line could only ever
        # be ambiguous about which of them is complaining.
        from matplotlib.gridspec import GridSpecFromSubplotSpec
        dials = GridSpecFromSubplotSpec(1, 2, subplot_spec=gs[0:2, 0], wspace=0.30)
        self.ax_dial_a = self.fig.add_subplot(dials[0], polar=True)
        self.ax_dial_b = self.fig.add_subplot(dials[1], polar=True)
        self.ax_read = self.fig.add_subplot(gs[2:4, 0])
        self.ax_pos = self.fig.add_subplot(gs[0, 1])
        self.ax_err = self.fig.add_subplot(gs[1, 1], sharex=self.ax_pos)
        self.ax_rate = self.fig.add_subplot(gs[2, 1], sharex=self.ax_pos)
        self.ax_slip = self.fig.add_subplot(gs[3, 1], sharex=self.ax_pos)

        self.dial_a = self._build_dial(self.ax_dial_a, "wheel A", POS_C, True)
        self.dial_b = self._build_dial(self.ax_dial_b, "wheel B", WHEEL_B, False)
        # Only wheel A has a driver, so three of the four panels are about it
        # alone -- say so, now that there is a second wheel on screen to confuse
        # them with. The position panel carries both and names them in its legend.
        for ax, title in ((self.ax_pos, "position (output turns)"),
                          (self.ax_err, "wheel A error (encoder counts)"),
                          (self.ax_rate, "wheel A step rate (steps/s)"),
                          (self.ax_slip, "wheel A slip (steps commanded but not moved)")):
            self._style_strip(ax, title, bottom=(ax is self.ax_slip))

        # The one panel where hue has to carry identity, so everything on it is
        # named in the legend: A's target is a reference, drawn dashed and
        # recessive, and B is here because position is the only measure it has.
        self.line_target, = self.ax_pos.plot([], [], lw=1.4, color=MUTED, ls="--",
                                             label="A target")
        self.line_pos, = self.ax_pos.plot([], [], lw=2, color=POS_C,
                                          solid_capstyle="round", label="wheel A")
        self.line_bpos, = self.ax_pos.plot([], [], lw=2, color=WHEEL_B,
                                           solid_capstyle="round", label="wheel B")
        leg = self.ax_pos.legend(loc="upper left", frameon=False, fontsize=8,
                                 labelcolor=INK_2, handlelength=1.6, ncols=3,
                                 borderpad=0, handletextpad=0.5, columnspacing=1.2)
        leg.set_zorder(6)
        self.leg_b = (leg.legend_handles[2], leg.get_texts()[2])

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
        self.readout = self.ax_read.text(0.0, 0.74, "", transform=self.ax_read.transAxes,
                                         va="top", ha="left", family="monospace",
                                         fontsize=9.5, color=INK_2, linespacing=1.75)
        self.note_txt = self.fig.text(0.395, 0.955, "", color=MUTED, fontsize=8,
                                      family="monospace")

        # Registered before the controls, so this runs ahead of the cmd box's
        # own key handler -- the one chance to see an enter before the box acts.
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)
        self._build_controls()
        # A throttled drag can end owing the board one last value; the button
        # coming up is when we settle that debt.
        self.fig.canvas.mpl_connect("button_release_event", self._on_release)

    def _build_dial(self, ax, title, color, target_needle):
        """One wheel's dial: angle within the turn, plus that wheel's health."""
        ax.set_title(title, color=INK_2, fontsize=10, pad=10)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_ylim(0, 1)
        ax.set_yticklabels([])
        ax.set_xticks([0, 1.5707963, 3.1415927, 4.712389])
        # Grid at all four quarters, but only the vertical pair is labelled:
        # side labels on adjacent dials collide in the gap between them.
        ax.set_xticklabels(["0", "", "180", ""], color=MUTED, fontsize=7.5)
        ax.grid(color=GRID, lw=0.6)
        ax.spines["polar"].set_color(AXIS)
        ax.tick_params(pad=0)
        d = {"color": color}
        # Only the servo wheel has a target to point at; B's stays hidden until
        # it has a driver that could chase one.
        d["target"] = ax.plot([0, 0], [0, 0.86], lw=1.3, color=MUTED, ls="--",
                              visible=target_needle)[0]
        d["needle"] = ax.plot([0, 0], [0, 0.86], lw=2, color=color,
                              solid_capstyle="round")[0]
        d["tip"] = ax.plot([0], [0.86], marker="o", ms=7, color=color)[0]
        # The hub sits on the surface colour so the needle passes behind the
        # value rather than striking through it.
        d["hero"] = ax.text(0.5, 0.5, "--", transform=ax.transAxes, ha="center",
                            va="center", fontsize=15, color=INK, zorder=5,
                            bbox=dict(facecolor=SURFACE, edgecolor="none", pad=4))
        d["magnet"] = ax.text(0.5, -0.17, "", transform=ax.transAxes, ha="center",
                              va="top", fontsize=8.5, color=MUTED)
        d["raw"] = ax.text(0.5, -0.30, "", transform=ax.transAxes, ha="center",
                           va="top", fontsize=8, color=MUTED, family="monospace")
        return d

    def _update_dial(self, d, turns, raw, agc, status, live, target=None):
        theta = (turns % 1.0) * math.tau
        d["needle"].set_data([theta, theta], [0, 0.86])
        d["tip"].set_data([theta], [0.86])
        if target is not None:
            t = (target % 1.0) * math.tau
            d["target"].set_data([t, t], [0, 0.86])
        d["hero"].set_text(f"{turns:+.3f}")
        # A wheel that is not answering shows the last angle it gave, greyed:
        # a stale needle at full strength is indistinguishable from a stopped
        # one, which is the confusion worth designing out.
        ink = d["color"] if live else mix(d["color"], SURFACE, 0.72)
        d["needle"].set_color(ink)
        d["tip"].set_color(ink)
        d["hero"].set_color(INK if live else MUTED)
        if not live:
            d["magnet"].set_text("not responding")
            d["magnet"].set_color(CRITICAL)
            d["raw"].set_text("--")
            return
        label, color = magnet_state(status)
        d["magnet"].set_text(label)
        d["magnet"].set_color(color)
        d["raw"].set_text(f"{raw:>4} / 4096   agc {agc}")

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

    # ---- controls --------------------------------------------------------
    # label, what to send, and the colour the button wears while that state is
    # live. A None accent is a one-shot with no state to report back.
    ACTIONS = [
        ("driver", "e", GOOD),
        ("loop", "l", POS_C),
        ("wiggle", "w", SLIP_C),
        ("calibrate", "c", None),
        ("zero", "z", None),
        ("clear fault", "f", CRITICAL),
        ("flip DIR", "d", None),
        ("pause", "p", WARNING),
        ("info", "i", None),
        ("STOP", "x", None),
    ]
    LIT_BY_FLAG = {"e": F_DRIVER, "l": F_LOOP, "w": F_WIGGLE, "f": F_FAULT}

    def _build_controls(self):
        """The bottom bar. Every widget sends a command the sketch already has."""
        self._widgets = []          # widgets die if only their axes hold them
        self.buttons, self.accents, self.lit = {}, {}, {}

        # Row one: the toggles and one-shots, in the order the help text lists
        # them, sized to their labels so the row fills the width evenly.
        left, right, gap, h, row = 0.045, 0.968, 0.011, 0.032, 0.104
        weights = [len(label) + 3 for label, _, _ in self.ACTIONS]
        free = (right - left) - gap * (len(self.ACTIONS) - 1)
        x = left
        for (label, key, accent), weight in zip(self.ACTIONS, weights):
            w = free * weight / sum(weights)
            # STOP wears its warning at rest: it is the one to hit blind.
            rest = mix(CRITICAL, SURFACE, 0.55) if key == "x" else CTRL
            self.buttons[key] = self._button([x, row, w, h], label, key, rest)
            self.accents[key] = accent
            self.lit[key] = None
            x += w + gap

        # Row two: nudge pad, then the target itself. Dragging the slider
        # streams goto at ~8 Hz, so the axis chases the handle as you move it.
        row, h = 0.060, 0.028
        pad = [("\u2212.25", "<"), ("\u2212.05", ","), ("\u2192 0", "goto 0\n"),
               ("+.05", "."), ("+.25", ">")]
        for i, (label, cmd) in enumerate(pad):
            self._button([left + i * 0.055, row, 0.050, h], label, cmd, CTRL)
        self.s_target = self._slider([0.395, row, 0.440, h], "target",
                                     -self.span, self.span, 0.0, "%+.3f turns",
                                     POS_C, 0.005)
        self.s_target.on_changed(lambda v: self._slide("goto %.4f\n", v))

        # Row three: how fast the loop is allowed to chase it, and a way in for
        # every command that did not earn a button.
        row, h = 0.016, 0.028
        self.s_vmax = self._slider([0.115, row, 0.240, h], "vmax", 0.05,
                                   VMAX_LIMIT, 0.5, "%.2f turns/s", RATE_C, 0.01)
        self.s_vmax.on_changed(lambda v: self._slide("vmax %.3f\n", v))

        ax = self.fig.add_axes([0.500, row, 0.330, h])
        self.cmd = TextBox(ax, "cmd", color=CTRL, hovercolor=CTRL_HOVER)
        self.cmd.label.set_color(MUTED)
        self.cmd.label.set_fontsize(9)
        self.cmd.text_disp.set_color(INK)
        self.cmd.text_disp.set_fontsize(9)
        self.cmd.cursor.set_color(INK)
        for side in ax.spines.values():
            side.set_color(AXIS)
        self.cmd.on_submit(self._on_cmd)
        self._widgets.append(self.cmd)
        self.fig.text(0.845, row + h / 2, "\u21b5 sends \u00b7 esc frees the keys",
                      color=MUTED, fontsize=7.5, va="center")

    def _button(self, rect, label, cmd, rest):
        ax = self.fig.add_axes(rect)
        b = Button(ax, label, color=rest, hovercolor=CTRL_HOVER)
        b.label.set_color(INK_2)
        b.label.set_fontsize(8.5)
        for side in ax.spines.values():
            side.set_color(AXIS)
        b.on_clicked(lambda _event, c=cmd: self._send(c))
        self._widgets.append(b)
        return b

    def _slider(self, rect, label, lo, hi, init, fmt, color, step):
        ax = self.fig.add_axes(rect, facecolor=SURFACE)
        s = Slider(ax, label, lo, hi, valinit=init, valfmt=fmt, valstep=step,
                   color=color, track_color=TRACK, initcolor="none",
                   handle_style=dict(facecolor=INK, edgecolor=AXIS, size=11))
        s.label.set_color(MUTED)
        s.label.set_fontsize(9)
        s.valtext.set_color(INK_2)
        s.valtext.set_fontsize(9)
        s.valtext.set_family("monospace")
        self._widgets.append(s)
        return s

    # ---- sending ---------------------------------------------------------
    def _send(self, text):
        self._sent_at = time.monotonic()
        try:
            self.source.send(text)
        except Exception as exc:  # port yanked mid-run
            self.note = f"send failed: {exc}"

    def _slide(self, fmt, value):
        """Slider moved. Rate-limit the wire; the rest is settled on release."""
        if self._echo:
            return
        if time.monotonic() - self._sent_at >= 0.12:
            self._queued = None
            self._send(fmt % value)
        else:
            self._queued = fmt % value

    def _on_release(self, _event):
        if self._queued is not None:
            cmd, self._queued = self._queued, None
            self._send(cmd)

    def _on_cmd(self, text):
        # A TextBox submits on the way out as well as on enter, so clicking off
        # it -- or hitting escape -- would fire whatever was half-typed at the
        # motor. Only a keystroke we saw ourselves counts as meaning it.
        entered, self._entered = self._entered, False
        text = text.strip()
        self.cmd.eventson = False       # set_val re-fires submit otherwise
        self.cmd.set_val("")
        self.cmd.cursor_index = 0
        self.cmd.eventson = True
        if not entered or not text:
            return
        # A bare number is a target on the board, but only an unsigned one --
        # and a leading '.' would be eaten as the nudge key. Spell it out.
        try:
            text = f"goto {float(text):g}"
        except ValueError:
            pass
        self._send(text + "\n")

    def _follow(self, slider, value):
        """Move a handle to the board's value without echoing it back."""
        v = min(max(value, slider.valmin), slider.valmax)
        if abs(v - slider.val) < 1e-4:
            return
        self._echo = True
        try:
            slider.set_val(v)
        finally:
            self._echo = False

    def _refresh_controls(self, s):
        """Light the toggles from the flags byte -- the board's word, not ours."""
        lit = {key: bool(s["flags"] & bit) for key, bit in self.LIT_BY_FLAG.items()}
        lit["p"] = self.paused
        for key, on in lit.items():
            if self.lit[key] == on:
                continue
            self.lit[key] = on
            b = self.buttons[key]
            fill = mix(self.accents[key], SURFACE, 0.40) if on else CTRL
            b.color = fill
            b.hovercolor = fill if on else CTRL_HOVER
            b.ax.set_facecolor(fill)
            b.label.set_color(INK if on else INK_2)

        # Follow the board while the user is not the one moving the handle, and
        # not so soon after a send that our own echo would fight the drag.
        if time.monotonic() - self._sent_at < 0.5:
            return
        if not self.s_target.drag_active:
            self._follow(self.s_target, s["target"])
        if self.vmax is not None and not self.s_vmax.drag_active:
            self._follow(self.s_vmax, self.vmax)

    # ---- redraw ----------------------------------------------------------
    HEADER_TRIES = 4
    HEADER_RETRY_S = 1.5

    def _chase_header(self):
        """Ask an already-running board to re-announce its columns.

        The banner is printed once at boot, so a scope started later never saw
        it. 'i' reprints it. A few tries covers a port that is not listening
        yet; a replay source swallows the send and falls back to LEGACY_COLUMNS.
        """
        if self.header_seen or self._header_tries >= self.HEADER_TRIES:
            return
        if time.monotonic() - self._header_asked < self.HEADER_RETRY_S:
            return
        self._header_asked = time.monotonic()
        self._header_tries += 1
        self._send("i\n")

    def update(self, _frame=None):
        # Drain first: on a normal boot the header is already in this batch, and
        # asking for one we are holding would only reprint the banner.
        self._drain()
        self._chase_header()
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
        bpos = list(self.bpos)[first:]

        self.line_pos.set_data(x, pos)
        self.line_target.set_data(x, target)
        self.line_bpos.set_data(x, bpos)
        self.line_err.set_data(x, err)
        self.line_rate.set_data(x, rate)
        self.line_slip.set_data(x, slip)
        self.ax_pos.set_xlim(-self.window, 0)
        b_live = bool(self.latest["flags"] & F_ENCB)
        self.line_bpos.set_visible(b_live)
        for artist in self.leg_b:
            artist.set_alpha(1.0 if b_live else 0.3)
        # B only earns a say in the shared scale while it is actually reporting,
        # or a dead wheel parked at zero would stretch the axis around nothing.
        self._fit(self.ax_pos, pos + target + (bpos if b_live else []), floor=0.05)
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
        self._update_dial(self.dial_a, s["pos"], s["enc"], s["agc"], s["status"],
                          live=True, target=s["target"])
        self._update_dial(self.dial_b, s["bpos"], s["benc"], s["bagc"],
                          s["bstatus"], live=b_live)

        f = s["flags"]
        chips = [("driver", f & F_DRIVER), ("loop", f & F_LOOP),
                 ("at target", f & F_AT), ("wiggle", f & F_WIGGLE)]
        self.state_txt.set_text("   ".join(
            f"{'●' if on else '○'} {name}" for name, on in chips))

        faulted = bool(f & F_FAULT)
        self.fault_dot.set_text("●")
        self.fault_dot.set_color(CRITICAL if faulted else GOOD)
        self.fault_txt.set_text("FAULT: slip" if faulted else "no fault")

        # Position, raw angle and magnet health live on the dials now; what is
        # left here is the servo, which is still wheel A alone -- plus what the
        # bit-banged bus is costing, the one number worth watching while wheel B
        # is new.
        bus = f"{s['busus']:>9} us" if b_live else f"{'--':>9}   "
        self.readout.set_text(
            f"target     {s['target']:>+9.4f} turns\n"
            f"error      {s['err']:>+9} counts ({s['err'] * 360.0 / COUNTS_PER_REV:+.2f}\N{DEGREE SIGN})\n"
            f"step rate  {s['rate']:>+9.0f} steps/s\n"
            f"steps      {s['steps']:>+9}\n"
            f"slip       {s['slip']:>+9} steps\n"
            f"speed A    {s['vel']:>+9.3f} turns/s\n"
            f"speed B    {s['bvel']:>+9.3f} turns/s\n"
            f"B soft bus {bus}  worst read\n"
            f"stream     {self._rate_hz():>9.1f} Hz  bad {self.bad_lines}"
        )
        self._refresh_controls(s)
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
    KEYS = set("elcdzfxwpih?,.<>")
    # Arrows are the nudge pad without the mouse: a turn of the wheel is far
    # enough that 0.05 and 0.25 are the two sizes worth having on one hand.
    ARROWS = {"left": ",", "right": ".", "down": "<", "up": ">",
              "shift+left": "<", "shift+right": ">", " ": "p"}

    def _on_key(self, event):
        # The cmd box owns the keyboard while it has focus, or every character
        # typed into it would also go down the wire as a command of its own.
        if getattr(self.cmd, "capturekeystrokes", False):
            self._entered = event.key in ("enter", "return")
            if event.key == "escape":
                self.cmd.stop_typing()   # discards the line, see _on_cmd
            return
        if event.key == "q":
            plt.close(self.fig)
            return
        key = self.ARROWS.get(event.key, event.key)
        if key not in self.KEYS:
            return
        self._send(key)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-p", "--port", default=DEFAULT_PORT)
    ap.add_argument("-b", "--baud", type=int, default=BAUD)
    ap.add_argument("-w", "--window", type=float, default=10.0,
                    help="seconds of history on the strip charts (default 10)")
    ap.add_argument("--span", type=float, default=3.0,
                    help="target slider reach in output turns (default +/-3)")
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

    scope = Scope(source, window=args.window, span=args.span)
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
