"""Timing of the phone, the link to the MCU and the servo bus, as delays in physics steps.

Two links are modelled; see protocol/PROTOCOL.md. The default is USB-C NCM,
Ethernet over USB Full Speed. The MCU owns a 10 ms tick and the command comes
back within it:

    t - read      MCU Fast Sync Reads every servo
    t             the state frame leaves for the phone
    t + ~1 ms     the app takes the newest CoreMotion sample and runs the policy
    t + turn      the command arrives at the MCU
    t + turn + w  the MCU Sync Writes the goals and the servos pick them up

The other option is BLE (`ble_link`), where one control step is one 15 ms
connection interval and the command waits for the next connection event:

    t - read      MCU Fast Sync Reads every servo
    t             connection event k carries the state notification to the phone
    t + ~2 ms     the app takes the newest CoreMotion sample and runs the policy
    t + T         connection event k+1 carries the command to the MCU, or event
                  k+2 if the packet was lost and retransmitted
    t + T + w     the MCU Sync Writes the goals and the servos pick them up

In the simulator the observation is taken at the start of a control step, so
the servo telemetry is `read` old and the command lands `turn + w` later. iOS
has been seen to stall BLE callbacks for ~250 ms every few seconds; during a
stall the MCU keeps the last goal, which the servo model holds. USB's numbers
are placeholders until measured on the robot, and it has no stalls until any
are seen.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch


@dataclass
class LinkCfg:
    transport: str = "usb-ncm"
    interval_s: float = 0.010  # control period, the MCU's tick
    read_s: tuple[float, float] = (0.0005, 0.0015)  # Fast Sync Read ahead of the state frame
    turnaround_s: tuple[float, float] = (0.0015, 0.005)  # state out, CoreMotion and policy, command back
    write_s: tuple[float, float] = (0.0005, 0.003)  # MCU Sync Write and servo pickup after the command
    late_probability: float = 0.0  # a command comes late_s later than usual
    late_s: tuple[float, float] = (0.0, 0.0)
    max_delay_s: float = 0.06  # sizes the command delay buffer
    stall_rate_hz: float = 0.0  # how often the phone goes quiet
    stall_s: tuple[float, float] = (0.05, 0.25)


def ble_link() -> LinkCfg:
    """BLE: the connection interval is the tick, and a lost packet waits for the next event."""
    interval = 0.015
    return LinkCfg(transport="ble", interval_s=interval, read_s=(0.0005, 0.004), turnaround_s=(interval, interval),
                   late_probability=0.03, late_s=(interval, interval), stall_rate_hz=0.05)


def servos(env):
    return env.scene["robot"].actuators[0]


def _steps(env, seconds: torch.Tensor) -> torch.Tensor:
    return torch.round(seconds / env.physics_dt).long()


def _uniform(bounds: tuple[float, float], count: int, device) -> torch.Tensor:
    return bounds[0] + (bounds[1] - bounds[0]) * torch.rand(count, device=device)


def sample_link(env, env_ids: torch.Tensor | None, link: LinkCfg) -> None:
    """Reset event: this episode's command latency and telemetry age."""
    actuator = servos(env)
    ids = torch.arange(env.num_envs, device=env.device) if env_ids is None else env_ids
    base = _uniform(link.turnaround_s, len(ids), env.device) + _uniform(link.write_s, len(ids), env.device)
    actuator.command_lag[ids] = _steps(env, base)
    actuator.telemetry_age[ids] = _steps(env, _uniform(link.read_s, len(ids), env.device))
    actuator.set_lags(actuator.command_lag[ids], ids)


def late_commands(env, env_ids: torch.Tensor | None, link: LinkCfg) -> None:
    """Step event: some commands arrive late, and now and then the phone goes quiet
    and the MCU holds the last goal."""
    del env_ids
    actuator = servos(env)
    late = torch.rand(env.num_envs, device=env.device) < link.late_probability
    extra = _steps(env, _uniform(link.late_s, env.num_envs, env.device))
    actuator.set_lags(actuator.command_lag + late.long() * extra)
    start = (torch.rand(env.num_envs, device=env.device) < link.stall_rate_hz * env.step_dt) & (actuator.stall == 0)
    length = _steps(env, _uniform(link.stall_s, env.num_envs, env.device))
    actuator.stall[:] = torch.where(start, length, actuator.stall)


def delay_settings(link: LinkCfg, physics_dt: float) -> dict:
    """Actuator delay-buffer settings: lags are set only by the events above."""
    return dict(delay_min_lag=0, delay_max_lag=round(link.max_delay_s / physics_dt), delay_hold_prob=1.0)
