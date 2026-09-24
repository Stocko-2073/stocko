"""Compare ideal supplies and the two provisional motor/driver profiles.

The electrical bench prescribes rotor motion at a 90-degree electrical load
angle. It measures synchronous torque, not a measured or simulated pull-out
curve. Speeds above one wheel turn/s exceed the current firmware envelope.
"""
import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from ubot_sim.env import UBotNavigationEnv
from ubot_sim.motor import DRIVE_PROFILES, StepperDrive


def electrical_bench(config, wheel_tps, dt):
    config = replace(config, slip_protection=False, hold_current_rms=config.run_current_rms)
    motor = StepperDrive(config)
    offset = math.pi / (2 * config.pole_pairs * config.gear_ratio)
    motor.reset([offset, offset])
    speed = wheel_tps * 2 * math.pi
    # At least eight complete electrical cycles; discard a matching warmup.
    period = 1 / (config.pole_pairs * config.gear_ratio * wheel_tps) if wheel_tps else 0.05
    duration = math.ceil(0.05 / period) * period if wheel_tps else period
    duration = max(duration, 8 * period) if wheel_tps else duration
    count = math.ceil(duration / dt)
    torque, power, saturation = [], [], []
    for n in range(2 * count):
        t = n * dt
        out = motor.advance([speed * t] * 2, [speed] * 2, [speed] * 2, dt)
        if n >= count:
            torque.append(out[0])
            power.append(motor.bus_power)
            saturation.append(np.mean(np.abs(motor.phase_voltages) >= config.supply_voltage - 1e-9))
    return {"wheel_tps": wheel_tps, "motor_rpm": wheel_tps * config.gear_ratio * 60,
            "mean_wheel_torque_nm": float(np.mean(torque)),
            "mean_two_motor_bus_power_w": float(np.mean(power)),
            "voltage_saturation_fraction": float(np.mean(saturation))}


def robot_start(config, gentle):
    with UBotNavigationEnv(drive=config, wheel_contact="smooth") as env:
        env.reset(seed=0, options={"yaw": 0, "goal": [3, 0]})
        start = env.data.xpos[env.base, :2].copy()
        for n in range(100):
            target = min(0.3, (n + 1) * 0.01) if gentle else 0.4
            _, _, terminated, truncated, info = env.step([target, target])
            if terminated or truncated:
                break
        return {"seconds": float(env.data.time), "policy_steps": n + 1,
                "displacement_xy_m": (env.data.xpos[env.base, :2] - start).tolist(),
                "wheel_speed_rad_s": env.data.qvel[env.drive_dof].tolist(),
                "warning_count": sum(int(w.number) for w in env.data.warning),
                "finite": bool(np.isfinite(env.data.qpos).all() and np.isfinite(env.data.qvel).all()),
                "motor_fault": info["motor_fault"], "motor": info["motor"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/motors.json"))
    args = parser.parse_args()
    profiles = dict(DRIVE_PROFILES)
    # Keep the same chip and current settings for the voltage-only comparison.
    profiles["ideal_12v_tmc2208"] = replace(profiles["talentcell_24v"], supply_voltage=12)
    profiles["ideal_24v_tmc2208"] = replace(profiles["talentcell_24v"], supply_voltage=24)
    results = {}
    for name, config in profiles.items():
        row = {"config": asdict(config), "electrical": {}, "robot": {}}
        for dt in (0.000025, 0.0000125):
            row["electrical"][str(dt)] = [electrical_bench(config, speed, dt)
                                          for speed in (0, 0.3, 1, 2, 3)]
            if name in DRIVE_PROFILES:
                row["robot"][str(dt)] = {
                    label: robot_start(replace(config, max_timestep=dt), gentle)
                    for label, gentle in (("gentle", True), ("firmware_ramp", False))}
        results[name] = row
        print(f"Finished {name}", flush=True)
    files = [Path(__file__).with_name(name) for name in ("motor.py", "env.py", "motor_benchmark.py",
                                                       "contact_model.py", "elevation.py")]
    files.append(Path(__file__).parent / "assets" / "robot.xml")
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(),
              "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
              "method": {"supply": "ideal fixed voltage; no sag, BMS, SOC or thermal model",
                         "mechanics": "same robot mass and terrain for both profiles; ideal rigid gearing",
                         "electrical": "prescribed rotor speed, 90-degree electrical load angle, run current; not pull-out torque",
                         "speed_limit": "2 and 3 wheel turns/s exceed current firmware's 1 turn/s limit",
                         "robot": "seed 0, smooth wheels, flat terrain; up to 2 s or fault",
                         "gentle": "target increases by 0.01 wheel turns/s each 20 ms up to 0.3",
                         "firmware_ramp": "0.4 wheel turns/s target with 8 turns/s² acceleration",
                         "calibration": "datasheet-based estimates; not hardware-validated"},
              "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
