"""Protocol models: the source of truth for the wire format.

The app's AgentCamCore/Protocol mirrors these, and both sides decode every file
in agentcam/protocol/examples in their tests. Units are millimetres and degrees;
frames are described in geometry.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROTOCOL_VERSION = 1

Vec3 = tuple[float, float, float]
Mat4 = list[list[float]]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Orbit(Strict):
    azimuth_deg: float = Field(description="Counter-clockwise from +x (the page's right edge) as seen from above.")
    elevation_deg: float = Field(ge=-90, le=90, description="Up from the paper; 90 looks straight down.")
    distance_mm: float = Field(gt=0, description="From look_at to the camera.")


class PoseSpec(Strict):
    look_at: Vec3 = Field((0.0, 0.0, 0.0), description="Page-frame point the camera looks at.")
    orbit: Orbit | None = None
    eye: Vec3 | None = Field(None, description="Camera centre, instead of orbit.")
    hold: Literal["landscape", "portrait"] = Field(
        "landscape", description="landscape: phone top to the left (sensor grid upright); portrait: phone upright.")
    roll_deg: float = Field(0.0, description="About the viewing axis, clockwise as seen from behind the camera.")
    up_hint: Vec3 | None = Field(None, description="World direction that should be image-up. Default +z, or +y looking straight down.")

    @model_validator(mode="after")
    def _one_position(self) -> PoseSpec:
        if (self.orbit is None) == (self.eye is None):
            raise ValueError("give exactly one of orbit or eye")
        return self


class Focus(Strict):
    mode: Literal["auto", "locked", "lens_position"] = Field(
        "auto", description="locked: lock wherever autofocus settles as the shot is taken.")
    lens_position: float | None = Field(None, ge=0, le=1)


class Exposure(Strict):
    mode: Literal["auto", "locked", "custom"] = "auto"
    duration_s: float | None = Field(None, gt=0)
    iso: float | None = Field(None, gt=0)
    bias_ev: float = Field(0.0, ge=-8, le=8)


class WhiteBalance(Strict):
    mode: Literal["auto", "locked", "gains"] = "auto"
    gains: Vec3 | None = None


class CaptureOptions(Strict):
    lens: Literal["wide", "ultrawide", "telephoto"] = Field(
        "wide", description="wide = 1x main; ultrawide = 0.5x, focuses to ~2 cm (macro); telephoto = 5x.")
    resolution: Literal["12mp", "48mp"] = "12mp"
    raw: Literal["none", "bayer", "proraw"] = Field(
        "none", description="bayer: 12 MP DNG of sensor data; proraw: processed DNG up to 48 MP. A JPEG is always delivered too.")
    flash: Literal["off", "on"] = "off"
    torch: float = Field(0.0, ge=0, le=1, description="Steady light level while aligning and capturing.")
    depth: Literal["none", "arkit", "lidar_photo"] = Field(
        "none", description="arkit: 256x192 LiDAR depth + confidence; lidar_photo: 768x576, wide lens only.")
    focus: Focus = Focus()
    exposure: Exposure = Exposure()
    white_balance: WhiteBalance = WhiteBalance()
    distortion_correction: bool = Field(False, description="Apple's geometric distortion correction; off keeps a plain lens model.")
    path: Literal["auto", "fast", "full"] = "auto"

    def needs_full_path(self) -> bool:
        """Anything the ARKit camera can't do means leaving AR for the shot."""
        return (self.path == "full" or self.lens != "wide" or self.resolution == "48mp" or self.raw != "none"
                or self.flash == "on" or self.depth == "lidar_photo")

    @model_validator(mode="after")
    def _consistent(self) -> CaptureOptions:
        if self.depth == "lidar_photo" and self.lens != "wide":
            raise ValueError("lidar_photo depth is only available with the wide lens")
        if self.path == "fast" and self.needs_full_path():
            raise ValueError("these options need the full capture path (lens, 48mp, raw, flash or lidar_photo)")
        return self


