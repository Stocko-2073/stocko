"""Domain randomization for what we don't know about the robot yet.

Every span is drawn per episode, and per servo where it applies. `scale`
shrinks every span toward its nominal value: 0 is the nominal robot, 1 the full
spread. The dr_curriculum term raises it as training progresses.

Measure what you can and narrow the span: a randomized parameter costs policy
performance, a wrong nominal costs sim2real.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
import gc
import math

import torch
import warp as wp

from mjlab.managers.event_manager import RecomputeLevel, requires_model_fields

from phone_girl.link import servos
from phone_girl.robot import BODY_GEOMS, FOOT_GEOMS, index


@dataclass
class Span:
    low: float
    high: float
    nominal: float

    def bounds(self, scale: float) -> tuple[float, float]:
        return (self.nominal + scale * (self.low - self.nominal), self.nominal + scale * (self.high - self.nominal))

    def sample(self, shape, scale: float, device) -> torch.Tensor:
        low, high = self.bounds(scale)
        return low + (high - low) * torch.rand(shape, device=device)


def _span(low, high, nominal):
    return field(default_factory=lambda: Span(low, high, nominal))


@dataclass
class Randomization:
    scale: float = 1.0
    # Contact. The stilt tips are PETG; floors run from polished to carpet.
    foot_friction: Span = _span(0.25, 1.2, 0.6)
    body_friction: Span = _span(0.3, 1.0, 0.6)
    # Battery: two 18650s in series straight to the servos, open circuit from
    # 3.3 to 4.2 V a cell. That is above the XL330's 6 V rating, as in BAM's own
    # XL330 identification (7.5 V). Then the cells' and wiring's resistance.
    supply_voltage: Span = _span(6.6, 8.4, 7.4)
    supply_resistance: Span = _span(0.05, 0.3, 0.15)
    idle_current: Span = _span(0.25, 0.6, 0.4)  # A: MCU, radio, servo electronics
    # Servos, as factors on BAM's identified XL330 values, per servo.
    kt: Span = _span(0.92, 1.08, 1.0)
    resistance: Span = _span(0.9, 1.3, 1.0)  # unit spread and a warm winding
    friction: Span = _span(0.7, 1.5, 1.0)
    viscous: Span = _span(0.6, 1.6, 1.0)
    gain: Span = _span(0.9, 1.1, 1.0)  # Kp-to-duty scaling, measured not documented
    max_current: Span = _span(0.9, 1.1, 1.0)
    armature: Span = _span(0.85, 1.15, 1.0)
    encoder_offset: Span = _span(-0.02, 0.02, 0.0)  # rad: horn spline and calibration
    # Mass. The torso carries the phone (weighed) and the unweighed wiring and
    # electronics, so it can only get heavier than modelled by much.
    link_mass: Span = _span(0.9, 1.1, 1.0)
    torso_mass: Span = _span(0.97, 1.12, 1.0)
    torso_com: Span = _span(-0.006, 0.006, 0.0)  # m per axis

    def spans(self) -> dict[str, Span]:
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != "scale"}


SERVO_FACTORS = {"kt": "kt", "resistance": "resistance", "friction": "friction_scale",
                 "viscous": "viscous_scale", "gain": "kp", "max_current": "max_current"}


def randomize_servos(env, env_ids: torch.Tensor | None, randomization: Randomization) -> None:
    """Reset event: per-servo motor, friction and gain factors, and encoder offsets."""
    actuator = servos(env)
    ids = torch.arange(env.num_envs, device=env.device) if env_ids is None else env_ids
    shape = (len(ids), len(actuator.target_names))
    scale = randomization.scale
    for name, attribute in SERVO_FACTORS.items():
        factor = getattr(randomization, name).sample(shape, scale, env.device)
        getattr(actuator, attribute)[ids] = actuator.nominal[attribute][ids] * factor
    robot = env.scene["robot"]
    robot.data.encoder_bias[ids[:, None], actuator.target_ids] = \
        randomization.encoder_offset.sample(shape, scale, env.device)


def randomize_supply(env, env_ids: torch.Tensor | None, randomization: Randomization) -> None:
    """Reset event: battery charge, its resistance and the electronics' idle draw."""
    actuator = servos(env)
    ids = torch.arange(env.num_envs, device=env.device) if env_ids is None else env_ids
    scale = randomization.scale
    actuator.supply_voltage[ids] = randomization.supply_voltage.sample(len(ids), scale, env.device)
    actuator.supply_resistance[ids] = randomization.supply_resistance.sample(len(ids), scale, env.device)
    actuator.idle_current[ids] = randomization.idle_current.sample(len(ids), scale, env.device)
    actuator.bus_voltage[ids] = actuator.supply_voltage[ids]


