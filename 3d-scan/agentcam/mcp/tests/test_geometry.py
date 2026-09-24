import json

import numpy as np
import pytest

from agentcam.geometry import look_at_pose, orbit_eye, rotation_matrix_cw, upright_rotation_cw_deg
from agentcam.models import PoseSpec
from agentcam.resolve import resolve_pose
from conftest import PROTOCOL


def axes(t):
    return t[:3, 0], t[:3, 1], t[:3, 2]


def test_orbit_puts_the_camera_where_the_angles_say():
    np.testing.assert_allclose(orbit_eye((0, 0, 0), 0, 0, 100), [100, 0, 0], atol=1e-9)
    np.testing.assert_allclose(orbit_eye((0, 0, 0), 90, 0, 100), [0, 100, 0], atol=1e-9)
    np.testing.assert_allclose(orbit_eye((10, 0, 5), 0, 90, 100), [10, 0, 105], atol=1e-9)


def test_landscape_keeps_world_up_at_the_top_of_the_image():
    t = look_at_pose(orbit_eye((0, 0, 0), -90, 30, 300), (0, 0, 0), "landscape")
    x, y, z = axes(t)
    assert y[2] < 0                                 # image down points down in the world
    np.testing.assert_allclose(x, [1, 0, 0], atol=1e-9)   # from the bottom edge, +x is to the right
    np.testing.assert_allclose(np.cross(x, y), z, atol=1e-9)


def test_portrait_puts_world_up_along_minus_x():
    t = look_at_pose(orbit_eye((0, 0, 0), -90, 30, 300), (0, 0, 0), "portrait")
    x, y, z = axes(t)
    assert x[2] < 0 and abs(y[2]) < 1e-9
    assert upright_rotation_cw_deg(t) == 90


def test_straight_down_takes_up_from_the_page_top():
    t = look_at_pose((0, 0, 400), (0, 0, 0), "landscape")
    x, y, z = axes(t)
    np.testing.assert_allclose(z, [0, 0, -1], atol=1e-9)
    np.testing.assert_allclose(y, [0, -1, 0], atol=1e-9)   # image up = page top (+y)
    assert upright_rotation_cw_deg(t) == 0


def test_roll_turns_about_the_viewing_axis():
    base = look_at_pose(orbit_eye((0, 0, 0), -90, 30, 300), (0, 0, 0))
    rolled = look_at_pose(orbit_eye((0, 0, 0), -90, 30, 300), (0, 0, 0), roll_deg=90)
    np.testing.assert_allclose(rolled[:3, 2], base[:3, 2], atol=1e-9)
    np.testing.assert_allclose(rolled[:3, 0], base[:3, 1], atol=1e-9)   # x turns toward y
    # Rolled clockwise, world up lands on the image's left: turn 90 cw to view.
    assert upright_rotation_cw_deg(rolled) == 90


@pytest.mark.parametrize("deg", [0, 90, 180, 270])
def test_pixel_rotation_matches_numpy(deg):
    w, h = 5, 3
    img = np.arange(w * h).reshape(h, w)
    rotated = np.rot90(img, k=-deg // 90)
    m = rotation_matrix_cw(deg, w, h)
    for yy in range(h):
        for xx in range(w):
            u, v, _ = m @ [xx, yy, 1]
            assert rotated[int(v), int(u)] == img[yy, xx]


def test_shared_pose_examples_still_resolve_the_same():
    """agentcam/protocol/examples/pose_specs.json is also checked by the Swift tests."""
    examples = json.loads((PROTOCOL / "examples" / "pose_specs.json").read_text())
    assert len(examples) >= 6
    for ex in examples:
        t, eye, distance = resolve_pose(PoseSpec.model_validate(ex["spec"]))
        np.testing.assert_allclose(t, ex["camera_to_page"], atol=1e-6, err_msg=ex["name"])
        assert upright_rotation_cw_deg(t) == ex["upright_rotation_cw_deg"], ex["name"]
