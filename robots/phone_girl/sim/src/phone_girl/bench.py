"""Measure simulation throughput for a phone_girl task: run this first on a new GPU.

For each world count it reports control steps and physics steps per second
under random actions (so robots fall and reset, as early in training), GPU
memory, Newton iterations, the most constraint rows any world used (njmax) and
the most contacts across all worlds (nconmax is per world on average).

--profile splits a control step into its parts: the CPU time each takes, not
counting parts nested in it, and the GPU kernels it launches. When the CPU time
adds up to much more than the GPU's busy time, the step is bound by Python
launching kernels, not by the GPU.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import functools
import time

import torch

from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg

LAUNCHES = {"cudaLaunchKernel", "cuLaunchKernel", "cudaLaunchKernelExC", "cuLaunchKernelEx",
            "cudaGraphLaunch", "cuGraphLaunch", "cudaMemcpyAsync", "cudaMemsetAsync"}


class Parts:
    """Wraps the methods a control step is made of, to time them and name them for the profiler."""

    def __init__(self, env: ManagerBasedRlEnv):
        robot = env.scene["robot"]
        methods = {
            "process action": (env.action_manager, "process_action"),
            "apply action": (env.action_manager, "apply_action"),
            "write to sim": (env.scene, "write_data_to_sim"),
            "physics step": (env.sim, "step"),
            "robot update": (robot, "update"),
            "terminations": (env.termination_manager, "compute"),
            "rewards": (env.reward_manager, "compute"),
            "events": (env.event_manager, "apply"),
            "reset": (env, "_reset_idx"),
            "forward": (env.sim, "forward"),
            "commands": (env.command_manager, "compute"),
            "sense": (env.sim, "sense"),
            "observations": (env.observation_manager, "compute"),
        }
        for i, actuator in enumerate(robot.actuators):
            methods[f"servos {i}" if i else "servos"] = (actuator, "compute")
        for sensor_cfg in env.cfg.scene.sensors:  # the task's own sensors, not the MJCF's
            methods[f"sensor {sensor_cfg.name}"] = (env.scene.sensors[sensor_cfg.name], "update")
        methods["recompute"] = (env.sim, "recompute_constants")
        self.names = list(methods)
        self.seconds, self.calls, self._nested = defaultdict(float), defaultdict(int), []
        self.serial = False  # wait for the GPU around each part, to time its GPU work too
        for name, (owner, method) in methods.items():
            setattr(owner, method, self._wrap(name, getattr(owner, method)))
        # Event terms one by one. Class-based terms keep their own reset(), so are left whole.
        manager = env.event_manager
        for mode, cfgs in manager._mode_term_cfgs.items():
            for name, cfg in zip(manager._mode_term_names[mode], cfgs, strict=True):
                if not hasattr(cfg.func, "reset"):
                    self.names.append(f"event {name}")
                    cfg.func = self._wrap(f"event {name}", cfg.func)

    def _wrap(self, name, fn):
        @functools.wraps(fn)  # keeps attributes such as an event's recompute level
        def part(*args, **kwargs):
            if self.serial:
                torch.cuda.synchronize()
            started = time.perf_counter()
            self._nested.append(0.0)
            try:
                with torch.profiler.record_function(name):
                    return fn(*args, **kwargs)
            finally:
                if self.serial:
                    torch.cuda.synchronize()
                elapsed = time.perf_counter() - started
                self.seconds[name] += elapsed - self._nested.pop()
                self.calls[name] += 1
                if self._nested:
                    self._nested[-1] += elapsed
        return part

    def clear(self):
        self.seconds.clear()
        self.calls.clear()


def profile(env: ManagerBasedRlEnv, parts: Parts, actions, steps: int) -> None:
    """Print each part's time per control step, as run and alone, its kernel launches, and the GPU's busy time."""
    def timed(serial: bool) -> float:
        parts.clear()
        parts.serial = serial
        torch.cuda.synchronize()
        started = time.perf_counter()
        for _ in range(steps):
            env.step(actions())
        torch.cuda.synchronize()
        parts.serial = False
        return (time.perf_counter() - started) / steps

    serial_wall = timed(serial=True)
    alone = dict(parts.seconds)
    wall = timed(serial=False)
    seconds, calls = dict(parts.seconds), dict(parts.calls)

    traced = 5
    activities = [torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA]
    with torch.profiler.profile(activities=activities) as prof:
        for _ in range(traced):
            env.step(actions())
        torch.cuda.synchronize()
    # GPU busy time: the union of kernel intervals, so concurrent kernels count once.
    gpu_us, end = 0.0, float("-inf")
    for start, stop in sorted((e.time_range.start, e.time_range.end) for e in prof.events()
                              if e.device_type == torch.autograd.DeviceType.CUDA):
        gpu_us += max(0.0, stop - max(start, end))
        end = max(end, stop)
    launches = defaultdict(int)
    for event in prof.events():
        if event.name in LAUNCHES:
            owner = event.cpu_parent
            while owner is not None and owner.name not in parts.names:
                owner = owner.cpu_parent
            launches[owner.name if owner is not None else "other"] += 1

    # CPU ms: time in the part, running as usual. Alone ms: the same with the GPU
    # drained before and after it, so the larger of its launch time and GPU time.
    accounted, alone_accounted = sum(seconds.values()) / steps, sum(alone.values()) / steps
    print(f"  {'part':20s} {'calls':>5s} {'CPU ms':>7s} {'alone ms':>8s} {'launches':>8s}")
    for name in sorted(alone, key=alone.get, reverse=True):
        print(f"  {name:20s} {calls[name] / steps:5.0f} {1e3 * seconds[name] / steps:7.2f}"
              f" {1e3 * alone[name] / steps:8.2f} {launches.get(name, 0) / traced:8.0f}")
    print(f"  {'other':20s} {'':5s} {1e3 * (wall - accounted):7.2f} {1e3 * (serial_wall - alone_accounted):8.2f}"
          f" {launches.get('other', 0) / traced:8.0f}")
    print(f"  {'step':20s} {'':5s} {1e3 * wall:7.2f} {1e3 * serial_wall:8.2f} {sum(launches.values()) / traced:8.0f}"
          f"   GPU busy {gpu_us / traced / 1e3:.2f} ms", flush=True)


def run(task: str, envs: int, steps: int, device: str, camera: bool, sync_debug: bool = False,
        breakdown: bool = False) -> dict:
    cfg = load_env_cfg(task)
    cfg.scene.num_envs = envs
    if camera:
        from phone_girl.phone import with_camera
        cfg = with_camera(cfg)
    env = ManagerBasedRlEnv(cfg, device=device)
    parts = Parts(env) if breakdown else None
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
    if parts is not None:
        result["profile"] = lambda: (profile(env, parts, actions, steps), env.close())
    else:
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
    parser.add_argument("--profile", action="store_true", help="split a control step into its parts (CUDA only)")
    args = parser.parse_args()
    cuda = "cuda" in args.device
    print(f"{args.task} on {args.device}" + (f" ({torch.cuda.get_device_name()})" if cuda else ""))
    for envs in args.envs:
        r = run(args.task, envs, args.steps, args.device, args.camera, args.sync_debug and cuda, args.profile and cuda)
        memory = f"  {r['gpu_used_gb']:.1f} GB" if "gpu_used_gb" in r else ""
        print(f"{envs:6d} envs  {r['control_steps_per_s']:10.0f} steps/s  {r['physics_steps_per_s']:11.0f} physics/s"
              f"  {r['ms_per_step']:6.1f} ms/step  newton<={r['max_newton_iterations']}"
              f"  rows<={r['max_constraint_rows']}  contacts<={r['max_contacts'] / envs:.1f}/world{memory}", flush=True)
        if "profile" in r:
            r["profile"]()


if __name__ == "__main__":
    main()
