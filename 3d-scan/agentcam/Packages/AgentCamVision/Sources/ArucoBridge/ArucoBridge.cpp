#include "ArucoBridge.h"

#include <algorithm>
#include <cmath>
#include <vector>

#include <opencv2/calib3d.hpp>
#include <opencv2/core.hpp>
#include <opencv2/objdetect/aruco_detector.hpp>

struct ACDetector {
    cv::aruco::ArucoDetector detector;
};

ACDetector *ac_detector_create(ACFamily family) {
    const auto dictionary = cv::aruco::getPredefinedDictionary(
        family == ACFamilyAprilTag36h11 ? cv::aruco::DICT_APRILTAG_36h11 : cv::aruco::DICT_4X4_100);
    cv::aruco::DetectorParameters params;
    // Must match the server (agentcam/mcp analysis.py), so phone and Mac agree.
    params.cornerRefinementMethod = cv::aruco::CORNER_REFINE_SUBPIX;
    try {
        return new ACDetector{cv::aruco::ArucoDetector(dictionary, params)};
    } catch (...) {
        return nullptr;
    }
}

void ac_detector_destroy(ACDetector *detector) { delete detector; }

int ac_detect(const ACDetector *detector,
              const uint8_t *gray, int width, int height, size_t bytesPerRow,
              ACMarker *out, int capacity) {
    if (detector == nullptr || gray == nullptr) return -1;
    // Wraps the caller's buffer; nothing is copied.
    const cv::Mat image(height, width, CV_8UC1, const_cast<uint8_t *>(gray), bytesPerRow);
    std::vector<std::vector<cv::Point2f>> corners;
    std::vector<int> ids;
    try {
        detector->detector.detectMarkers(image, corners, ids);
    } catch (...) {
        return -1;
    }
    const int n = std::min(static_cast<int>(ids.size()), capacity);
    for (int i = 0; i < n; ++i) {
        out[i].id = ids[i];
        for (int k = 0; k < 4; ++k) {
            out[i].x[k] = corners[i][k].x;
            out[i].y[k] = corners[i][k].y;
        }
    }
    return static_cast<int>(ids.size());
}

int ac_solve_planar(const double *object, const double *image, int count,
                    const double *k, ACPlanarPose out[2]) {
    if (count < 4 || object == nullptr || image == nullptr || k == nullptr) return 0;
    std::vector<cv::Point3d> objectPoints(count);
    std::vector<cv::Point2d> imagePoints(count);
    for (int i = 0; i < count; ++i) {
        objectPoints[i] = {object[2 * i], object[2 * i + 1], 0.0};
        imagePoints[i] = {image[2 * i], image[2 * i + 1]};
    }
    const cv::Mat camera = cv::Mat(3, 3, CV_64F, const_cast<double *>(k)).clone();
    try {
        std::vector<cv::Mat> rvecs, tvecs;
        cv::solvePnPGeneric(objectPoints, imagePoints, camera, cv::noArray(), rvecs, tvecs,
                            false, cv::SOLVEPNP_IPPE);
        std::vector<ACPlanarPose> poses;
        for (size_t s = 0; s < rvecs.size() && s < 2; ++s) {
            cv::Mat rvec = rvecs[s], tvec = tvecs[s];
            cv::solvePnPRefineLM(objectPoints, imagePoints, camera, cv::noArray(), rvec, tvec);
            std::vector<cv::Point2d> projected;
            cv::projectPoints(objectPoints, rvec, tvec, camera, cv::noArray(), projected);
            double sum = 0;
            for (int i = 0; i < count; ++i) {
                const cv::Point2d d = projected[i] - imagePoints[i];
                sum += d.dot(d);
            }
            cv::Mat rotation;
            cv::Rodrigues(rvec, rotation);
            ACPlanarPose pose{};
            for (int i = 0; i < 9; ++i) pose.r[i] = rotation.at<double>(i / 3, i % 3);
            for (int i = 0; i < 3; ++i) pose.t[i] = tvec.at<double>(i);
            pose.rmsPx = std::sqrt(sum / count);
            poses.push_back(pose);
        }
        std::sort(poses.begin(), poses.end(),
                  [](const ACPlanarPose &a, const ACPlanarPose &b) { return a.rmsPx < b.rmsPx; });
        for (size_t s = 0; s < poses.size(); ++s) out[s] = poses[s];
        return static_cast<int>(poses.size());
    } catch (...) {
        return 0;
    }
}

