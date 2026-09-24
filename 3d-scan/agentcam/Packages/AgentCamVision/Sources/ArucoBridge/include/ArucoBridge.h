// C interface over OpenCV's ArucoDetector and planar PnP.
//
// Plain C on purpose: Swift imports it directly, no C++ type crosses the
// boundary, and no Foundation header ends up in the same translation unit as
// OpenCV (whose headers collide with Objective-C's YES/NO macros).

#ifndef ARUCO_BRIDGE_H
#define ARUCO_BRIDGE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    ACFamilyAruco4x4_100 = 0,
    ACFamilyAprilTag36h11 = 1,
} ACFamily;

/// One detected marker. Corners are in pixels, in the marker's own order
/// (TL, TR, BR, BL as printed). Pixel coordinates follow OpenCV everywhere in
/// AgentCam: (0, 0) is the center of the top-left pixel.
typedef struct {
    int32_t id;
    float x[4];
    float y[4];
} ACMarker;

/// One planar pose: camera-from-object, OpenCV camera convention.
/// `r` is a row-major 3x3 rotation.
typedef struct {
    double r[9];
    double t[3];
    double rmsPx;
} ACPlanarPose;

typedef struct ACDetector ACDetector;

ACDetector *ac_detector_create(ACFamily family);
void ac_detector_destroy(ACDetector *detector);

/// Detects markers in an 8-bit grayscale image. Writes at most `capacity`
/// markers to `out` and returns how many were found in total (which may exceed
/// `capacity`), or -1 if OpenCV threw.
int ac_detect(const ACDetector *detector,
              const uint8_t *gray, int width, int height, size_t bytesPerRow,
              ACMarker *out, int capacity);

/// Solves the pose of a planar target (object points on z = 0) with IPPE,
/// refines each solution with Levenberg-Marquardt, and writes both solutions
/// to `out`, lowest reprojection error first. `object` and `image` are `count`
/// interleaved (x, y) pairs; `k` is the row-major 3x3 camera matrix; no lens
/// distortion. Returns the number of solutions written (0 if count < 4 or
/// OpenCV threw).
int ac_solve_planar(const double *object, const double *image, int count,
                    const double *k, ACPlanarPose out[2]);

/// The mat's pose from all detected markers, the same algorithm as the
/// server's analysis.solve_mat: RANSAC (AP3P) over every corner; a marker is
/// kept only if all four corners are inliers; the kept markers are refined
/// with IPPE + LM and every marker re-sorted against the refined pose (up to
/// three rounds); of two markers with the same id, the one that fits better
/// stays. `ids` has `markerCount` entries; `object` and `image` have 4 (x, y)
/// pairs per marker. Writes a 0/1 flag per marker to `inliers` and returns the
/// number of solutions in `out` (0-2, lowest error first).
int ac_solve_mat(const int32_t *ids, const double *object, const double *image, int markerCount,
                   const double *k, double thresholdPx, uint8_t *inliers, ACPlanarPose out[2]);

#ifdef __cplusplus
}
#endif

#endif
