"""Pulse schedules for the bench experiments (E2-E6 in the plan).

Each experiment is designed as a commanded angle per frame, then turned into
pulse widths through a PulseMap. Until the static map (E2) has measured the
real one, the map is the nominal SG90 one: 1500 us at center, 500-2500 us over
180 degrees, with the angle measured from the arm hanging straight down.
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class PulseMap:
    center_us: float = 1500.0
    us_per_deg: float = 2000.0 / 180.0
    lo_us: int = 600
    hi_us: int = 2400

    def widths(self, deg):
        w = np.rint(self.center_us + np.asarray(deg, float) * self.us_per_deg)
        if w.size and (w.min() < self.lo_us or w.max() > self.hi_us):
            raise ValueError(f"schedule needs {w.min():.0f}-{w.max():.0f} us, "
                             f"outside the {self.lo_us}-{self.hi_us} us limits")
        return w.astype(np.uint16)

    @property
    def max_deg(self):
        return min(self.hi_us - self.center_us, self.center_us - self.lo_us) / self.us_per_deg


@dataclass
class Experiment:
    name: str
    widths: np.ndarray
    frame_us: int = 20000
    end_us: int | None = None
    raw_taps: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def seconds(self):
        return len(self.widths) * self.frame_us / 1e6


def _frames(seconds, frame_us):
    return max(1, int(round(seconds * 1e6 / frame_us)))


def _hold(deg, seconds, frame_us):
    return np.full(_frames(seconds, frame_us), float(deg))


def _ramp(a, b, speed_dps, frame_us):
    n = max(1, int(np.ceil(abs(b - a) / speed_dps * 1e6 / frame_us)))
    return np.linspace(a, b, n + 1)[1:]


def static_map(pm, frame_us=20000, step_us=10, dwell_s=0.5):
    """E2. Pulse width up from the low limit to the high one and back, holding
    each level, so the settled angles trace the map and its hysteresis."""
    up = np.arange(pm.lo_us, pm.hi_us + 1, step_us)
    levels = np.concatenate([np.full(3, pm.lo_us), up, up[::-1]])
    n = _frames(dwell_s, frame_us)
    return Experiment("static-map", np.repeat(levels, n).astype(np.uint16), frame_us,
                      meta=dict(levels_us=levels.tolist(), dwell_frames=n, step_us=step_us))


def steps(pm, frame_us=20000, amplitudes_deg=(0.5, 1, 2, 5, 10, 20, 45, 90, 150),
          starts_deg=(-45, 0, 45), dwell_s=0.8, seed=0):
    """E3. Steps of each size in both directions from a few start angles, in
    shuffled order, each held long enough to settle."""
    pairs = []
    for a in amplitudes_deg:
        for d in (1, -1):
            fits = [s for s in starts_deg if abs(s) <= pm.max_deg and abs(s + d * a) <= pm.max_deg]
            if not fits and a <= 2 * pm.max_deg:
                fits = [-d * a / 2]
            pairs += [(float(s), float(s + d * a)) for s in fits]
    order = np.random.default_rng(seed).permutation(len(pairs))
    pairs = [pairs[i] for i in order]
    deg, marks = [], []
    for s, e in pairs:
        marks.append(dict(frame=sum(len(x) for x in deg), start_deg=s, end_deg=e))
        deg += [_hold(s, dwell_s, frame_us), _hold(e, dwell_s, frame_us)]
    return Experiment("steps", pm.widths(np.concatenate(deg)), frame_us,
                      meta=dict(steps=marks, dwell_s=dwell_s, seed=seed))


def sines(pm, frame_us=20000, freqs_hz=(0.2, 0.5, 1, 2, 3, 5), amps_deg=(5, 20, 60),
          cycles=4, max_speed_dps=900, gap_s=0.5):
    """E4. Sine segments about the hanging position. Combinations whose peak
    speed is far beyond what the servo can do are skipped."""
    deg, segments = [_hold(0, gap_s, frame_us)], []
    for a in amps_deg:
        for f in freqs_hz:
            if 2 * np.pi * f * a > max_speed_dps or a > pm.max_deg:
                continue
            t = np.arange(_frames(cycles / f, frame_us)) * frame_us / 1e6
            segments.append(dict(frame=sum(len(x) for x in deg), freq_hz=f, amp_deg=a))
            deg += [a * np.sin(2 * np.pi * f * t), _hold(0, gap_s, frame_us)]
    return Experiment("sines", pm.widths(np.concatenate(deg)), frame_us, meta=dict(segments=segments))


def chirp(pm, frame_us=20000, f0_hz=0.1, f1_hz=4.0, amp_deg=15, seconds=40):
    """E4. Logarithmic chirp: equal time per octave."""
    t = np.arange(_frames(seconds, frame_us)) * frame_us / 1e6
    k = np.log(f1_hz / f0_hz)
    phase = 2 * np.pi * f0_hz * seconds / k * (np.exp(k * t / seconds) - 1)
    deg = np.concatenate([_hold(0, 0.5, frame_us), amp_deg * np.sin(phase), _hold(0, 0.5, frame_us)])
    return Experiment("chirp", pm.widths(deg), frame_us,
                      meta=dict(f0_hz=f0_hz, f1_hz=f1_hz, amp_deg=amp_deg, seconds=seconds))


def multisine(pm, frame_us=20000, f_max_hz=4.0, rms_deg=12, seconds=40, seed=0):
    """E4. Random-phase multisine: equal power at every multiple of 1/seconds up
    to f_max, scaled to the requested RMS (and down if a peak would leave range)."""
    t = np.arange(_frames(seconds, frame_us)) * frame_us / 1e6
    freqs = np.arange(1, int(f_max_hz * seconds) + 1) / seconds
    phases = np.random.default_rng(seed).uniform(0, 2 * np.pi, len(freqs))
    x = np.sin(2 * np.pi * freqs[:, None] * t + phases[:, None]).sum(0)
    x *= rms_deg / x.std()
    x *= min(1.0, 0.95 * pm.max_deg / np.abs(x).max())
    x *= np.clip(np.minimum(t, seconds - t) / 0.5, 0, 1)   # fade in and out over 0.5 s
    deg = np.concatenate([_hold(0, 0.5, frame_us), x, _hold(0, 0.5, frame_us)])
    return Experiment("multisine", pm.widths(deg), frame_us,
                      meta=dict(f_max_hz=f_max_hz, rms_deg=float(x.std()), seconds=seconds, seed=seed))


def up_and_down(pm, frame_us=20000, speeds_dps=(20, 50, 100, 200, 400), lo_deg=-60, hi_deg=60, dwell_s=0.5):
    """E4. Constant-speed sweeps between two angles, both ways, at several speeds:
    friction against speed, with the pendulum's gravity torque changing along the way."""
    deg, segments = [_hold(lo_deg, dwell_s, frame_us)], []
    for v in speeds_dps:
        segments.append(dict(frame=sum(len(x) for x in deg), speed_dps=v))
        deg += [_ramp(lo_deg, hi_deg, v, frame_us), _hold(hi_deg, dwell_s, frame_us),
                _ramp(hi_deg, lo_deg, v, frame_us), _hold(lo_deg, dwell_s, frame_us)]
    return Experiment("up-and-down", pm.widths(np.concatenate(deg)), frame_us,
                      meta=dict(segments=segments, lo_deg=lo_deg, hi_deg=hi_deg))