namespace {

struct Marker {
    int id;
    std::vector<cv::Point3d> object;
    std::vector<cv::Point2d> image;
};

std::vector<ACPlanarPose> solveMarkers(const std::vector<Marker> &markers, const std::vector<bool> &use,
                                       const cv::Mat &camera) {
    std::vector<double> object, image;
    int count = 0;
    for (size_t i = 0; i < markers.size(); ++i) {
        if (!use[i]) continue;
        for (int c = 0; c < 4; ++c) {
            object.push_back(markers[i].object[c].x);
            object.push_back(markers[i].object[c].y);
            image.push_back(markers[i].image[c].x);
            image.push_back(markers[i].image[c].y);
        }
        count += 4;
    }
    ACPlanarPose out[2];
    const int n = ac_solve_planar(object.data(), image.data(), count, camera.ptr<double>(), out);
    return std::vector<ACPlanarPose>(out, out + n);
}

double maxCornerError(const Marker &m, const ACPlanarPose &pose, const cv::Mat &camera) {
    const cv::Mat r(3, 3, CV_64F, const_cast<double *>(pose.r));
    cv::Mat rvec;
    cv::Rodrigues(r, rvec);
    const cv::Mat tvec(3, 1, CV_64F, const_cast<double *>(pose.t));
    std::vector<cv::Point2d> projected;
    cv::projectPoints(m.object, rvec, tvec, camera, cv::noArray(), projected);
    double worst = 0;
    for (int c = 0; c < 4; ++c) worst = std::max(worst, cv::norm(projected[c] - m.image[c]));
    return worst;
}

}  // namespace

int ac_solve_mat(const int32_t *ids, const double *object, const double *image, int markerCount,
                   const double *k, double thresholdPx, uint8_t *inliers, ACPlanarPose out[2]) {
    if (markerCount < 1 || ids == nullptr || object == nullptr || image == nullptr || k == nullptr) return 0;
    try {
        const cv::Mat camera = cv::Mat(3, 3, CV_64F, const_cast<double *>(k)).clone();
        std::vector<Marker> markers(markerCount);
        std::vector<cv::Point3d> allObject;
        std::vector<cv::Point2d> allImage;
        for (int i = 0; i < markerCount; ++i) {
            markers[i].id = ids[i];
            for (int c = 0; c < 4; ++c) {
                const int j = 4 * i + c;
                markers[i].object.push_back({object[2 * j], object[2 * j + 1], 0.0});
                markers[i].image.push_back({image[2 * j], image[2 * j + 1]});
                allObject.push_back(markers[i].object.back());
                allImage.push_back(markers[i].image.back());
            }
        }
        std::vector<bool> use(markerCount, markerCount == 1);
        if (markerCount > 1) {
            cv::Mat rvec, tvec;
            std::vector<int> cornerInliers;
            if (cv::solvePnPRansac(allObject, allImage, camera, cv::noArray(), rvec, tvec, false, 200,
                                   static_cast<float>(thresholdPx), 0.999, cornerInliers, cv::SOLVEPNP_AP3P)) {
                std::vector<int> perMarker(markerCount, 0);
                for (int c : cornerInliers) perMarker[c / 4] += 1;
                for (int i = 0; i < markerCount; ++i) use[i] = perMarker[i] == 4;
            }
        }
        if (std::none_of(use.begin(), use.end(), [](bool b) { return b; })) return 0;

        // RANSAC's inliers come from its best minimal sample; re-sort every
        // marker against the refined pose.
        std::vector<ACPlanarPose> solutions;
        for (int round = 0; round < 3; ++round) {
            solutions = solveMarkers(markers, use, camera);
            if (solutions.empty()) return 0;
            std::vector<bool> again(markerCount);
            for (int i = 0; i < markerCount; ++i) again[i] = maxCornerError(markers[i], solutions[0], camera) < thresholdPx;
            if (std::none_of(again.begin(), again.end(), [](bool b) { return b; }) || again == use) break;
            use = again;
        }

        // Two copies of one id can't both be on the mat; keep the one that fits.
        bool changed = false;
        for (int i = 0; i < markerCount; ++i) {
            if (!use[i]) continue;
            for (int j = i + 1; j < markerCount; ++j) {
                if (!use[j] || ids[j] != ids[i]) continue;
                changed = true;
                if (maxCornerError(markers[i], solutions[0], camera) <= maxCornerError(markers[j], solutions[0], camera)) {
                    use[j] = false;
                } else {
                    use[i] = false;
                    break;
                }
            }
        }
        if (changed) solutions = solveMarkers(markers, use, camera);
        for (int i = 0; i < markerCount; ++i) inliers[i] = use[i] ? 1 : 0;
        for (size_t s = 0; s < solutions.size() && s < 2; ++s) out[s] = solutions[s];
        return static_cast<int>(std::min<size_t>(solutions.size(), 2));
    } catch (...) {
        return 0;
    }
}
