"""The SG90 in MuJoCo.

Mechanics live in the MJCF: a motor-side hinge carrying the reflected rotor
inertia, the gear friction and the motor; nested on it, an output hinge
carrying the horn and its load. The output hinge's angle is the deflection
across the gear mesh, and a fixed tendon on it is a spring with a dead band:
backlash, then tooth compliance. Everything that isn't rigid-body mechanics runs
once per physics step in Python, the way BAM's adapter does it:

- the control IC, an analog M51660L-style servo chip (KC8801A in the unit on the
  bench): at the end of each input pulse it compares the pulse with one
  generated from the pot and drives the motor at full voltage for a burst
  proportional to the difference, and not at all inside the dead band;
- the H-bridge: supply minus its drop while driving, then braking (motor
  shorted) or coasting (motor floating) between bursts;
- the DC motor and the supply's resistance, as a MuJoCo `general` actuator whose
  gain and velocity bias follow the bridge state, so the back-EMF damping is
  integrated implicitly;
- gear friction that depends on speed (Stribeck) and on the torque the mesh
  carries, written into ``dof_frictionloss`` each step from the last step's
  state, MuJoCo's constraint solver then resolving stiction.

The defaults are nominal SG90 guesses consistent with the datasheet (0.18 N m
stall, 10.5 rad/s no-load at 4.8 V) with a 60 % efficient gearbox. With the
bridge coasting between bursts, the reflected rotor inertia carries the output
well past its target and the loop hunts, which real SG90s don't do, so the
default brakes until the motor taps show what the KC8801A really does. The bench
fits replace all of them.
"""

from dataclasses import asdict, dataclass

import mujoco
import numpy as np

AS5600_TAU = 0.15e-3     # 2x slow filter, ~0.286 ms to settle, as a first-order lag
INA219_WINDOW = 532e-6   # 12-bit conversion: a box-car average this long
QUIESCENT_A = 0.0043     # KC8801 listing (the bench unit has a KC8801A): 4.3 mA with the output open


@dataclass
class Params:
    # Control IC. Reference pulse from the pot: center + a1 th + a2 th^2 + a3 th^3 (us, th in rad).
    center_us: float = 1500.0
    us_per_rad: float = 2000.0 / np.pi
    us_per_rad2: float = 0.0
    us_per_rad3: float = 0.0
    deadband_us: float = 5.0
    gain: float = 120.0            # burst us per us of error past the dead band
    max_burst_us: float = 30000.0  # the stretcher's longest burst
    latency_us: float = 100.0      # pulse end to burst start
    brake: bool = True             # bridge between bursts: shorted (True) or floating
    # Motor, bridge and supply
    gear_ratio: float = 300.0
    kt: float = 1.45e-3            # N m/A, equal to the back-EMF constant in V s/rad
    resistance: float = 7.0        # winding plus brushes, ohm
    rotor_inertia: float = 4.4e-9  # kg m^2 at the motor; armature = N^2 times this
    bridge_drop: float = 0.3       # V lost across the bridge while driving
    supply_v: float = 5.0
    supply_r: float = 0.05         # ohm between the regulator and the servo
    # Gear friction, at the output
    coulomb: float = 0.010         # N m
    static: float = 0.015          # N m, at standstill
    stribeck_vel: float = 0.5      # rad/s
    viscous: float = 0.001         # N m s/rad
    load_friction: float = 0.4     # fraction of the mesh torque lost to friction
    # Backlash and tooth compliance
    backlash: float = np.radians(0.5)   # full width, rad
    mesh_stiffness: float = 10.0        # N m/rad once the gap closes
    mesh_damping: float = 0.002         # N m s/rad

    @property
    def armature(self):
        return self.gear_ratio**2 * self.rotor_inertia

    def reference_us(self, th):
        return self.center_us + th * (self.us_per_rad + th * (self.us_per_rad2 + th * self.us_per_rad3))


@dataclass
class Fixture:
    """What hangs on the horn: hub, arm, masses and the horn itself."""
    mass: float = 0.012            # kg
    com: float = 0.02              # m from the axis; the arm hangs straight down at angle 0
    inertia: float = 1.2e-5        # kg m^2 about the axis, everything included
    gravity: bool = True           # axis horizontal (pendulum) or vertical


