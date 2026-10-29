"""The iPhone's motion sensors and cameras as the phone app will see them.

The IMU follows CoreMotion: CMDeviceMotion.gravity (unit vector, g), rotationRate
(rad/s) and the raw accelerometer (g, reading (0, 0, -1) face up at rest), all
in the device frame: x right and y up the screen in portrait, z out of the
screen. The model's `imu` site carries that frame.

Samples are taken every physics step, as the hardware does, but the app only
gets them at CoreMotion's rate and after its latency, and the phone sits in the
chest pocket slightly askew. Noise, biases, mount tilt, latency and sample phase
are drawn per episode; the defaults are deliberately generous estimates until
they are measured on the robot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

import mujoco
import mujoco_warp as mjwarp
import torch

from mjlab.sensor import CameraSensorCfg
from mjlab.sensor.sensor import Sensor, SensorCfg
from mjlab.utils.lab_api.math import matrix_from_quat, normalize, quat_from_angle_axis

GRAVITY = 9.81


def random_tilt(count: int, limit: float, device) -> torch.Tensor:
    """Rotations about random horizontal-or-not axes, angle uniform in [0, limit]."""
    axis = normalize(torch.randn(count, 3, device=device))
    angle = torch.rand(count, device=device) * limit
    return matrix_from_quat(quat_from_angle_axis(angle, axis))


@dataclass
class PhoneImuCfg(SensorCfg):
    name: str = "phone_imu"
    entity: str = "robot"
    rate_hz: float = 100.0  # CoreMotion deviceMotion
    latency_s: tuple[float, float] = (0.005, 0.025)  # sample to app, per episode
    history_s: float = 0.06
    gyro_noise: float = 0.005  # rad/s, per sample
    gyro_bias: float = 0.01  # rad/s, per axis, per episode
    gravity_noise: float = 0.003  # per sample, unit vector
    gravity_tilt: float = math.radians(1.0)  # sensor-fusion attitude error, per episode
    accel_noise: float = 0.01  # g, per sample
    accel_bias: float = 0.02  # g, per axis, per episode
    mount_tilt: float = math.radians(2.0)  # phone seated askew in the chest pocket
    compile: bool = True  # on CUDA, fuse each physics step's ~30 small kernels into a few

    def build(self) -> PhoneImu:
        return PhoneImu(self)


class PhoneImu(Sensor[dict]):
    """CoreMotion-like gravity, rotation rate and acceleration with per-episode errors."""

    def __init__(self, cfg: PhoneImuCfg) -> None:
        super().__init__()
        self.cfg = cfg

    def edit_spec(self, scene_spec: mujoco.MjSpec, entities: dict) -> None:
        del scene_spec, entities  # the robot MJCF defines the imu site and its sensors

    def initialize(self, mj_model: mujoco.MjModel, model: mjwarp.Model, data: mjwarp.Data, device: str) -> None:
        def view(name):
            sensor = mj_model.sensor(f"{self.cfg.entity}/{name}")
            return data.sensordata[:, sensor.adr[0]:sensor.adr[0] + sensor.dim[0]]

        self._gyro, self._accel, self._quat = view("imu_gyro"), view("imu_accel"), view("imu_quat")
        self._down = torch.tensor([0.0, 0.0, -1.0], device=device)
        dt = mj_model.opt.timestep
        n = data.nworld
        self.device = device
        self.period = max(1, round(1 / (self.cfg.rate_hz * dt)))
        self.latency_range = tuple(round(t / dt) for t in self.cfg.latency_s)
        steps = max(round(self.cfg.history_s / dt), self.latency_range[1] + self.period + 1)
        self._ring = torch.zeros((steps, n, 9), device=device)
        self._head = 0
        self._count = torch.zeros(n, dtype=torch.long, device=device)
        self.latency = torch.zeros(n, dtype=torch.long, device=device)
        self.phase = torch.zeros(n, dtype=torch.long, device=device)
        self.mount = torch.eye(3, device=device).repeat(n, 1, 1)
        self.fusion = torch.eye(3, device=device).repeat(n, 1, 1)
        self.gyro_bias = torch.zeros(n, 3, device=device)
        self.accel_bias = torch.zeros(n, 3, device=device)
        self._arange = torch.arange(n, device=device)
        if self.cfg.compile and device.startswith("cuda"):
            self._measure = torch.compile(self._measure)
        self.reset()

    def _measure(self) -> torch.Tensor:
        """This physics step's readings, with errors, as (envs, 9): gravity, gyro, accel."""
        cfg, n = self.cfg, self._arange.numel()
        world_to_site = matrix_from_quat(self._quat[...]).transpose(1, 2)
        true_gravity = torch.einsum("nij,j->ni", world_to_site, self._down)
        gravity = torch.einsum("nij,nj->ni", self.fusion @ self.mount, true_gravity)
        gravity = normalize(gravity + cfg.gravity_noise * torch.randn(n, 3, device=self.device))
        gyro = torch.einsum("nij,nj->ni", self.mount, self._gyro[...]) + self.gyro_bias \
            + cfg.gyro_noise * torch.randn(n, 3, device=self.device)
        # MuJoCo's accelerometer gives specific force; CoreMotion reports its negative, in g.
        accel = -torch.einsum("nij,nj->ni", self.mount, self._accel[...]) / GRAVITY + self.accel_bias \
            + cfg.accel_noise * torch.randn(n, 3, device=self.device)
        return torch.cat((gravity, gyro, accel), dim=-1)

    def update(self, dt: float) -> None:
        super().update(dt)
        self._ring[self._head] = self._measure()
        self._head = (self._head + 1) % self._ring.shape[0]
        self._count += 1

    def _compute_data(self) -> dict:
        # The app holds the newest CoreMotion sample at least `latency` old; samples
        # are `period` steps apart starting at a per-episode phase.
        held = self._count - self.latency
        age = self.latency + torch.remainder(held - self.phase, self.period)
        age = torch.minimum(age, self._count - 1).clamp(min=0)
        index = (self._head - 1 - age) % self._ring.shape[0]
        sample = torch.where((self._count > 0)[:, None], self._ring[index, self._arange], self._measure())
        return dict(gravity=sample[:, :3], gyro=sample[:, 3:6], accel=sample[:, 6:])

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        super().reset(env_ids)
        if not hasattr(self, "_ring"):
            return
        ids = self._arange[slice(None) if env_ids is None else env_ids]
        n, cfg = ids.numel(), self.cfg
        self._count[ids] = 0
        self.latency[ids] = torch.randint(self.latency_range[0], self.latency_range[1] + 1, (n,), device=self.device)
        self.phase[ids] = torch.randint(0, self.period, (n,), device=self.device)
        self.mount[ids] = random_tilt(n, cfg.mount_tilt, self.device)
        self.fusion[ids] = random_tilt(n, cfg.gravity_tilt, self.device)
        self.gyro_bias[ids] = (2 * torch.rand(n, 3, device=self.device) - 1) * cfg.gyro_bias
        self.accel_bias[ids] = (2 * torch.rand(n, 3, device=self.device) - 1) * cfg.accel_bias


