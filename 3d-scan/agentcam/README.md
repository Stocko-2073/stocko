# AgentCam

An agent (Claude Code) asks for photos from specific camera poses around an object sitting on the
printed marker page (`work/border_letter_aruco_4x4_10mm.pdf`, printed at 100%). The iPhone app locks
onto the page, guides you to each pose with two wireframe cubes and a sight line, takes the photo
by itself when you're lined up and steady, and sends it to the Mac. The agent gets the photo with its
intrinsics and two poses: the phone's tracked pose, and one solved from the markers in the still itself.

```
Claude Code ──stdio──> agentcam-mcp (agentcam/mcp) <──Wi-Fi: Bonjour, WebSocket, HTTP──> AgentCam (iPhone)
                            │
                            └── 3d-scan/captures/<request>/<capture>/{image.jpg, meta.json, analysis.json, preview.jpg, ...}
```

Requests wait on the Mac while the app is closed; ask the user to open AgentCam, then `wait_for_photos`.

## Layout

| Path | What |
|---|---|
| `mcp/` | The MCP server (Python, uv). Also serves the phone on port 47815 and advertises `_agentcam._tcp`. |
| `project.yml`, `AgentCam/` | The iOS app (XcodeGen; `AgentCam.xcodeproj` is generated and gitignored). |
| `Packages/AgentCamCore/` | Protocol, frames, page-pose fusion, guidance, link, outbox. Plain Swift, tested on the Mac. |
| `Packages/AgentCamVision/` | OpenCV marker detection and the page solver (C++ bridge), the same algorithm as the server. |
| `protocol/` | The shared contract: board layouts, JSON examples both sides decode, and the real-photo fixture. |

The server's pydantic models (`mcp/src/agentcam/models.py`) are the source of truth for the wire
format. After changing them, run `uv run python tests/make_examples.py` and check the diff; the Swift
tests decode every example.

## Use it from Claude Code

`3d-scan/.mcp.json` registers the server for Claude Code sessions started in `3d-scan/` (approve it
the first time). Tools: `request_photos`, `wait_for_photos`, `get_photo`, `list_requests`,
`cancel_requests`, `phone_status`, `get_board`, `set_print_scale`. `get_board` explains the frames:
page frame in mm, origin at the page centre, +y toward the marker-0 edge, +z up; OpenCV camera axes on
the stored (sensor) pixel grid, EXIF orientation 1.

Only one Claude Code session can run the server at a time (it holds a lock on `captures/`).

## Build and install

```sh
cd 3d-scan/agentcam/mcp && uv sync --group dev && uv run pytest -q          # server: 33 tests
cd ../Packages/AgentCamCore && swift test                                # core: 30 tests
cd ../AgentCamVision && swift test                                       # vision: 6 tests (downloads OpenCV, ~200 MB, once)
cd ../.. && xcodegen generate
xcodebuild build -project AgentCam.xcodeproj -scheme AgentCam \
    -destination 'platform=iOS,name=SamW' -allowProvisioningUpdates -derivedDataPath build
xcrun devicectl device install app --device SamW build/Build/Products/Debug-iphoneos/AgentCam.app
```

`agentcam-fakephone --server http://127.0.0.1:47815` (from `mcp/`) stands in for the phone: it takes
each queued request, renders the page from that pose, and uploads it through the real protocol.

## Troubleshooting

- **The phone never connects.** Allow Local Network for AgentCam (Settings > Privacy & Security >
  Local Network). On the Mac, the application firewall must allow incoming connections to uv's Python
  (`~/.local/share/uv/python/cpython-3.12*/bin/python3.12`). `phone_status` reports "No phone has
  connected yet" in that case. You can also type the Mac's address in the app's settings.
- **"another program is already using port 47815".** Set `AGENTCAM_PORT` in `.mcp.json`. The server
  checks that its own health endpoint answers, because another program bound to 127.0.0.1 on the
  same port would otherwise silently take local traffic.
- **The page won't lock.** It needs to be flat and level (within 20 degrees of level), with markers
  in view. Settings > "Show tracking details" shows marker counts and why estimates were rejected.
- **Unsent photos** wait in the app's Documents/Outbox (visible in the Files app) and go out on the
  next connection.

## Status

Done: page lock, guidance, automatic capture on the main lens (12 MP), torch, focus, exposure and
white-balance locks, ARKit LiDAR depth, delivery with still-image PnP checks, placement prompts,
"can't reach" skips with a turn-the-page tip.

Not yet: requests needing the full camera path (ultra-wide macro, 5x telephoto, flash, 48 MP, RAW,
LiDAR photo depth) show "Can't do this one yet". That's the next phase: pause AR, shoot with
AVFoundation on the chosen physical lens, resume, and take the pose from the markers in the still.
