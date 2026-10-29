"""The assembled environment: resets, command timing, stalls and randomization."""

import pytest
import torch

from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg

from phone_girl import MJCF
from phone_girl.randomization import Randomization, randomize_body
from phone_girl.robot import BODY_GEOMS, FEET, FOOT_GEOMS, FOOT_SITES, HOME, JOINTS
from phone_girl.xl330 import Xl330Actuator


def make(scale: float = 0.0, envs: int = 2, device: str = "cpu", **link) -> ManagerBasedRlEnv:
    cfg = load_env_cfg("PhoneGirl-Stand", play=True)
    cfg.scene.num_envs = envs
    for name in ("servos", "supply", "body", "friction"):
        cfg.events[name].params["randomization"].scale = scale
    for key, value in dict(stall_rate_hz=0.0, late_probability=0.0, **link).items():
        setattr(cfg.events["late_commands"].params["link"], key, value)
    env = ManagerBasedRlEnv(cfg, device=device)
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


@pytest.mark.parametrize("task", ["PhoneGirl-Stand", "PhoneGirl-Walk"])
def test_web_viewer_builds_the_command_controls(task):
    """`play`'s web viewer adds a joystick per command; Stand's zero ranges once crashed it."""
    import viser

    cfg = load_env_cfg(task, play=True)
    cfg.scene.num_envs = 1
    env = ManagerBasedRlEnv(cfg, device="cpu")
    server = viser.ViserServer(port=8099, verbose=False)
    try:
        env.command_manager.create_gui(server, lambda: 0)
    finally:
        server.stop()
        env.close()


def test_density_and_com_shift_match_pseudo_inertia():
    """randomize_body's closed form is dr.pseudo_inertia with only its alpha and t parameters."""
    import mujoco
    from mjlab.envs.mdp.dr import body as pseudo
    from mjlab.utils.lab_api.math import matrix_from_quat

    model = mujoco.MjModel.from_xml_path(str(MJCF))
    mass, ipos, inertia, iquat = (torch.as_tensor(getattr(model, f)[1:], dtype=torch.float64)
                                  for f in ("body_mass", "body_ipos", "body_inertia", "body_iquat"))
    alpha = torch.linspace(-0.05, 0.06, len(mass), dtype=torch.float64)
    zero = torch.zeros_like(alpha)
    t = torch.zeros(3, len(mass), dtype=torch.float64)
    t[:, 0] = torch.tensor([0.004, -0.006, 0.002])  # the torso only
    U = pseudo._build_perturbation_U(alpha, zero, zero, zero, zero, zero, zero, *t)
    L = U @ pseudo._cholesky_4x4(pseudo._reconstruct_pseudo_inertia_J(mass, ipos, inertia, iquat))
    mass2, ipos2, inertia2, iquat2 = pseudo._decompose_pseudo_inertia_J(L @ L.mT)

    s = torch.exp(2 * alpha)
    close = dict(rtol=1e-9, atol=1e-12)
    torch.testing.assert_close(mass2, mass * s, **close)
    torch.testing.assert_close(ipos2, ipos + t.T, **close)
    # The same inertia tensor, in whatever order the eigendecomposition lists its axes.
    tensor = lambda diagonal, quat: matrix_from_quat(quat) @ torch.diag_embed(diagonal) @ matrix_from_quat(quat).mT
    torch.testing.assert_close(tensor(inertia2, iquat2), tensor(inertia * s[:, None], iquat), **close)


def test_reset_randomizes_body_and_friction_within_spans():
    env = make(scale=1.0, envs=64)
    r = Randomization()
    robot = env.scene["robot"]
    bodies, model, default = robot.indexing.body_ids, env.sim.model, env.sim.get_default_field
    ratio = model.body_mass[:, bodies] / default("body_mass")[bodies]
    assert ratio[:, 0].min() >= r.torso_mass.low and ratio[:, 0].max() <= r.torso_mass.high
    assert ratio[:, 1:].min() >= r.link_mass.low and ratio[:, 1:].max() <= r.link_mass.high
    assert ratio.std(0).min() > 0  # drawn per world and per body
    torch.testing.assert_close(model.body_inertia[:, bodies] / default("body_inertia")[bodies],
                               ratio[..., None].expand(-1, -1, 3))
    shift = model.body_ipos[:, bodies] - default("body_ipos")[bodies]
    assert shift[:, 0].abs().max() <= r.torso_com.high and shift[:, 0].abs().max() > 0
    assert shift[:, 1:].abs().max() == 0
    # subtree_com divides by body_subtreemass, so it must follow the masses at once.
    torch.testing.assert_close(model.body_subtreemass[:, bodies[0]], model.body_mass[:, bodies].sum(1))
    dofs = env.scene["robot"].actuators[0].dof_ids
    armature = model.dof_armature[:, dofs] / default("dof_armature")[dofs]
    assert armature.min() >= r.armature.low and armature.max() <= r.armature.high
    geoms = robot.indexing.geom_ids
    feet = model.geom_friction[:, geoms[list(FOOT_GEOMS)], 0]
    body = model.geom_friction[:, geoms[list(BODY_GEOMS)], 0]
    assert (feet == feet[:, :1]).all() and (body == body[:, :1]).all()  # one per episode
    assert r.foot_friction.low <= feet.min() and feet.max() <= r.foot_friction.high
    assert r.body_friction.low <= body.min() and body.max() <= r.body_friction.high
    env.close()


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA graphs")
def test_captured_recompute_matches_set_const():
    """The graph-captured recompute gives what MuJoCo Warp's set_const gives, on new masses each time."""
    import mujoco_warp as mjw
    import warp as wp
    from mjlab.managers.event_manager import RecomputeLevel

    env = make(scale=1.0, envs=8, device="cuda:0")
    sim = env.sim
    assert not hasattr(sim.recompute_constants, "__self__")  # replaced by graph_recompute
    derived = ("body_subtreemass", "dof_invweight0", "body_invweight0", "actuator_acc0")
    for _ in range(3):  # capture, then replays on fresh masses
        randomize_body(env, None, Randomization())
        sim.recompute_constants(RecomputeLevel.set_const)
        captured = {f: getattr(sim.model, f)[...].clone() for f in derived}
        with wp.ScopedDevice(sim.wp_device):
            mjw.set_const(sim.wp_model, sim.wp_data)
        for f in derived:
            torch.testing.assert_close(captured[f], getattr(sim.model, f)[...], rtol=1e-6, atol=0, msg=f)
    env.close()


def test_body_on_floor_matches_a_contact_sensor():
    """The contact-list fall check says what one contact sensor per body said, step by step."""
    from mjlab.sensor import ContactMatch, ContactSensorCfg
    from mjlab.tasks.velocity.mdp import illegal_contact

    from phone_girl.tasks.env import body_on_floor

    cfg = load_env_cfg("PhoneGirl-Stand", play=True)
    cfg.scene.num_envs = 16
    cfg.scene.sensors = (*cfg.scene.sensors, ContactSensorCfg(
        name="body_ground", primary=ContactMatch(mode="body", pattern=r"(?!.*_knee_link$).*", entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"), fields=("found",), reduce="netforce", num_slots=1))
    cfg.terminations = {}  # fallen robots stay down, so falls are seen from many poses
    env = ManagerBasedRlEnv(cfg, device="cpu")
    env.reset()
    check, falls = body_on_floor(None, env), 0
    for _ in range(150):
        env.step(torch.randn(16, len(JOINTS)))
        expected = illegal_contact(env, "body_ground")
        torch.testing.assert_close(check(env), expected)
        falls += int(expected.sum())
    assert falls > 100
    env.close()
