# Wi-Fi radio comparison, 2026-09-20

Replacement XIAO ESP32-S3, MAC `64:e8:33:51:2a:70`, ESP-IDF v6.1.
Same stored credentials, AP, and robot position throughout. Direct-IP tests
used `192.168.1.157`; the connected RSSI was approximately -48 to -55 dBm.
Modem sleep stayed off. No motor commands were sent; drivers stayed disabled.

## Results

| Firmware / radio configuration | Ping, 30 requests | HTTP, 10 downloads | WebSocket telemetry |
| --- | --- | --- | --- |
| 0.1.6: Wi-Fi and BLE on core 0, BLE advertising, no BLE clients | 28 replies, 19 later than 1 s; 1469 ms mean | 0 completed within 3 s | Handshake took 4.5 s; no status before receive timeout |
| 0.1.7-wifi-only: Bluetooth initialization skipped, Wi-Fi core 0 | Not run: did not obtain an IP | Not run | Not run |
| 0.1.7: Wi-Fi core 1, Bluetooth controller and NimBLE core 0, BLE advertising, no BLE clients | 19 replies, 12 later than 1 s; 1506 ms mean | 0 completed within 3 s | Handshake timed out after 5 s |

Ping ran once per second with a 1 s reporting threshold, concurrently with
sequential HTTP GETs of `/`, each with a 3 s total timeout and 0.2 s pause.
Late replies are included in received counts and mean RTT. WebSocket testing
followed those probes and only received telemetry; it sent no robot commands.
Some HTTP attempts received status 200 but failed to download the body.

The Wi-Fi-only console confirmed no BLE advertising or connections. Repeated
attempts failed the four-way handshake. Two captured attempts showed successful
802.11 authentication and association, followed about 3.2 s later by an AP
deauthentication frame with reason 15 (`recv deauth, reason=0xf`). The device
still had no IP after more than two minutes. One redundant reconnect request
hit the existing retry timer and returned `sta is connecting`; another
automatic attempt independently failed with the same AP deauthentication.

The final 0.1.7 boot log confirmed `wifi driver task ... core=1`, joined the
same AP with WPA2-PSK / BW20, and obtained its IP about 5 s after boot. It stayed
associated during the probe, despite unusable traffic. HTTP send errors were
logged. No reset or driver fault was observed. Worst recorded control interval
was 7502 us against the nominal 5000 us period, including startup; motion and
loaded control timing were not tested.

A subsequent 15 s BLE-only client check connected and displayed telemetry
throughout the remaining observation window, with both motors disabled and
zero commanded velocity. The client was stopped after this check. All live
tests ended before the owner began the antenna replacement.

Neither experiment established reliable Wi-Fi. BLE activity is not necessary
to reproduce the handshake failure. These short, sequential trials do not
establish that core separation caused the difference in packet loss, or that
the handshake failures and connected-state stalls share one cause.

After changing the antenna with 0.1.7 still installed, the owner reported much
better pings and a successful connection from the app. This supports the
antenna or its connection being a major contributor. No post-swap packet-loss
measurement or extended reliability test was recorded in this session.

## Build and recovery

Both ESP-IDF builds and flash hash verification passed. Only the running
`ota_0` application slot at `0x20000` was flashed. NVS, calibration, bootloader,
partition table, and OTA metadata were preserved. The prior device application
was backed up and matched the saved 0.1.6 build.

Final firmware is **0.1.7**, with BLE enabled, Wi-Fi on core 1, Bluetooth on core
0, and software coexistence enabled. These choices are in `sdkconfig.defaults`
and the active `sdkconfig`. The default-on `CONFIG_UBOT_BLE_ENABLE` option in
`main/Kconfig.projbuild` allows repeating the Wi-Fi-only comparison.

Raw logs, configurations, probe script, original application backup, and both
test images are in `/private/tmp/ubot-radio-tests/` on the test Mac. This is
temporary storage. The final image SHA-256 is
`2486e578df05fb72ccdea7bdfbfc93314c849c546c57a1170436ec57681ba45b`.
