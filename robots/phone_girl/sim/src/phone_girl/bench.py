"""Measure simulation throughput for a phone_girl task: run this first on a new GPU.

For each world count it reports control steps and physics steps per second
under random actions (so robots fall and reset, as early in training), GPU
memory, Newton iterations, the most constraint rows any world used (njmax) and
the most contacts across all worlds (nconmax is per world on average).
"""

from __future__ import annotations

import argparse
import time

import torch

from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg


def run(task: str, envs: int, steps: int, device: str, camera: bool, sync_debug: bool = False) -> dict:
    cfg = load_env_cfg(task)
    cfg.scene.num_envs = envs
    if camera:
        from phone_girl.phone import with_camera
        cfg = with_camera(cfg)
    env = ManagerBasedRlEnv(cfg, device=device)
    env.reset()
    actions = lambda: 0.5 * torch.randn(envs, env.action_manager.total_action_dim, device=device)
    for _ in range(20):  # compile kernels and capture graphs
        env.step(actions())
    if sync_debug:
        # Report every point where the CPU waits for the GPU during one control step.
        torch.cuda.set_sync_debug_mode("warn")
        env.step(actions())
        torch.cuda.set_sync_debug_mode("default")
    if device.startswith("cuda"):
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    iterations, rows, contacts = [], [], []
    started = time.perf_counter()
    for _ in range(steps):
        env.step(actions())
        iterations.append(env.sim.data.solver_niter[...].max())
        rows.append(env.sim.data.nefc[...].max())
        contacts.append(env.sim.data.nacon[...].max())  # all worlds together
    if device.startswith("cuda"):
        torch.cuda.synchronize()
    seconds = time.perf_counter() - started
    result = dict(envs=envs, control_steps_per_s=envs * steps / seconds,
                  physics_steps_per_s=envs * steps * cfg.decimation / seconds,
                  ms_per_step=1000 * seconds / steps, max_newton_iterations=int(torch.stack(iterations).max()),
                  max_constraint_rows=int(torch.stack(rows).max()), max_contacts=int(torch.stack(contacts).max()))
    if device.startswith("cuda"):
        free, total = torch.cuda.mem_get_info()
        result["gpu_used_gb"] = (total - free) / 1e9
    env.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", default="PhoneGirl-Walk")
    parser.add_argument("--envs", type=int, nargs="+", default=[1024, 2048, 4096, 8192])
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--device", default="cuda:0" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--camera", action="store_true", help="add the front depth camera at 48x64")
    parser.add_argument("--sync-debug", action="store_true", help="warn at each CPU-GPU sync in one step")
    args = parser.parse_args()
    print(f"{args.task} on {args.device}" + (f" ({torch.cuda.get_device_name()})" if "cuda" in args.device else ""))
    for envs in args.envs:
        r = run(args.task, envs, args.steps, args.device, args.camera, args.sync_debug and "cuda" in args.device)
        memory = f"  {r['gpu_used_gb']:.1f} GB" if "gpu_used_gb" in r else ""
        print(f"{envs:6d} envs  {r['control_steps_per_s']:10.0f} steps/s  {r['physics_steps_per_s']:11.0f} physics/s"
              f"  {r['ms_per_step']:6.1f} ms/step  newton<={r['max_newton_iterations']}"
              f"  rows<={r['max_constraint_rows']}  contacts<={r['max_contacts'] / envs:.1f}/world{memory}", flush=True)


if __name__ == "__main__":
    main()
