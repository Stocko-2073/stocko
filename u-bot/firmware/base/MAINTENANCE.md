# Serial-free maintenance

The native Mac CLI lives in `../../app/Packages/UBotCore`. Build it with
`swift build --package-path ../../app/Packages/UBotCore`; the executable is
`../../app/Packages/UBotCore/.build/debug/ubotctl` (relative to `base/`).

```sh
ubotctl diagnostics --wifi ubot.local
ubotctl exec set --ble ubot
ubotctl exec wheel A reg 6F --wifi ubot.local
ubotctl shell --ble ubot
ubotctl logs --wifi ubot.local
ubotctl stream 20 --ble ubot
ubotctl jobs --wifi ubot.local
ubotctl jobs result 12 --wifi ubot.local
ubotctl jobs cancel 12 --ble ubot
ubotctl wifi scan --ble ubot
ubotctl wifi set 'network name' 'password' --ble ubot
ubotctl wifi reconnect --ble ubot
ubotctl exec reboot --ble ubot
```

`--json` emits protocol JSON for automation. `--timeout SEC` controls the Mac's
wait; a timeout does not cancel a bounded job. `--deadline MS` sets the robot's
job deadline (default 60,000; maximum 3,600,000). Ctrl-C cancels the current
owned job. Shell quoting handles spaces, single/double quotes and backslashes;
it does not invoke a shell on the robot. Credentials are never echoed.

`ubotctl drive v w seconds` retains its existing normalized joystick behavior.
`ubotctl exec drive 0.1 0 2` uses **metres/second and radians/second**. A drive
with zero duration, a wheel spin, or a manually closed position loop requires
a renewable one-second session lease. The CLI renews it every 300 ms. A lost
connection ends renewal; a late or replayed renewal cannot restart motion.
Calibration, demos, timed velocity and bounded position jobs survive disconnect.
Only one maintenance motion owns the robot; all other motor mutations are
refused until it finishes. Any client may stop it. Motors start disabled.

All existing command handlers receive an explicit output context. USB, Wi-Fi
and BLE use the same bounded worker; no global stdout redirection is involved.
Stop, E-stop and cancellation bypass its queue. Recent command output/results
are retained for four jobs, up to 4095 bytes each, with explicit truncation.
Queue capacity is six requests, further limited by free job records. Each
connected client has four 768-byte response slots. Completed responses drain
without blocking the command worker. Reconnecting clients can retrieve retained
output in pages; nothing automatically replays commands after reconnecting.

Logs retain the latest 16 records (127 bytes each), independent of subscriptions.
Each subscriber has its own cursor, sequence and overwritten-record count.
The previous boot's ring and boot ID survive warm resets via retained memory;
a compact panic reason/address also survives warm resets. Full power loss and
complete crash dumps are outside this milestone. USB log drops and
response-queue drops are counted separately. CSV subscriptions are per client,
0.5–50 Hz. Consumers never run on the control or command worker tasks.

A credential replacement is a 30-second trial. The previous credentials remain
in NVS until the candidate obtains an IP address; a failed/cancelled trial
restores them. Successful credentials are committed as one NVS blob. A reset
before commit returns to the old credentials. Use BLE while changing Wi-Fi.

## Wire protocol, version 1

Wi-Fi: WebSocket text frames at `/manage`. The driving `/ws` endpoint and phone
GATT characteristics keep their existing format. Trusted local access remains
the security model; this is not an Internet-facing command service.

The initial `hello` carries protocol, capabilities, boot ID, session ID,
firmware version, project, target, full ELF hash, and maximum request size.
Requests are JSON objects shorter than 768 bytes, with increasing positive
32-bit `id` values and the current `session`. IDs from a previous connection
cannot be reused in the new session. Frames with trailing JSON junk are rejected.

```json
{"op":"exec","session":2,"id":1,"args":["wheel","A","goto","1"],"deadline_ms":60000}
{"op":"jobs","session":2,"id":2}
{"op":"result","session":2,"id":3,"job":1,"offset":0}
{"op":"cancel","session":2,"id":4,"job":1}
{"op":"renew","session":2,"id":5,"job":1,"seq":1}
{"op":"logs","session":2,"id":6,"since":0}
{"op":"diagnostics","session":2,"id":7}
```

Responses distinguish `accepted` from `finished`. `output` includes byte offset;
`progress` includes elapsed time. `jobs` lists retained jobs; `result` returns a
page plus `next`, `total`, `done`, `code` and `truncated`. `log` and `stream` events
are asynchronous. Each response has cumulative per-client `dropped` reporting.
Exit codes: 0 success, 1 refusal/failure, 2 invalid request, 3 unsupported
firmware, 4 lost connection, 124 timeout/lease/deadline expiry, 130 cancellation.
Job identifiers belong to the boot ID and do not survive reboot.