def mjcf(params, fixture, timestep=2.5e-4):
    p, f = params, fixture
    i_com = f.inertia - f.mass * f.com**2
    if i_com <= 0:
        raise ValueError("fixture inertia is less than its mass at its COM radius")
    g = "0 0 -9.81" if f.gravity else "0 0 0"
    return f"""
<mujoco model="sg90">
  <option timestep="{timestep}" integrator="implicitfast" gravity="{g}"/>
  <worldbody>
    <body name="gear">
      <inertial pos="0 0 0" mass="1e-4" diaginertia="1e-10 1e-10 1e-10"/>
      <joint name="motor" type="hinge" axis="0 1 0" armature="{p.armature}" damping="{p.viscous}"
             frictionloss="{p.static}" solimpfriction="0.99 0.999 0.001" solreffriction="{2 * timestep} 1"/>
      <body name="horn">
        <inertial pos="0 0 {-f.com}" mass="{f.mass}" diaginertia="{i_com} {i_com} {i_com}"/>
        <joint name="output" type="hinge" axis="0 1 0"/>
      </body>
    </body>
  </worldbody>
  <tendon>
    <fixed name="mesh" stiffness="{p.mesh_stiffness}" damping="{p.mesh_damping}"
           springlength="{-p.backlash / 2} {p.backlash / 2}">
      <joint joint="output" coef="1"/>
    </fixed>
  </tendon>
  <actuator>
    <general name="motor" joint="motor" gainprm="1" biastype="affine" biasprm="0 0 0"/>
  </actuator>
</mujoco>"""


class Servo:
    """The per-step half of the model, for one servo in a MuJoCo model built
    from :func:`mjcf`. Call :meth:`pulse` at each frame start and :meth:`step`
    before every ``mj_step``."""

    def __init__(self, model, data, params, joint_motor="motor", joint_output="output",
                 actuator="motor", tendon="mesh"):
        self.model, self.data, self.p = model, data, params
        jm, jo = model.joint(joint_motor).id, model.joint(joint_output).id
        self.dof_m, self.qpos_m = model.jnt_dofadr[jm], model.jnt_qposadr[jm]
        self.qpos_o = model.jnt_qposadr[jo]
        self.act = model.actuator(actuator).id
        self.ten = model.tendon(tendon).id
        self.burst_start = self.burst_end = -1.0
        self.burst_sign = 0.0
        self.pending = None
        self.current = 0.0
        self.terminal_v = 0.0
        self.driving = False

    @property
    def output_angle(self):
        """The horn's angle: the gear's plus the deflection across the mesh."""
        return float(self.data.qpos[self.qpos_m] + self.data.qpos[self.qpos_o])

    def pulse(self, t, width_us):
        """A pulse starting at time t. The IC compares it with the pot when it
        ends, so the decision waits until then (see :meth:`step`)."""
        if width_us > 0:
            self.pending = (t + width_us * 1e-6, width_us)

    def _decide(self, t, width_us):
        p = self.p
        err = width_us - p.reference_us(self.output_angle)
        over = abs(err) - p.deadband_us
        if over <= 0:
            return
        start = t + p.latency_us * 1e-6
        self.burst_start = start
        self.burst_end = start + min(p.gain * over, p.max_burst_us) * 1e-6
        self.burst_sign = float(np.sign(err))

    def update_friction(self):
        p, d = self.p, self.data
        omega = d.qvel[self.dof_m]
        gap = abs(d.ten_length[self.ten]) - p.backlash / 2
        mesh_torque = p.mesh_stiffness * gap if gap > 0 else 0.0
        stribeck = p.coulomb + (p.static - p.coulomb) * np.exp(-(omega / p.stribeck_vel) ** 2)
        self.model.dof_frictionloss[self.dof_m] = stribeck + p.load_friction * mesh_torque

    def step(self):
        p, m, d = self.p, self.model, self.data
        t = d.time
        if self.pending is not None and t >= self.pending[0]:
            self._decide(*self.pending)
            self.pending = None

        nkt = p.gear_ratio * p.kt
        self.driving = self.burst_start <= t < self.burst_end
        emf = nkt * d.qvel[self.dof_m]       # the motor joint's speed is in output units
        if self.driving:
            r = p.resistance + p.supply_r
            v = self.burst_sign * (p.supply_v - p.bridge_drop)
            m.actuator_gainprm[self.act, 0] = nkt / r
            m.actuator_biasprm[self.act, 2] = -nkt**2 / r
            d.ctrl[self.act] = v
            self.current = (v - emf) / r
            self.terminal_v = v - self.burst_sign * abs(self.current) * p.supply_r
        else:
            m.actuator_gainprm[self.act, 0] = nkt / p.resistance
            m.actuator_biasprm[self.act, 2] = -nkt**2 / p.resistance if p.brake else 0.0
            d.ctrl[self.act] = 0.0
            self.current = -emf / p.resistance if p.brake else 0.0
            self.terminal_v = 0.0 if p.brake else emf
        self.update_friction()

    @property
    def supply_current(self):
        """What the INA219 sees: the motor's current while driving, plus the IC's own."""
        return (abs(self.current) if self.driving else 0.0) + QUIESCENT_A


