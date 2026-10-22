# Serial-free maintenance acceptance — 2026-09-20

Robot: U-BOT hardware rev A, ESP32-S3, serial 64E833512A70. The user confirmed
rack readiness, external power and USB unplugged. All tests after that
confirmation use only Wi-Fi and BLE. Phone connection/live status was confirmed
by the user; the phone also displayed the active firmware-update state.

## Automated verification

- Production command service with pthread FreeRTOS fakes, ASan and UBSan: passed.
  Covers malformed/replayed requests, ownership, disconnected job completion,
  lease expiry/replay, position deadlines, slow subscribers and urgent stop.
- Production BLE reassembly parser, ASan/UBSan: passed MTU 23–517, independent
  peers, malformed flags, gaps, duplicates, stale fragments, size and NUL limits.
- Drive host tests: passed current quantization, register verification, dropped
  writes, reset recovery, threshold validation and fault refusal.
- Native Swift package: 43 tests in eight suites passed, including unchanged
  phone codecs, normalized driving and reconnect behavior.
- Native CLI against a real loopback WebSocket peer: eight tests passed,
  covering accepted versus finished, exit codes, explicit OTA timeout, JSON and paginated results.
- Release metadata tests: three passed, covering identity, hash and invalid images.

## Bootstrap and preservation

The original application and NVS were backed up in private, gitignored
`base/.recovery/` before installation. The 4 MiB flash backup SHA-256 is
`e77d926c0a6bb75820ce88fee90b961ce6bcd5574ae300cac52086c7156fe31a`.
The original 0.1.7 ota_0 image passed ESP image checksum/hash validation; ota_1
was blank. The partition map and NVS were preserved. Bootstrap 0.2.0 was
confirmed over Wi-Fi and both management radios verified before USB removal.

Bootstrap exposed and fixed a NimBLE initialization-order panic. Wireless
S3 testing subsequently exposed OTA-worker and NimBLE-host stack shortages.
The final task stack sizes are 16 KiB and 8 KiB respectively. A compact retained
panic reason/address made the latter diagnosable without USB. Management and
logging buffers were reduced to preserve TLS memory headroom. Failed attempts
were reported as failures, never success; current confirmed images remained
bootable throughout.

## Executed hardware checks

- Wi-Fi and BLE command access, firmware identity, diagnostics, settings, heap,
  timing and retained previous-boot logs: passed.
- Cold start of confirmed firmware after USB removal: management became reachable
  without confirmation or a serial connection.
- BLE provisioning with deliberately incorrect replacement credentials: failed
  after the 30-second trial and restored the previous working Wi-Fi credentials.
- Rack calibration A: completed after client disconnect; +12,288 counts,
  gain 1.0163, return residual zero. Result retrieved after reconnect.
- Rack demo and bounded 0.1-turn wheel move: completed after client disconnect.
- Continuous 0.03 m/s motion: duplicate renewal rejected; lease expiry stopped
  motion with exit 124; late renewal rejected. Explicit job cancellation: 130.
- Local Wi-Fi OTA: repeated successful writes, reboot, identity verification and
  health confirmation, including 0.2.6.
- BLE-initiated S3 OTA 0.2.6: successful write, progress, reboot, reconnect,
  expected-image verification and confirmation. Concurrent Wi-Fi motion request
  returned refusal while writing.

## Observations and remaining run results

Wheel B reports a weak encoder magnet (AGC 128); wheel A reports magnet OK
(AGC 128). No driver faults were reported. Calibration retained existing
polarity and tuning. Control timing has exceeded the 5 ms budget: boot/network
peaks around 7–12 ms, and 107–109 ms maxima were observed during rack operations.
These are recorded limitations, not timing acceptance passes.

- Corrupt binary with original expected hash: HTTP 409, current boot preserved.
- Concurrent upload: HTTP 409. Both management radios refused motion with exit 1.
- Wrong target/project/oversized metadata: HTTP 400 before writing.
- Wrong target/project in the actual binary header (metadata claims valid):
  HTTP 409 before writing.
- Interrupted transfer after 8 KiB: current image remained selected and reachable;
  final status reported interrupted upload / invalid image.
- Final 0.2.7 local installation: identity verified and confirmed; motor interlock
  now also covers the pending health phase before confirmation.

Evidence is in [results/2026-09-20](results/2026-09-20/), including the diagnosed
BLE stack overflow and subsequent successful S3 transfer.

## Final wireless results and handoff

- Deliberately unconfirmed 0.2.7 candidate: verified fallback available; motor
  enable refused while pending; wrong image confirmation rejected. Rolled back
  at the 120-second deadline to the original valid ota_0 and reported
  `rollback: confirmation timeout`. Boot identities and partition states are
  recorded in [rollback.jsonl](results/2026-09-20/rollback.jsonl).
- A final Wi-Fi-initiated S3 installation restored ota_1 and was verified and
  confirmed as 0.2.7. Both legacy Wi-Fi and BLE motor-enable requests were
  refused during this transfer.
- Native CLI Ctrl-C: cancellation acknowledged, exit 130, robot idle afterward.
- Existing normalized driving: 0.1 input produced 0.020 m/s over both Wi-Fi and
  BLE, then released and stopped. The final test issued E-stop.
- User confirmed the existing phone app connects and shows live status,
  including the shared firmware-update state.

Final firmware: **0.2.7**, ELF identity
`aee7ffbe7f2ccea12fd3839948516d82044338f49b416ac673baf27407042d9e`.
USB remains disconnected. No automated motion or background test is left running.

**The uninterrupted 30-minute wireless soak was explicitly postponed by the
user to run with a fully charged battery. It has not run and is not a pass.**
The prepared `wireless_soak.py` performs no motion and exercises telemetry,
logs, commands, a slow reader and repeated radio connections. Hardware
malformed/reassembly boundary coverage is currently the production-parser host
test plus actual native BLE traffic; the postponed soak adds sustained
simultaneous-client and slow-reader hardware coverage.

Overall implementation and the listed functional tests are complete; extended
stability acceptance remains pending. Weak wheel-B magnet and control timing
observations above remain visible limitations.

Final read-only handoff snapshot: drivers disabled, command idle, no drive faults,
OTA confirmed, ota_1 valid with verified fallback available, free heap 73,728
bytes. See [final diagnostics](results/2026-09-20/final-diagnostics.txt).
No test processes remained active when control was returned to the user.