BLE adds `7b1a0004-6f4b-4c2e-9d3a-2e5f1c8a9b01` (acknowledged request writes)
and `7b1a0005-6f4b-4c2e-9d3a-2e5f1c8a9b01` (response indications) alongside
the original drive service. Subscribe before writing. Both directions fragment
JSON using a five-byte header: flags (START=1, END=2), message LE16, offset LE16.
Payload capacity is ATT MTU minus eight. Reassembly is independent per peer,
limited to 767 bytes and five seconds; gaps, duplicates, NULs and invalid flags
are rejected. Only one response indication is outstanding per peer, and an
unacknowledged indication disconnects that peer after five seconds.

## Updates and emergency recovery

`ubotctl ota source URL`, `ota check`, `ota install [MANIFEST_URL]`,
`ota upload FILE.bin`, and `ota cancel` are the maintenance entry points.
`ota confirm EXPECTED_VERSION EXPECTED_ELF_SHA256` is available for bootstrap
recovery; normal installers perform confirmation themselves.

The manifest schema is generated by `tools/release_manifest.py`:
`version`, `project`, `target`, `size`, `sha256`, `image` (ELF SHA-256), `url`.
Publish immutable `releases/VERSION/SHA256.bin` and a versioned manifest first,
then the discovery `manifest.json`. Publishing still writes legacy root objects.
The publisher requires AWS CLI credentials and a current `boto3` installation
for conditional immutable uploads (`python3 -m venv .venv-publish`, then
`.venv-publish/bin/pip install boto3`; set `UBOT_PUBLISH_PYTHON` to that Python).
Re-run `ota_provisioning.sh` once when upgrading an existing bucket so the new
manifest and release paths are readable. Unrelated objects remain private.

The asynchronous HTTP upload is `POST /ota`, with Content-Length and headers
`X-Ubot-Version`, `X-Ubot-Project`, `X-Ubot-Target`, `X-Ubot-SHA256`,
`X-Ubot-Image`. The shared writer disables motors and gates every motor mutation,
streams into the inactive partition, validates descriptor/project/target/version,
size, full hash and ESP image checks before selecting it. Failed or interrupted
transfers do not select the candidate. Only one transfer can run.

Candidate boot keeps the motor interlock until confirmation. It requires
initialized radio management, a responsive worker, and
a reconnecting updater's `confirm` request matching boot, version and ELF hash.
At 120 seconds without confirmation it rolls back if a valid fallback exists.
Otherwise it remains explicitly unconfirmed with motors disabled; it never
silently marks itself healthy. Confirmed normal boots do not need a client.
Transfer/confirmation/rollback outcomes persist in NVS.

The existing partition map and settings remain intact. `tools/bootstrap.py`
handles this robot's initial layout (confirmed ota_0, empty ota_1) only. It checks
a full-flash backup, writes the new image to ota_1, preserves ota_0 and NVS, and
uses the native updater to confirm wirelessly. It deliberately refuses other
layouts. Private backups are under gitignored `.recovery/`; do not publish them.
USB is the recovery interface if neither radio starts.

See [acceptance record](tests/MAINTENANCE_ACCEPTANCE.md) for executed checks and
remaining physical observations. Hardware movement requires wheels safely clear.

## Repeating validation

Run software checks from the firmware root:

```sh
python3 base/components/drive/tests/run_host_tests.py
python3 base/tests/run_management_tests.py
cc -std=c11 -fsanitize=address,undefined -I base/components/management/include \
  base/tests/test_fragment.c -o /tmp/ubot-fragment-tests
/tmp/ubot-fragment-tests
python3 base/tests/test_release.py
swift test --package-path ../app/Packages/UBotCore
python3 base/tests/test_cli.py
```

The hardware scripts in `base/tests/` never open USB. `rack_probe.py
--rack-ready` moves the robot and requires both wheels safely clear.
`ota_interlock_probe.py` corrupts only the inactive image; follow it with a
successful installation to restore a valid fallback. `rollback_probe.py`
requires a verified fallback, deliberately withholds confirmation and checks
recovery. `wireless_soak.py --minutes 30 --cli PATH` runs telemetry, retained
logs, command completions, a stalled subscriber and repeated Wi-Fi/BLE
connections, verifying that boot identity stays constant.