def build(params, fixture, timestep=2.5e-4):
    model = mujoco.MjModel.from_xml_string(mjcf(params, fixture, timestep))
    return model, mujoco.MjData(model)


def _start(params, fixture, theta0, timestep):
    model, data = build(params, fixture, timestep)
    servo = Servo(model, data, params)
    data.qpos[servo.qpos_m] = theta0
    mujoco.mj_forward(model, data)
    return model, data, servo


def simulate(params, fixture, widths, frame_us=20000, theta0=0.0, timestep=2.5e-4,
             sample_dt=5e-4, tail_s=0.0):
    """Closed loop: one pulse width per frame in (0 = no pulse), bench-like traces out.

    Returns arrays sampled every ``sample_dt``: ``t``; ``angle`` (the horn);
    ``as5600`` (the same through the encoder's filter); ``current`` (supply
    current averaged like the INA219); ``terminal_v`` (motor terminals, A - B);
    ``drive`` (-1, 0 or 1).
    """
    model, data, servo = _start(params, fixture, theta0, timestep)
    frame_s = frame_us * 1e-6
    widths = np.asarray(widths, float)
    n_steps = int(round((len(widths) * frame_s + tail_s) / timestep))
    every = max(1, int(round(sample_dt / timestep)))
    alpha = timestep / (AS5600_TAU + timestep)
    recent = np.zeros(max(1, int(round(INA219_WINDOW / timestep))))
    enc = servo.output_angle
    rows = []
    frame = 0
    for k in range(n_steps):
        while frame < len(widths) and data.time >= frame * frame_s - 1e-12:
            servo.pulse(frame * frame_s, widths[frame])
            frame += 1
        servo.step()
        mujoco.mj_step(model, data)
        enc += alpha * (servo.output_angle - enc)
        recent[k % len(recent)] = servo.supply_current
        if k % every == 0:
            rows.append((data.time, servo.output_angle, enc, recent.mean(), servo.terminal_v,
                         servo.burst_sign if servo.driving else 0.0))
    return dict(zip(("t", "angle", "as5600", "current", "terminal_v", "drive"), np.array(rows).T))


def simulate_voltage(params, fixture, t, motor_v, theta0=0.0, timestep=2.5e-4):
    """Open loop: a measured motor terminal voltage drives the model directly,
    with no control IC. Torque is G (V - emf), which holds whatever the bridge
    was doing: while it drives, V is the applied voltage; when it brakes, V is
    about zero; when it floats, V is the back-EMF and the torque comes out zero.
    Returns the horn angle at the times ``t``."""
    model, data, servo = _start(params, fixture, theta0, timestep)
    nkt = params.gear_ratio * params.kt
    model.actuator_gainprm[servo.act, 0] = nkt / params.resistance
    model.actuator_biasprm[servo.act, 2] = -nkt**2 / params.resistance
    t = np.asarray(t, float)
    v = np.asarray(motor_v, float)
    angle = np.empty(len(t))
    for k, tk in enumerate(t):
        while data.time < tk - 1e-12:
            data.ctrl[servo.act] = np.interp(data.time, t, v)
            servo.update_friction()
            mujoco.mj_step(model, data)
        angle[k] = servo.output_angle
    return angle


def as_dict(params):
    return {k: (bool(v) if isinstance(v, (bool, np.bool_)) else float(v)) for k, v in asdict(params).items()}
