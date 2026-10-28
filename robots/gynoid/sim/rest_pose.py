"""Constrained whole-body rest pose, using sliced masses and inverse statics."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np
from scipy.optimize import minimize

MODEL_PATH = Path(__file__).with_name("gynoid_full.xml")
REST_PATH = Path(__file__).with_name("rest_pose.json")


class RestPoseProblem:
    def __init__(self):
        self.model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
        self.data = mujoco.MjData(self.model)
        self.q0 = self.model.qpos0.copy()
        self.joints = self.model.actuator_trnid[:, 0]
        self.qids = self.model.jnt_qposadr[self.joints]
        self.dofs = self.model.jnt_dofadr[self.joints]
        self.feet = [self.model.site(f"{s}_foot").id for s in ("left", "right")]
        self.torso = self.model.body("waist").id
        self.pelvis = self.model.body("pelvis").id
        self.rod_sites = [(self.model.site(f"{s}_rod_end").id,
                           self.model.site(f"{s}_stem").id) for s in ("left", "right")]
        mujoco.mj_forward(self.model, self.data)
        self.anchors = self.data.site_xpos[self.feet].copy()
        # These are spherical 2.5 mm tips, so their centers are above the floor.
        self.anchors[:, 2] = 0.0025
        self.last_x = None

    def set_x(self, x):
        if self.last_x is not None and np.array_equal(x, self.last_x):
            return
        self.data.qpos[:] = self.q0
        mujoco.mj_integratePos(self.model, self.data.qpos, x, 1.0)
        self.data.qvel[:] = 0
        mujoco.mj_forward(self.model, self.data)
        self.last_x = x.copy()

    def holding_torque(self):
        """Solve actuator and neck-closure forces for equal vertical tip loads.

        At a centered CoM the two vertical loads balance all six root forces.
        Rod reactions are internal forces, not fictitious floor welds.
        """
        m, d = self.model, self.data
        external = np.zeros(m.nv)
        weight = m.body_mass.sum() * 9.81
        for site in self.feet:
            mujoco.mj_applyFT(m, d, np.array([0., 0., weight / 2]), np.zeros(3),
                             d.site_xpos[site], int(m.site_bodyid[site]), external)
        columns = np.eye(m.nv)[:, self.dofs]
        for end, stem in self.rod_sites:
            j1, j2 = np.zeros((3, m.nv)), np.zeros((3, m.nv))
            mujoco.mj_jacSite(m, d, j1, None, end)
            mujoco.mj_jacSite(m, d, j2, None, stem)
            columns = np.column_stack((columns, (j1 - j2).T))
        required = d.qfrc_bias - external
        forces = np.linalg.lstsq(columns, required, rcond=1e-10)[0]
        return forces[:m.nu], required - columns @ forces

    def constraints(self, x):
        self.set_x(x)
        d = self.data
        rotation = d.xmat[self.torso].reshape(3, 3)
        closure = np.concatenate([d.site_xpos[a] - d.site_xpos[b] for a, b in self.rod_sites])
        return np.concatenate(((d.site_xpos[self.feet] - self.anchors).ravel() * 100,
                               (d.subtree_com[self.pelvis, :2] - self.anchors[:, :2].mean(0)) * 100,
                               rotation[:2, 2], [x[5]], closure * 100))

    def objective(self, x):
        self.set_x(x)
        tau, residual = self.holding_torque()
        height_error = (self.data.qpos[2] - (self.q0[2] + 0.005)) / 0.015
        penetration = sum(min(c.dist, 0.) ** 2 for c in self.data.contact
                          if c.geom1 != 0 and c.geom2 != 0)
        return (float(np.sum((tau / 0.03) ** 2)) + 5 * height_error ** 2
                + 0.01 * float(np.sum(x[6:] ** 2)) + 1e6 * penetration
                + 1e5 * float(np.sum(residual[6:] ** 2)))

    def metrics(self):
        tau, residual = self.holding_torque()
        parameters = json.loads(MODEL_PATH.with_name("assets").joinpath("xl330_m6.json").read_text())
        return dict(hip_height_m=float(self.data.qpos[2]),
                    com_m=self.data.subtree_com[self.pelvis].tolist(),
                    foot_centers_m=self.data.site_xpos[self.feet].tolist(),
                    holding_torque_nm=tau.tolist(), peak_holding_torque_nm=float(np.abs(tau).max()),
                    copper_loss_w=float(np.sum((tau / parameters["kt"]) ** 2) * parameters["R"]),
                    force_balance_residual=float(np.linalg.norm(residual)),
                    torso_up=self.data.xmat[self.torso].reshape(3, 3)[:, 2].tolist())

    def solve(self):
        bounds = [(-0.04, 0.04)] * 2 + [(-0.001, 0.025)] + [(-0.15, 0.15)] * 3
        bounds += [(-0.8, 0.8)] * (self.model.nv - 6)
        for joint in range(1, self.model.njnt):
            if self.model.jnt_type[joint] == mujoco.mjtJoint.mjJNT_HINGE:
                bounds[self.model.jnt_dofadr[joint]] = tuple(self.model.jnt_range[joint])
        x0 = np.zeros(self.model.nv)
        self.set_x(x0)
        baseline = self.metrics()
        # A feasible comparison: smallest leg/waist adjustment with the upper
        # body retained in CAD pose, subject to the same foot and torso goals.
        fixed_upper_ids = np.r_[np.arange(6), self.dofs[:9]]
        def expand(z):
            x = np.zeros(self.model.nv)
            x[fixed_upper_ids] = z
            return x
        centered = minimize(lambda z: np.sum(z * z), np.zeros(len(fixed_upper_ids)),
                            method="SLSQP", bounds=[bounds[i] for i in fixed_upper_ids],
                            constraints=[dict(type="eq", fun=lambda z: self.constraints(expand(z))[:11])],
                            options=dict(ftol=1e-12, maxiter=200))
        if not centered.success:
            raise RuntimeError("Unable to construct the fixed-upper-body comparison")
        self.set_x(expand(centered.x))
        comparison = self.metrics()
        result = minimize(self.objective, x0, method="SLSQP", bounds=bounds,
                          constraints=[dict(type="eq", fun=self.constraints)],
                          options=dict(maxiter=400, ftol=1e-10, disp=True))
        self.set_x(result.x)
        error = np.max(np.abs(self.constraints(result.x)))
        if not result.success or error > 1e-5:
            raise RuntimeError(f"Rest pose failed: {result.message}; constraint error {error}")
        if any(c.dist < -1e-5 and c.geom1 != 0 and c.geom2 != 0 for c in self.data.contact):
            raise RuntimeError("Rest pose contains a self collision")
        return dict(model_sha256=hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
                    qpos=self.data.qpos.tolist(), foot_anchors_m=self.anchors.tolist(),
                    joint_names=[self.model.joint(int(j)).name for j in self.joints],
                    optimized=self.metrics(), cad_pose=baseline, centered_fixed_upper_body=comparison,
                    iterations=result.nit, objective=result.fun, constraint_error=error,
                    assumptions=["Equal vertical loads through the two original CAD foot centers.",
                                 "Vertical torso; hips no lower than 1 mm below CAD height.",
                                 "Copper loss is an I-squared-R proxy, excluding electronics and stiction.",
                                 "Joint ranges, collision proxies and fixed neck roll need hardware validation."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REST_PATH)
    args = parser.parse_args()
    result = RestPoseProblem().solve()
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["optimized"], indent=2))


if __name__ == "__main__":
    main()