class Tolerance(Strict):
    position_mm: float | None = Field(None, gt=0, description="Default max(8, 3% of distance).")
    pointing_deg: float = Field(3.0, gt=0)
    roll_deg: float = Field(10.0, gt=0)
    steady_s: float = Field(0.5, ge=0)
    max_speed_mm_s: float = Field(10.0, gt=0)
    max_ang_speed_deg_s: float = Field(1.5, gt=0)


class Placement(Strict):
    label: str = Field(description="Short name for how the object sits, e.g. 'upright' or 'flipped'.")
    instruction: str = Field(description="Shown to the user, who confirms before this request's guidance starts.")


class PhotoRequestSpec(Strict):
    """What the agent asks for."""
    kind: Literal["pose", "free", "freeform"] = Field(
        "pose", description="free: no target; the user frames the shot, which is taken once the phone is held still. "
                            "freeform: no target or hold; taken as soon as the whole page is in view with the phone "
                            "steady (tolerance max_speed_mm_s and max_ang_speed_deg_s), e.g. for a first look at what's "
                            "on it.")
    pose: PoseSpec | None = None
    options: CaptureOptions = CaptureOptions()
    tolerance: Tolerance = Tolerance()
    placement: Placement | None = None
    note: str = Field("", description="Shown to the user with the request, e.g. 'close-up of the latch'.")

    @model_validator(mode="after")
    def _pose_for_pose_kind(self) -> PhotoRequestSpec:
        if self.kind == "pose" and self.pose is None:
            raise ValueError("kind 'pose' needs a pose")
        if self.kind != "pose" and self.pose is not None:
            raise ValueError(f"kind {self.kind!r} takes no pose")
        return self


class Target(Strict):
    camera_to_page: Mat4
    eye: Vec3
    look_at: Vec3
    distance_mm: float
    position_tolerance_mm: float


RequestState = Literal["queued", "captured", "skipped", "cancelled"]


class PhotoRequest(PhotoRequestSpec):
    """A stored request, as the phone and list_requests see it."""
    id: str
    seq: int
    state: RequestState = "queued"
    created_at: str
    updated_at: str
    target: Target | None = None
    preflight: list[str] = []
    capture_ids: list[str] = []
    skip_reason: str | None = None


class BoardInfo(Strict):
    dictionary: str = "DICT_4X4_100"
    print_scale: tuple[float, float] = (1.0, 1.0)


# ---- Phone <-> server messages (WebSocket /v1/ws, JSON text frames) ----------

class LensInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: Literal["wide", "ultrawide", "telephoto"]
    fov_deg: tuple[float, float] | None = None      # horizontal, vertical on the sensor grid
    min_focus_mm: float | None = None


class Hello(BaseModel):
    model_config = ConfigDict(extra="allow")
    t: Literal["hello"]
    v: int
    device: dict = {}
    lenses: list[LensInfo] = []
    lidar: bool = False
    app_state: Literal["foreground", "background"] = "foreground"


class RequestUpdate(Strict):
    t: Literal["request_update"]
    v: int = PROTOCOL_VERSION
    id: str
    state: Literal["skipped"]
    reason: str = ""


class CaptureFile(Strict):
    name: str
    sha256: str
    bytes: int


class CaptureImage(BaseModel):
    model_config = ConfigDict(extra="allow")
    file: str
    w: int
    h: int
    grid: Literal["sensor"] = "sensor"
    upright_rotation_cw_deg: Literal[0, 90, 180, 270] = 0


class Intrinsics(BaseModel):
    model_config = ConfigDict(extra="allow")
    K: list[list[float]]
    source: str
    ref_dims: tuple[int, int]


class CapturePose(BaseModel):
    model_config = ConfigDict(extra="allow")
    camera_to_page: Mat4 | None
    source: Literal["arkit_live", "arkit_held", "none"]


class CaptureMetadata(BaseModel):
    """Body of POST .../commit. Only these fields are checked; the rest (lens,
    exposure, tracking, depth, bracket...) is stored as sent."""
    model_config = ConfigDict(extra="allow")
    capture_id: str
    request_id: str
    captured_at: str
    path: Literal["fast", "full"]
    files: list[CaptureFile]
    image: CaptureImage
    intrinsics: Intrinsics
    pose: CapturePose
