"""Render original, centered and whole-body optimized poses from matched cameras."""

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np
from scipy.optimize import minimize

from sim.preview import write_png
from sim.rest_pose import RestPoseProblem, REST_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("sim/runs/pose-comparison.png"))
    parser.add_argument("--variant", type=Path, help="Compare the optimized pose with another saved qpos JSON")
    args = parser.parse_args()
    problem = RestPoseProblem()
    ids = np.r_[np.arange(6), problem.dofs[:9]]
    def expand(z):
        x = np.zeros(problem.model.nv)
        x[ids] = z
        return x
    result = minimize(lambda z: np.sum(z * z), np.zeros(len(ids)), method="SLSQP",
                      constraints=[dict(type="eq", fun=lambda z: problem.constraints(expand(z))[:11])],
                      options=dict(ftol=1e-12, maxiter=200))
    if not result.success:
        raise RuntimeError(result.message)
    problem.set_x(expand(result.x))
    poses = [problem.q0, problem.data.qpos.copy(), np.array(json.loads(REST_PATH.read_text())["qpos"])]
    labels = ["Original CAD pose", "Centered, original arms", "Optimized, all joints"]
    if args.variant:
        poses = [poses[-1], np.array(json.loads(args.variant.read_text())["qpos"])]
        labels = ["Optimized, all joints", "Palms inward"]
    options = mujoco.MjvOption()
    options.geomgroup[3] = 0
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0, 0, 0.28]
    camera.distance = 0.87
    camera.elevation = -8
    renderer = mujoco.Renderer(problem.model, height=640, width=600)
    rows = []
    try:
        for azimuth in (90, 180):
            camera.azimuth = azimuth
            panels = []
            for pose, label in zip(poses, labels, strict=True):
                problem.data.qpos[:] = pose
                mujoco.mj_forward(problem.model, problem.data)
                renderer.update_scene(problem.data, camera=camera, scene_option=options)
                scene = renderer.scene
                text = scene.geoms[scene.ngeom]
                mujoco.mjv_initGeom(text, mujoco.mjtGeom.mjGEOM_LABEL, np.zeros(3),
                                  np.array([0., 0., 0.57]), np.eye(3).ravel(),
                                  np.array([1., 1., 1., 1.], dtype=np.float32))
                text.label = label
                scene.ngeom += 1
                panels.append(renderer.render().copy())
            rows.append(np.concatenate(panels, axis=1))
        write_png(args.output, np.concatenate(rows, axis=0))
        print(args.output.resolve())
    finally:
        renderer.close()


if __name__ == "__main__":
    main()
