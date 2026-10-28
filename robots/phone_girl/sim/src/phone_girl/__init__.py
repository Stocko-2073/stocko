"""phone_girl simulation: CAD-derived MuJoCo model, BAM XL330 servos, iPhone
sensors, BLE link timing and domain randomization for mjlab on MuJoCo Warp."""

from pathlib import Path

import numpy as np

PACKAGE = Path(__file__).resolve().parent
ASSETS = PACKAGE / "assets"
MJCF = PACKAGE / "phone_girl.xml"
ROBOT_DIR = PACKAGE.parents[2]  # robots/phone_girl
CAD = ROBOT_DIR / "phone_girl.scad"
# CAD (+Y back) to simulation (+X forward, +Y left, +Z up).
CAD_TO_SIM = np.array([[0., -1, 0], [1, 0, 0], [0, 0, 1]])

# Importing mjlab loads phone_girl.tasks through its entry point. Doing it here,
# after the paths above, means that happens before any other phone_girl module
# starts importing, whichever module is imported first.
import mjlab  # noqa: E402,F401