# Phone cameras defined in the MJCF, with resolutions small enough to render for
# thousands of environments. The TrueDepth camera faces forward, the rear ones back.
CAMERAS = ("front", "rear_main", "rear_ultrawide", "rear_tele")


def camera(name: str = "front", width: int = 48, height: int = 64,
           data_types: tuple[str, ...] = ("rgb",), **kwargs) -> CameraSensorCfg:
    """A phone camera as an mjlab camera sensor, portrait like the robot holds it."""
    if name not in CAMERAS:
        raise ValueError(f"Unknown phone camera {name}; choose from {CAMERAS}")
    return CameraSensorCfg(name=f"{name}_camera", camera_name=f"robot/{name}", width=width, height=height,
                           data_types=data_types, **kwargs)


class held_frames:
    """Observation term: the newest frame the app has from a phone camera, (B, C, H, W).

    The camera sensor renders every control step, but frames reach the app at the
    camera's frame rate and `latency_s` late, so a policy sees each frame for
    several steps. RGB is kept as bytes and depth as half floats to save memory.
    Params: sensor_name, kind ("rgb" or "depth"), fps, latency_s, depth_cutoff (m).
    """

    def __init__(self, cfg, env):
        params = cfg.params
        step = env.step_dt
        self.period = max(1, round(1 / (params.get("fps", 30.0) * step)))
        self.latency = tuple(round(t / step) for t in params.get("latency_s", (0.03, 0.05)))
        self.size = self.latency[1] + self.period + 1
        self.device = env.device
        self.arange = torch.arange(env.num_envs, device=env.device)
        self.count = torch.zeros(env.num_envs, dtype=torch.long, device=env.device)
        self.lag = torch.zeros_like(self.count)
        self.phase = torch.zeros_like(self.count)
        self.ring = None
        self.head, self.last_step = 0, -1
        self.reset()

    def reset(self, env_ids=None):
        ids = self.arange[slice(None) if env_ids is None else env_ids]
        self.count[ids] = 0
        self.lag[ids] = torch.randint(self.latency[0], self.latency[1] + 1, (ids.numel(),), device=self.device)
        self.phase[ids] = torch.randint(0, self.period, (ids.numel(),), device=self.device)

    def __call__(self, env, sensor_name: str, kind: str = "rgb", fps: float = 30.0,
                 latency_s: tuple[float, float] = (0.03, 0.05), depth_cutoff: float = 3.0) -> torch.Tensor:
        data = env.scene[sensor_name].data
        frame = data.rgb if kind == "rgb" else data.depth.half()
        if self.ring is None:
            self.ring = torch.zeros((self.size, *frame.shape), dtype=frame.dtype, device=self.device)
        if env.common_step_counter != self.last_step:  # one frame per control step
            self.ring[self.head] = frame
            self.head = (self.head + 1) % self.size
            self.count += 1
            self.last_step = env.common_step_counter
        age = self.lag + torch.remainder(self.count - self.lag - self.phase, self.period)
        age = torch.minimum(age, self.count - 1).clamp(min=0)
        held = self.ring[(self.head - 1 - age) % self.size, self.arange]
        held = torch.where((self.count > 0)[:, None, None, None], held, frame)
        held = held.permute(0, 3, 1, 2).float()
        return held / 255.0 if kind == "rgb" else (held.clamp(0.01, depth_cutoff) / depth_cutoff)


def with_camera(cfg, name: str = "front", width: int = 48, height: int = 64, kind: str = "depth",
                fps: float = 30.0, latency_s: tuple[float, float] = (0.03, 0.05)):
    """Add a phone camera to an environment as a separate "camera" observation group.

    Train with obs_groups {"actor": ("actor", "camera"), "critic": ("critic", "camera")}
    and a cnn_cfg, as mjlab's vision manipulation tasks do.
    """
    from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg

    sensor = camera(name, width, height, (kind,))
    cfg.scene.sensors = tuple(cfg.scene.sensors or ()) + (sensor,)
    term = ObservationTermCfg(func=held_frames, params=dict(sensor_name=sensor.name, kind=kind, fps=fps,
                                                            latency_s=latency_s))
    cfg.observations["camera"] = ObservationGroupCfg(terms={name: term}, concatenate_terms=True,
                                                     enable_corruption=False)
    return cfg
