# AgentCam TODO

Phases 0–4 are done: OpenCV packaging, server and fake phone, thin app, page lock, guidance and
automatic capture. They were checked on the iPhone 16 Pro over three sessions, 9 photos in all.
Phone vs still-PnP poses agreed within 0.3–1.2 mm / 0.05–0.22°, and 2.8 mm / 0.7° for one side view
with 20 markers. What's left, in order.

## Phase 5: capture options that leave AR (the "full path")

Requests that need these show "Can't do this one yet" today.

- [ ] **Probe first**, on a debug screen:
  - [ ] Does `captureHighResolutionFrame(using:)` (iOS 26) honour `flashMode` or larger
    `maxPhotoDimensions`? If flash works there, it can stay on the fast path.
  - [ ] Time the AR pause → AVCaptureSession shot → AR resume, and record the tracking-state
    timeline. The plan assumes 1–2.5 s.
  - [ ] Check `AVCaptureDevice.extrinsicMatrix(from:to:)` for wide → ultra-wide and wide → tele:
    non-nil, and its units and direction.
- [ ] `Capture/AVPhotoSession`:
  - [ ] One physical lens per shot (`builtInWideAngleCamera` / `builtInUltraWideCamera` /
    `builtInTelephotoCamera`), never an auto-switching virtual device.
  - [ ] A 4:3 active format (the telephoto defaults to 16:9), `videoZoomFactor = 1`.
  - [ ] Geometric distortion correction off unless `distortion_correction` is set.
  - [ ] Focus, exposure and white-balance locks; flash and torch.
  - [ ] `maxPhotoDimensions` for 48 MP.
  - [ ] Bayer RAW (12 MP) or ProRAW, plus a processed JPEG.
  - [ ] K from one video frame with intrinsic-matrix delivery, scaled to the photo.
  - [ ] Files stay on the sensor grid with Orientation 1, as on the fast path.
- [ ] LiDAR photo depth (`builtInLiDARDepthCamera`, 768×576, wide only). Include
  `AVDepthData.cameraCalibrationData` (intrinsics plus the lens-distortion lookup table) in meta.json.
- [ ] `CaptureCoordinator` full-path sequence:
  1. Show "hold still" and record the pose.
  2. Pause AR, shoot, resume AR without reset.
  3. Wait for `.normal` tracking and a fresh page observation, then record the pose again.
  4. Report the before/after bracket and its delta. `pose.source = arkit_held`.

  The server's still PnP remains the reference pose.
- [ ] Guide the *capture lens*, not the wide camera: turn the target into a wide-camera target with
  the lens extrinsics (`TargetResolver`). While guiding, draw that lens's field of view as a
  rectangle.
- [ ] Macro stand-off:
  1. Guide to a pose on the same sight line at least 120 mm out.
  2. Switch to a live ultra-wide preview with a reticle.
  3. The user pushes in and it captures when steady.
  4. The pose comes from the still if markers are visible, else it's "unknown", with the stand-off
     pose recorded.
- [ ] `hello` reports per-lens RAW types and real 4:3 photo sizes. The server's preflight uses them.
- [ ] Tests:
  - [ ] Unit: option → path selection, and K scaling across formats.
  - [ ] On the device, a tripod check: per-lens still PnP agrees with the extrinsics within 1–2 mm.

## Phase 6: metrology and polish

- [ ] `calibrate_lens` tool: run cv2 calibration over a set of requests that share a locked focus
  (the markers on the empty page), then store K and distortion per lens and format. Later analyses
  use them.
- [ ] Undistortion-aware still PnP when a lens has a calibration or Apple's distortion lookup table.
- [ ] Rotate HUD text for landscape holds, so it reads upright when the phone is sideways.
- [ ] `get_photo` depth previews (a false-colour PNG) for the agent to look at.
- [ ] Record the print scale with the user's caliper spans (`set_print_scale` exists, but nothing
  prompts for it yet).

## From testing (open questions)

- [ ] Request D (a low, 30° landscape shot from the page's bottom edge) was skipped as "can't reach".
  Find out whether the low sideways pose or the hints were the problem.
- [ ] The user's reachable side here is the page's top edge (marker 0). Consider letting the server
  learn reachable azimuths from skips and live poses. `phone_status` could then report where the
  user stands, so the agent picks reachable views or says "turn the page" up front.
- [ ] Write request notes by marker edge ("from the marker-0 edge"), not "near/far". Say so in the
  tool descriptions.
- [ ] Views below about 20° elevation lose the markers. A second page taped upright behind the object
  would give end-on views a pose.

## Loose ends

- [ ] `SimulatedTrackingSource`, so the Simulator and UI tests can exercise guidance (ARKit world
  tracking doesn't run in the Simulator). Then UI tests: connection badge, request card, can't reach,
  all done.
- [ ] Remaining on-device checks:
  - [ ] Page-pose jitter while still (< 0.5 mm).
  - [ ] Pose unchanged when the phone rolls 0 → 90 → 180°.
  - [ ] Reconnect < 3 s after 5 min in the background.
  - [ ] Kill mid-upload, relaunch, and it resumes.
  - [ ] Denied Local Network shows the Settings hint.
  - [ ] Measure a caliper-checked object from ≥ 2 stills (< 0.5 mm).
- [ ] Optional, only if needed:
  - [ ] A LAN pairing token (today anyone on the Wi-Fi can reach port 47815).
  - [ ] An HTTP-transport daemon so several Claude Code sessions can share one phone.
  - [ ] Multi-frame page refinement, if phone-vs-still disagreement ever exceeds guidance tolerance.
- [ ] Tell the modelling agent about AgentCam in `work/AGENTS.md`: request views, wait, prefer the
  still's PnP pose, and use `board_generation` to group photos of an unmoved page.
