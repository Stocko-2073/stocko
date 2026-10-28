"""The assembled environment: resets, command timing, stalls and randomization."""

import pytest
import torch

from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg

from phone_girl.robot import FEET, FOOT_GEOMS, FOOT_SITES, HOME, JOINTS
from phone_girl.xl330 import Xl330Actuator


def make(scale: float = 0.0, envs: int = 2, **link) -> ManagerBasedRlEnv:
    cfg = load_env_cfg("PhoneGirl-Stand", play=True)
    cfg.scene.num_envs = envs
    for name in ("servos", "supply", "body", "friction"):
        cfg.events[name].params["randomization"].scale = scale
    for key, value in dict(stall_rate_hz=0.0, late_probability=0.0, **link).items():
        setattr(cfg.events["late_commands"].params["link"], key, value)
    env = ManagerBasedRlEnv(cfg, device="cpu")
    env.reset()
    return env


def test_reset_starts_the_servos_at_home():
    """No goal-step jerk or supply sag at the start of an episode."""
    env = make()
    actuator = env.scene["robot"].actuators[0]
    home = torch.tensor([HOME[j] for j in JOINTS])
    torch.testing.assert_close(env.scene["robot"].data.joint_pos_target[0], home)
    env.step(torch.zeros(2, len(JOINTS)))
    assert actuator.current.abs().max() < 0.2 and actuator.bus_voltage.min() > 7.25
    env.close()


def test_commands_reach_the_servos_one_interval_later():
    """A new goal takes command_lag physics steps (a 15 ms interval plus the bus write) to land."""
    env = make()
    actuator = env.scene["robot"].actuators[0]
    targets = []
    original = Xl330Actuator.compute

    def record(self, cmd):
        targets.append(cmd.position_target[0, 0].item())
        return original(self, cmd)

    Xl330Actuator.compute = record
    try:
        env.step(torch.zeros(2, len(JOINTS)))
        targets.clear()
        action = torch.zeros(2, len(JOINTS))
        action[:, 0] = 1.0  # waist
        env.step(action)
        env.step(action)
    finally:
        Xl330Actuator.compute = original
    lag = int(actuator.command_lag[0])
    assert 6 <= lag <= 8
    moved = next(i for i, t in enumerate(targets) if abs(t - HOME["waist"]) > 1e-6)
    assert moved == lag
    env.close()


def test_a_stall_holds_the_last_goal():
    env = make()
    actuator = env.scene["robot"].actuators[0]
    env.step(torch.zeros(2, len(JOINTS)))
    actuator.stall[:] = 100
    action = torch.ones(2, len(JOINTS))
    for _ in range(3):
        env.step(action)
    torch.testing.assert_close(actuator._held[0], torch.tensor([HOME[j] for j in JOINTS]))
    env.close()


def test_randomization_spans_and_curriculum():
    env = make(scale=1.0, envs=64)
    actuator = env.scene["robot"].actuators[0]
    spans = env.event_manager.get_term_cfg("servos").params["randomization"]
    ratio = actuator.kt / actuator.nominal["kt"]
    assert spans.kt.low - 1e-6 <= ratio.min() and ratio.max() <= spans.kt.high + 1e-6
    assert ratio.std() > 0.01  # every servo draws its own
    assert spans.supply_voltage.low <= actuator.supply_voltage.min() <= actuator.supply_voltage.max() <= 8.4
    low, high = spans.supply_voltage.bounds(0.5)
    assert (low, high) == pytest.approx((7.0, 7.9))
    env.close()


def test_cached_foot_indices_name_the_feet():
    """Rewards index the feet with tensors built once; they must be the entity's own ids."""
    env = make()
    robot = env.scene["robot"]
    assert [robot.site_names[i] for i in FOOT_SITES] == list(FEET)
    assert [robot.geom_names[i] for i in FOOT_GEOMS] == list(FEET)
    env.close()
