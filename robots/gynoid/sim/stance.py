"""Find a small hip adjustment that centers COM and levels the two leg tips."""

import mujoco
import numpy as np


def standing_pose(model, stance="centered"):
    if stance not in ("cad", "centered"):
        raise ValueError("Stance must be 'cad' or 'centered'")
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    pelvis = model.body("pelvis").id
    feet = [model.site(f"{side}_foot").id for side in ("left", "right")]
    original = data.qpos.copy()

    def residual(parameters):
        pitch, roll, differential_pitch = parameters
        data.qpos[:] = original
        for side, sign in (("left", 1), ("right", -1)):
            data.joint(f"{side}_hip_pitch").qpos[0] = pitch + sign * differential_pitch
            data.joint(f"{side}_hip_roll").qpos[0] = sign * roll
        mujoco.mj_forward(model, data)
        tips = data.site_xpos[feet]
        return np.r_[data.subtree_com[pelvis, :2] - tips[:, :2].mean(axis=0),
                     tips[0, 2] - tips[1, 2]]

    parameters = np.zeros(3)
    if stance == "centered":
        for _ in range(12):
            error = residual(parameters)
            if np.linalg.norm(error) < 1e-8:
                break
            epsilon = 1e-5
            jacobian = np.column_stack([
                (residual(parameters + epsilon * axis) - error) / epsilon
                for axis in np.eye(3)])
            parameters -= np.linalg.solve(jacobian, error)
            if np.max(np.abs(parameters)) > 0.1:
                raise ValueError("Centering requires more than a small hip adjustment")
        if np.linalg.norm(residual(parameters)) > 1e-6:
            raise ValueError("Unable to center the standing pose")
    residual(parameters)
    # Both rounded tips start 0.3 mm above ground, as in the CAD baseline.
    data.qpos[2] += 0.0003 - (data.site_xpos[feet, 2].min() - 0.0025)
    return data.qpos.copy()