def lift_and_drop(pm, frame_us=20000, lifts_deg=(30, 60, 80, -30, -60, -80), limp_s=0.8,
                  hold_s=1.0, catch_s=1.5, speed_dps=120):
    """E4. Raise the pendulum, stop the pulses so the servo goes limp and the
    load falls, backdriving the gearbox, then resume at the hanging position.
    Width 0 frames carry no pulse."""
    deg, segments = [_hold(0, hold_s, frame_us)], []
    for lift in lifts_deg:
        lift = float(np.clip(lift, -pm.max_deg, pm.max_deg))
        deg += [_ramp(0, lift, speed_dps, frame_us), _hold(lift, hold_s, frame_us)]
        segments.append(dict(frame=sum(len(x) for x in deg), lift_deg=lift))
        deg += [np.full(_frames(limp_s, frame_us), np.nan), _hold(0, catch_s, frame_us)]
    deg = np.concatenate(deg)
    limp = np.isnan(deg)
    widths = pm.widths(np.where(limp, 0, deg))
    widths[limp] = 0
    return Experiment("lift-and-drop", widths, frame_us,
                      meta=dict(segments=segments, limp_s=limp_s, speed_dps=speed_dps))


def hold(pm, frame_us=20000, angle_deg=80, seconds=60, check_every_s=10, check_deg=5):
    """E5. Hold near stall (load the arm so ``angle_deg`` is near horizontal),
    with a small check step every few seconds to see the response drift."""
    deg, t = [], 0.0
    while t < seconds:
        deg += [_hold(angle_deg, check_every_s - 0.6, frame_us),
                _hold(angle_deg - check_deg, 0.3, frame_us), _hold(angle_deg, 0.3, frame_us)]
        t += check_every_s
    return Experiment("hold", pm.widths(np.concatenate(deg)), frame_us,
                      meta=dict(angle_deg=angle_deg, check_every_s=check_every_s, check_deg=check_deg))


def reference(pm, frame_us=20000):
    """The drift check repeated between runs: 0, +20, 0, -20, 0 degrees, 1 s each."""
    deg = np.concatenate([_hold(a, 1.0, frame_us) for a in (0, 20, 0, -20, 0)])
    return Experiment("reference", pm.widths(deg), frame_us)


EXPERIMENTS = {
    "static-map": static_map,
    "steps": steps,
    "sines": sines,
    "chirp": chirp,
    "multisine": multisine,
    "up-and-down": up_and_down,
    "lift-and-drop": lift_and_drop,
    "hold": hold,
    "reference": reference,
}
