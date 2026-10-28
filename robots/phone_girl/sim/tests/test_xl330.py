"""The XL330 actuator against BAM's own CPU implementation."""

import mujoco
import numpy as np
import pytest
import torch

from bam.model import load_model
from bam.mujoco import MujocoController

from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.scene import Scene, SceneCfg
from mjlab.sim import MujocoCfg, Simulation, SimulationCfg

from phone_girl.xl330 import FRICTION_SOLIMP, FRICTION_SOLREF, TICK, Bam, Xl330ActuatorCfg, \
    friction_budget, motor


@pytest.fixture(scope="module")
def reference():
    model = load_model(motor_name="xl330", model="m6")
    model.actuator.vin = 7.4
    return model


def test_motor_matches_bam(reference):
    rng = np.random.default_rng(0)
    target, q, dq = rng.uniform(-1, 1, 2000), rng.uniform(-1, 1, 2000), rng.uniform(-8, 8, 2000)
    actuator = reference.actuator
    volts = actuator.compute_control(target, q, dq, 0.002)
    torque = actuator.compute_torque(volts, True, q, dq)
    bam = Bam.load()
    t = lambda x: torch.as_tensor(x, dtype=torch.float64)
    duty, current, ours = motor(t((target - q) / TICK), t(dq), t(7.4), t(actuator.kp), bam.kt, bam.resistance,
                                bam.error_gain, bam.max_pwm, bam.max_current)
    np.testing.assert_allclose(duty.numpy() * 7.4, volts, atol=1e-12)
    np.testing.assert_allclose(ours.numpy(), torque, atol=1e-12)
    np.testing.assert_allclose(current.numpy(), torque / bam.kt, atol=1e-12)
    assert np.abs(current.numpy()).max() <= bam.max_current + 1e-9 or np.any(np.abs(duty.numpy()) == 1)


def test_friction_matches_bam(reference):
    rng = np.random.default_rng(1)
    # Include exact zeros: BAM's quadratic term switches on sign comparisons.
    motor_torque = np.concatenate([rng.normal(0, 0.2, 3000), np.zeros(50), rng.normal(0, 0.2, 50)])
    external = np.concatenate([rng.normal(0, 0.2, 3000), rng.normal(0, 0.2, 50), np.zeros(50)])
    velocity = rng.normal(0, 3, 3100)
    expected = np.array([reference.compute_frictions(m, e, v)[0]
                         for m, e, v in zip(motor_torque, external, velocity)])
    t = lambda x: torch.as_tensor(x, dtype=torch.float64)
    ours = friction_budget(Bam.load(), t(motor_torque), t(external), t(velocity)).numpy()
    np.testing.assert_allclose(ours, expected, atol=1e-12)


PENDULUM = """<mujoco>
  <worldbody><body name="arm" pos="0 0 0.5">
    <joint name="servo" axis="0 1 0"/>
    <geom type="capsule" fromto="0 0 0 0.1 0 0" size="0.01" mass="0.15"/>
  </body></worldbody>
  <actuator><motor name="servo" joint="servo"/></actuator>
</mujoco>"""


def test_pendulum_tracks_bam_cpu(reference):
    """A held, then swinging, 150 g arm: MuJoCo Warp with this actuator vs BAM on CPU MuJoCo."""
    steps, dt = 400, 0.002
    goal = lambda k: 0.6 if k < 200 else -0.4

    model = mujoco.MjModel.from_xml_string(PENDULUM)
    model.opt.timestep, model.opt.integrator = dt, mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    # Same stiff joint-friction impedance the GPU actuator uses for lack of noslip.
    model.dof_solref[:], model.dof_solimp[:] = FRICTION_SOLREF, FRICTION_SOLIMP
    data = mujoco.MjData(model)
    controller = MujocoController(reference, "servo", model, data)
    reference.actuator.kp = 400
    expected = []
    for k in range(steps):
        controller.set_q_target("servo", goal(k))
        controller.update()
        mujoco.mj_step(model, data)
        expected.append(data.qpos[0])

    servo = Xl330ActuatorCfg(target_names_expr=("servo",), kp=400, quantize=False, supply_voltage=7.4,
                             supply_resistance=0.0, idle_current=0.0)
    entity = EntityCfg(spec_fn=lambda: mujoco.MjSpec.from_string(PENDULUM),
                       articulation=EntityArticulationInfoCfg(actuators=(servo,)))
    scene = Scene(SceneCfg(num_envs=2, terrain=None, entities={"robot": entity}), "cpu")
    sim = Simulation(num_envs=2, cfg=SimulationCfg(mujoco=MujocoCfg(timestep=dt, gravity=(0, 0, -9.81))),
                     spec=scene.spec, device="cpu")
    scene.initialize(mj_model=sim.mj_model, model=sim.model, data=sim.data)
    sim.expand_model_fields(("dof_frictionloss", "dof_damping"))
    robot = scene["robot"]
    ours = []
    for k in range(steps):
        robot.set_joint_position_target(torch.full((2, 1), goal(k)))
        scene.write_data_to_sim()
        sim.step()
        scene.update(dt)
        ours.append(robot.data.joint_pos[:, 0].numpy().copy())
    ours = np.array(ours)
    np.testing.assert_allclose(ours[:, 0], ours[:, 1])  # worlds are independent copies
    # float32 MuJoCo Warp against float64 MuJoCo: compare trajectories, not bits.
    np.testing.assert_allclose(ours[:, 0], expected, atol=5e-4)
    # Gravity sags the held arm past its goal; the second goal is still being approached.
    assert 0.62 < ours[199, 0] < 0.72 and ours[-1, 0] < -0.25
