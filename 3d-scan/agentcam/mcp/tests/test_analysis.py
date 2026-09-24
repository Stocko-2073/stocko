import json

import cv2
import numpy as np
import pytest

from agentcam import analysis, fakephone
from agentcam.mat import MatLayout
from agentcam.geometry import look_at_pose, orbit_eye, pose_difference
from conftest import PROTOCOL

FIXTURES = PROTOCOL / "fixtures"


@pytest.fixture(scope="module")
def mat():
    return MatLayout.load()


@pytest.fixture(scope="module")
def raster():
    return fakephone.mat_raster()


@pytest.mark.parametrize("az,el,d,hold", [(-90, 55, 380, "landscape"), (0, 35, 330, "portrait"),
                                          (135, 70, 300, "landscape"), (-90, 90, 400, "portrait"),
                                          (45, 25, 250, "landscape")])
def test_still_pose_matches_the_render(mat, raster, az, el, d, hold):
    truth = look_at_pose(orbit_eye((0, 0, 0), az, el, d), (0, 0, 0), hold)
    img = fakephone.render(truth, raster, rng=np.random.default_rng(0))
    corners, ids, _ = mat.detector().detectMarkers(img)
    fit = analysis.solve_mat(mat, ids, np.array(corners).reshape(-1, 4, 2), fakephone.K)
    assert fit.inliers.all()
    dt, dr = pose_difference(fit.choose().camera_to_mat, truth)
    assert dt < 0.5 and dr < 0.1


def test_one_edge_is_enough(mat, raster):
    """Close to one edge only the markers along it are visible: nearly collinear
    marker centers, which a homography over centers can't handle."""
    truth = look_at_pose(orbit_eye((0, 125, 0), -90, 50, 140), (0, 125, 0))
    img = fakephone.render(truth, raster, rng=np.random.default_rng(0))
    corners, ids, _ = mat.detector().detectMarkers(img)
    assert 4 <= len(ids) and all(0 <= i < 16 for i in ids.ravel())      # top row only
    fit = analysis.solve_mat(mat, ids, np.array(corners).reshape(-1, 4, 2), fakephone.K)
    dt, dr = pose_difference(fit.choose(prior=truth).camera_to_mat, truth)
    assert dt < 2 and dr < 0.5


def test_a_misplaced_marker_is_rejected(mat, raster):
    truth = look_at_pose(orbit_eye((0, 0, 0), -90, 55, 380), (0, 0, 0))
    img = fakephone.render(truth, raster, rng=np.random.default_rng(0))
    corners, ids, _ = mat.detector().detectMarkers(img)
    corners = np.array(corners).reshape(-1, 4, 2)
    # A false positive: a second marker 17 somewhere off the mat.
    ids = np.r_[ids.ravel(), 17]
    corners = np.r_[corners, corners[:1] + [300, 900]]
    fit = analysis.solve_mat(mat, ids, corners, fakephone.K)
    assert fit.inliers.sum() == len(ids) - 1 and not fit.inliers[-1]


def test_the_real_photo(mat):
    """The phone photo of the printed mat: 70 markers plus a false 17 on wood grain."""
    ref = json.loads((FIXTURES / "aruco_border.json").read_text())
    k = np.array(ref["K"])
    a = analysis.analyze(FIXTURES / "aruco_border.jpeg", mat, k, None)
    assert a["markers_detected"] == 71 and a["markers_used"] == 70 and a["markers_rejected"] == [17]
    assert a["pnp"]["rms_px"] < 8                                       # a curled mat, no lens model
    dt, dr = pose_difference(np.array(a["pnp"]["camera_to_mat"]), np.array(ref["camera_to_mat"]))
    assert dt < 1e-3 and dr < 1e-4


def test_preview_is_upright_and_maps_back(tmp_path, mat, raster):
    truth = look_at_pose(orbit_eye((0, 0, 0), 0, 35, 330), (0, 0, 0), "portrait")
    path = tmp_path / "image.jpg"
    cv2.imwrite(str(path), fakephone.render(truth, raster))
    info = analysis.write_preview(path, tmp_path / "preview.jpg", 90, px=800)
    assert info["size"] == [600, 800]                                   # portrait after turning
    m = np.array(info["preview_to_full"])
    # The preview's top-left maps to the full image's bottom-left for a 90 deg turn.
    np.testing.assert_allclose((m @ [0, 0, 1])[:2], [0, fakephone.HEIGHT - 1], atol=2)
