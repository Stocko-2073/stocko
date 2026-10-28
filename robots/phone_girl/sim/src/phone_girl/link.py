"""Timing of the phone, BLE link, MCU and servo bus, as delays in physics steps.

One control step is one BLE connection interval (see protocol/PROTOCOL.md):

    t - read      MCU Fast Sync Reads every servo
    t             connection event k carries the state notification to the phone
    t + ~2 ms     the app takes the newest CoreMotion sample and runs the policy
    t + T         connection event k+1 carries the command to the MCU, or event
                  k+2 if the packet was lost and retransmitted
    t + T + w     the MCU Sync Writes the goals and the servos pick them up

In the simulator the observation is taken at the start of a control step, so
the servo telemetry is `read` old and the command lands T + w later. iOS has
been seen to stall BLE callbacks for ~250 ms every few seconds; during a stall
the MCU keeps the last goal, which the servo model holds.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch


@dataclass
class LinkCfg:
    interval_s: float = 0.015  # BLE connection interval and control period
    write_s: tuple[float, float] = (0.0005, 0.003)  # MCU Sync Write and servo pickup after the event
    late_probability: float = 0.03  # a command misses its event and goes one interval later
    read_s: tuple[float, float] = (0.0005, 0.004)  # Fast Sync Read ahead of the notification
    max_delay_s: float = 0.06  # sizes the command delay buffer
    stall_rate_hz: float = 0.05  # how often the phone goes quiet
    stall_s: tuple[float, float] = (0.05, 0.25)


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
    base = link.interval_s + _uniform(link.write_s, len(ids), env.device)
    actuator.command_lag[ids] = _steps(env, base)
    actuator.telemetry_age[ids] = _steps(env, _uniform(link.read_s, len(ids), env.device))
    actuator.set_lags(actuator.command_lag[ids], ids)


def late_commands(env, env_ids: torch.Tensor | None, link: LinkCfg) -> None:
    """Step event: some commands arrive one connection interval late, and now and
    then the phone goes quiet and the MCU holds the last goal."""
    del env_ids
    actuator = servos(env)
    late = torch.rand(env.num_envs, device=env.device) < link.late_probability
    interval = round(link.interval_s / env.physics_dt)
    actuator.set_lags(actuator.command_lag + late.long() * interval)
    start = (torch.rand(env.num_envs, device=env.device) < link.stall_rate_hz * env.step_dt) & (actuator.stall == 0)
    length = _steps(env, _uniform(link.stall_s, env.num_envs, env.device))
    actuator.stall[:] = torch.where(start, length, actuator.stall)


def delay_settings(link: LinkCfg, physics_dt: float) -> dict:
    """Actuator delay-buffer settings: lags are set only by the events above."""
    return dict(delay_min_lag=0, delay_max_lag=round(link.max_delay_s / physics_dt), delay_hold_prob=1.0)