@requires_model_fields("body_mass", "body_ipos", "body_inertia", "dof_armature",
                       recompute=RecomputeLevel.set_const_fixed)
def randomize_body(env, env_ids: torch.Tensor | None, randomization: Randomization) -> None:
    """Reset event: link density (mass and inertia together), the torso's CoM, servo armature.

    This is dr.pseudo_inertia (Rucker & Wensing) with only its density (alpha)
    and CoM-shift (t) parameters, in closed form. Scaling density by s scales
    mass and inertia by s and leaves the CoM and principal axes alone. Moving the
    mass by t moves the CoM by t and leaves the inertia about it alone. That is
    a few kernels where the general form launches about a thousand, and the
    event runs on every step that resets an episode.

    mjlab then recomputes body_subtreemass, which subtree_com divides by. The
    other constants that depend on mass and armature, the constraints'
    regularization weights and the solver's mean inertia, wait for
    refresh_constants. Recomputing them takes the full set_const over every
    world, about 11 ms a step at 16k worlds, when only the few that reset changed.
    """
    scale = randomization.scale
    ids = torch.arange(env.num_envs, device=env.device) if env_ids is None else env_ids
    bodies = env.scene["robot"].indexing.body_ids  # the torso first
    dofs = servos(env).dof_ids
    model, default = env.sim.model, env.sim.get_default_field

    def density(span: Span, shape) -> torch.Tensor:
        # exp(2 alpha) with alpha uniform, as pseudo_inertia draws it
        low, high = (math.log(v) for v in span.bounds(scale))
        return torch.exp(low + (high - low) * torch.rand(shape, device=env.device))

    n = len(ids)
    s = torch.cat([density(randomization.torso_mass, (n, 1)), density(randomization.link_mass, (n, len(bodies) - 1))], 1)
    rows = ids[:, None]
    model.body_mass[rows, bodies] = default("body_mass")[bodies] * s
    model.body_inertia[rows, bodies] = default("body_inertia")[bodies] * s[..., None]
    model.body_ipos[ids, bodies[0]] = default("body_ipos")[bodies[0]] + \
        randomization.torso_com.sample((n, 3), scale, env.device)
    model.dof_armature[rows, dofs] = default("dof_armature")[dofs] * \
        randomization.armature.sample((n, len(dofs)), scale, env.device)


def refresh_constants(env, env_ids, every: int) -> None:
    """Step event: the full set_const every `every` steps, for what randomize_body leaves stale."""
    del env_ids
    if env.common_step_counter % every == 0:
        env.sim.recompute_constants(RecomputeLevel.set_const)


def graph_recompute(env, env_ids=None) -> None:
    """Startup event: replay mjlab's recompute_constants from CUDA graphs.

    After randomize_body changes masses, mjlab runs MuJoCo Warp's set_const, on
    every step that resets an episode. It loops over DOFs and bodies in Python,
    about 560 kernel launches. Each level is captured on first use, once the
    model's fields are final, and replayed as one launch after that.
    """
    del env_ids
    sim = env.sim
    if not sim.use_cuda_graph:
        return
    uncaptured, graphs = sim.recompute_constants, {}

    def recompute(level: RecomputeLevel) -> None:
        with wp.ScopedDevice(sim.wp_device):
            if level not in graphs:
                # As mjlab captures its own graphs: a garbage collection during
                # capture would record stale graphs' destructors into this one.
                collecting = gc.isenabled()
                gc.disable()
                try:
                    with wp.ScopedCapture() as capture:
                        uncaptured(level)
                finally:
                    if collecting:
                        gc.enable()
                graphs[level] = capture.graph
            wp.capture_launch(graphs[level])

    sim.recompute_constants = recompute


@requires_model_fields("geom_friction")
def randomize_friction(env, env_ids: torch.Tensor | None, randomization: Randomization) -> None:
    """Reset event: one floor friction per episode at both tips, another for falls."""
    ids = torch.arange(env.num_envs, device=env.device) if env_ids is None else env_ids
    geoms = env.scene["robot"].indexing.geom_ids
    for local, span in ((FOOT_GEOMS, randomization.foot_friction), (BODY_GEOMS, randomization.body_friction)):
        env.sim.model.geom_friction[ids[:, None], geoms[index(local, env.device)], 0] = \
            span.sample((len(ids), 1), randomization.scale, env.device)


def dr_curriculum(env, env_ids, start: float, steps: int, terms: tuple[str, ...]) -> float:
    """Curriculum term: widen every randomization span from `start` to 1 over `steps` env steps."""
    del env_ids
    scale = min(1.0, start + (1.0 - start) * env.common_step_counter / steps)
    for name in terms:
        env.event_manager.get_term_cfg(name).params["randomization"].scale = scale
    return scale
