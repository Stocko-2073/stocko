"""Domain randomization for what we don't know about the robot yet.

Every span is drawn per episode, and per servo where it applies. `scale`
shrinks every span toward its nominal value: 0 is the nominal robot, 1 the full
spread. The dr_curriculum term raises it as training progresses.

Measure what you can and narrow the span: a randomized parameter costs policy
performance, a wrong nominal costs sim2real.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
import math

import torch

from mjlab.envs.mdp import dr
from mjlab.managers.event_manager import RecomputeLevel, requires_model_fields
from mjlab.managers.scene_entity_config import SceneEntityCfg

from phone_girl.link import servos


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


@requires_model_fields("body_mass", "body_ipos", "body_inertia", "body_iquat", "dof_armature",
                       recompute=RecomputeLevel.set_const)
def randomize_body(env, env_ids: torch.Tensor | None, randomization: Randomization) -> None:
    """Reset event: link density (mass and inertia together), the torso's CoM, servo armature."""
    scale = randomization.scale
    # pseudo_inertia scales mass and inertia by exp(2 alpha) and shifts the CoM by t.
    alpha = lambda span: tuple(math.log(v) / 2 for v in span.bounds(scale))
    links = SceneEntityCfg("robot", body_names=(r"(?!torso$).*",))
    torso = SceneEntityCfg("robot", body_names=("torso",))
    for cfg in (links, torso):
        cfg.resolve(env.scene)
    dr.pseudo_inertia(env, env_ids, alpha_range=alpha(randomization.link_mass), asset_cfg=links)
    dr.pseudo_inertia(env, env_ids, alpha_range=alpha(randomization.torso_mass),
                      t_range=randomization.torso_com.bounds(scale), asset_cfg=torso)
    dr.joint_armature(env, env_ids, operation="scale", ranges={".*": randomization.armature.bounds(scale)})


@requires_model_fields("geom_friction")
def randomize_friction(env, env_ids: torch.Tensor | None, randomization: Randomization) -> None:
    """Reset event: one floor friction per episode at both tips, another for falls."""
    scale = randomization.scale
    dr.geom_friction(env, env_ids, operation="abs", axes=[0], shared_random=True,
                     ranges={"(left|right)_foot": randomization.foot_friction.bounds(scale)})
    dr.geom_friction(env, env_ids, operation="abs", axes=[0], shared_random=True,
                     ranges={".*_[0-9]+": randomization.body_friction.bounds(scale)})


def dr_curriculum(env, env_ids, start: float, steps: int, terms: tuple[str, ...]) -> float:
    """Curriculum term: widen every randomization span from `start` to 1 over `steps` env steps."""
    del env_ids
    scale = min(1.0, start + (1.0 - start) * env.common_step_counter / steps)
    for name in terms:
        env.event_manager.get_term_cfg(name).params["randomization"].scale = scale
    return scale
