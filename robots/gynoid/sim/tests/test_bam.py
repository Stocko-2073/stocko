import mujoco
import numpy as np
import pytest
from bam.model import load_model
from bam.mujoco import MujocoController

from sim.actuators import BamActuators, PARAMETERS
from sim.env import GynoidBalanceEnv


def pendulum(floating=False):
    root = '<freejoint/>' if floating else ''
    return mujoco.MjModel.from_xml_string(f'''<mujoco>
      <option timestep="0.002" gravity="0 0 0" integrator="implicitfast"/>
      <worldbody><body pos="0 0 1">{root}<geom size=".1" mass="1"/>
        <body><joint name="servo" axis="0 1 0"/>
          <geom pos="0 0 -.2" size=".04" mass=".1"/>
        </body></body></worldbody>
      <actuator><motor name="servo" joint="servo"/></actuator>
    </mujoco>''')


def test_electrical_limits_and_back_emf():
    model = pendulum()
    data = mujoco.MjData(model)
    controller = BamActuators(model, data)
    kt, resistance = controller.bam.kt.value, controller.bam.R.value
    for velocity in (-5.0, 0.0, 5.0):
        data.qvel[:] = velocity
        for target in (-100.0, 100.0):
            controller.update(np.array([target]))
            assert abs(controller.control_voltage[0]) <= 5.0
            assert abs(data.ctrl[0] / kt) <= 1.75 + 1e-12
    # Zero position error still produces electrical braking from back-EMF.
    data.qvel[:] = 5.0
    controller.update(np.zeros(1))
    assert data.ctrl[0] == pytest.approx(-kt * kt * 5.0 / resistance)


def test_fixed_base_matches_bam_cpu_reference():
    ours, reference = pendulum(), pendulum()
    data, ref_data = mujoco.MjData(ours), mujoco.MjData(reference)
    controller = BamActuators(ours, data)
    bam = load_model(str(PARAMETERS))
    bam.actuator.vin, bam.actuator.kp = 5.0, 200.0
    ref = MujocoController(bam, ['servo'], reference, ref_data)
    # Upstream's initial friction is caller-owned; align the starting budget.
    reference.dof_frictionloss[:] = ours.dof_frictionloss
    reference.dof_damping[:] = ours.dof_damping
    mujoco.mj_forward(ours, data)
    mujoco.mj_forward(reference, ref_data)
    for step in range(300):
        target = 0.25 if step < 150 else -0.25
        controller.update(np.array([target]))
        ref.set_q_target('servo', target)
        ref.update()
        np.testing.assert_allclose(data.ctrl, ref_data.ctrl, atol=1e-12)
        np.testing.assert_allclose(ours.dof_frictionloss, reference.dof_frictionloss, atol=1e-12)
        mujoco.mj_step(ours, data)
        mujoco.mj_step(reference, ref_data)
        np.testing.assert_allclose(data.qpos, ref_data.qpos, atol=1e-12)
        if step == 149:
            assert data.qpos[0] > 0.1
    assert data.qpos[0] < -0.1


def test_floating_base_removes_own_friction_by_dof():
    model = pendulum(floating=True)
    data = mujoco.MjData(model)
    controller = BamActuators(model, data)
    assert controller.joints[0] == 1 and controller.dofs[0] == 6
    mujoco.mj_forward(model, data)
    for _ in range(50):
        controller.update(np.array([0.25]))
        mujoco.mj_step(model, data)
    assert data.efc_id.tolist() == [6]
    assert abs(data.efc_force[0]) > 1e-4
    # There are no contacts or limits: the only constraint is own dry friction.
    np.testing.assert_allclose(controller.external_torque(),
                               -data.qfrc_bias[controller.dofs], atol=1e-12)


def test_centered_pose_and_episode_reset():
    env = GynoidBalanceEnv(reset_noise=0)
    env.reset(seed=1)
    assert np.linalg.norm(env._support_error()) < 1e-6
    assert abs(np.diff(env.data.site_xpos[env.feet, 2])[0]) < 1e-6
    assert env.data.ncon == 0
    assert np.max(np.abs(env.neutral)) < np.deg2rad(1.2)
    env.reset_noise = .01
    first_obs, _ = env.reset(seed=123)
    first_step = env.step(np.ones(9) * .2)
    for _ in range(20):
        env.step(np.ones(9) * -.8)
    second_obs, _ = env.reset(seed=123)
    second_step = env.step(np.ones(9) * .2)
    np.testing.assert_array_equal(first_obs, second_obs)
    np.testing.assert_array_equal(first_step[0], second_step[0])
    assert first_step[1:] == second_step[1:]
    env.close()


def test_wider_targets_retain_physics_and_pose_penalty():
    narrow = GynoidBalanceEnv(reset_noise=0)
    wide = GynoidBalanceEnv(reset_noise=0, action_range="wide")
    narrow.reset(seed=1)
    wide.reset(seed=1)
    np.testing.assert_array_equal(narrow.model.jnt_range, wide.model.jnt_range)
    np.testing.assert_array_equal(narrow.model.dof_armature, wide.model.dof_armature)
    np.testing.assert_array_equal(narrow.pose_scale, wide.pose_scale)
    assert narrow.actuators.configuration() == wide.actuators.configuration()
    # Fixed-target behavior must be identical: only policy target range changes.
    for _ in range(20):
        a = narrow.step(np.zeros(9))
        b = wide.step(np.zeros(9))
        np.testing.assert_array_equal(a[0], b[0])
        assert a[1:] == b[1:]
    narrow.close()
    wide.close()
