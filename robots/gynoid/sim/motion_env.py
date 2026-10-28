"""Planted task with command headroom for recovery and deliberate motion."""

import mujoco
import numpy as np

from sim.planted import GynoidPlantedEnv


class GynoidMotionEnv(GynoidPlantedEnv):
    def __init__(self, *, command_scale=2.0, target_speed=8.0, right_shoulder_upper=0.8, **kwargs):
        if not np.isfinite([command_scale, target_speed]).all() or min(command_scale, target_speed) <= 0:
            raise ValueError("Command scale and slew rate must be finite and positive")
        super().__init__(**kwargs)
        if not np.isfinite(right_shoulder_upper) or not 0.8 <= right_shoulder_upper <= np.pi:
            raise ValueError("Right shoulder upper travel must be between 0.8 and pi radians")
        self.right_shoulder_upper = float(right_shoulder_upper)
        self.model.jnt_range[self.model.joint("right_shoulder_1").id, 1] = right_shoulder_upper
        self.command_scale = float(command_scale)
        self.action_scale *= self.command_scale
        self.target_speed = float(target_speed)
        self.action_range = "motion_residual"
        self.hand = self.model.geom("part_19_hand").id
        self.head = self.model.geom("part_2_head").id
        self.extent_vertices = {}
        for geom in (self.hand, self.head):
            mesh = self.model.geom_dataid[geom]
            start, count = self.model.mesh_vertadr[mesh], self.model.mesh_vertnum[mesh]
            self.extent_vertices[geom] = self.model.mesh_vert[start:start + count].copy()
        self.shoulder = self.joint_names.index("right_shoulder_1")
        self.hand_origin = np.zeros(3)
        self.initial_command_center = self.command_center.copy()

    def reset(self, **kwargs):
        self.command_center[:] = self.initial_command_center
        result = super().reset(**kwargs)
        self.hand_origin[:] = self.data.geom_xpos[self.hand]
        return result

    def step(self, action):
        observation, reward, terminated, truncated, info = super().step(action)
        loads = np.zeros(2)
        for index, contact in enumerate(self.data.contact):
            pair = (contact.geom1, contact.geom2)
            if self.floor not in pair:
                continue
            foot = pair[1] if pair[0] == self.floor else pair[0]
            if foot in self.foot_geoms:
                force = np.zeros(6)
                mujoco.mj_contactForce(self.model, self.data, index, force)
                world_force = contact.frame.reshape(3, 3).T @ force[:3]
                loads[self.foot_geoms.index(foot)] += abs(world_force[2])
        def heights(geom):
            return (self.extent_vertices[geom] @ self.data.geom_xmat[geom].reshape(3, 3)[2]
                    + self.data.geom_xpos[geom, 2])
        head_top = float(heights(self.head).max())
        info.update(right_shoulder_offset_rad=float(self.data.qpos[self.qpos_ids[self.shoulder]]
                                                    - self.neutral[self.shoulder]),
                    right_hand_forward_m=float(self.data.geom_xpos[self.hand, 0] - self.hand_origin[0]),
                    right_hand_above_head_m=float(self.data.geom_xpos[self.hand, 2] - head_top),
                    right_hand_lowest_above_head_m=float(heights(self.hand).min() - head_top),
                    peak_current_a=self.actuators.peak_current_a,
                    peak_voltage_v=self.actuators.peak_voltage_v,
                    peak_torque_nm=self.actuators.peak_torque_nm,
                    saturated_actuator_updates=self.actuators.saturated_updates,
                    com_lateral_m=float(self.data.subtree_com[self.pelvis, 1] - self.anchors[:, 1].mean()),
                    foot_vertical_load_n=loads.tolist(),
                    left_load_fraction=float(loads[0] / loads.sum()) if loads.sum() > 1e-6 else 0.5)
        return observation, reward, terminated, truncated, info

    def configuration(self):
        config = super().configuration()
        config.update(task="motion", command_scale=self.command_scale,
                      target_speed_rad_s=self.target_speed,
                      right_shoulder_upper_rad=self.right_shoulder_upper,
                      command_center_rad=self.initial_command_center.tolist())
        return config
