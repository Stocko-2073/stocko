#pragma once
// BLE peripheral (NimBLE). Advertises as the device name and serves:
//
//   Device Information 0x180A   manufacturer, model, serial, firmware rev,
//                               hardware rev
//   Battery Service    0x180F   battery level 0x2A19, notify
//   U-BOT drive        7b1a0000-6f4b-4c2e-9d3a-2e5f1c8a9b01
//     drive   7b1a0001-...  write (no response): int16 v, int16 w, each in
//                           thousandths of the current limit (-1000..1000),
//                           little-endian. Held 500 ms; keep sending. Since
//                           0.3.0 an optional fifth byte of flags: bit 0
//                           boost (while held), the rest ignored. Send it
//                           only after status flags2 bit 7: older firmware
//                           refuses any length but 4.
//     control 7b1a0002-...  write: 0 stop, 1 enable, 2 disable, 3 estop,
//                           4 clear faults
//     status  7b1a0003-...  read / notify at 5 Hz, packed little-endian, 20
//                           bytes (18 in 0.2.9, 13 before):
//                           u8 flags (b0 enabled, b1 faulted, b2 cmd active,
//                                     b3 enc A ok, b4 enc B ok, b5 batt present)
//                           u8 fault (the latched drive_fault_t, 0 when none)
//                           u16 battery mV
//                           u8 battery %
//                           i16 wheel A velocity, i16 wheel B velocity
//                              (thousandths of a turn/s)
//                           i16 v mm/s, i16 w mrad/s (command in force)
//                           u8 flags2 (either wheel: b0 boost granted, b1
//                              manual boost asked, b2 derate >= 1, b3 heat-
//                              limited, b4 OTPW, b5 recovering, b6 load
//                              estimate valid, b7 torque bytes valid)
//                           u8 heat A, u8 heat B (h x 100, saturating)
//                           u8 recovery attempts (low byte, wraps)
//                           u8 battery state (0 none, 1 ok, 2 low, 3 cutoff)
//                           u8 derate levels (A bits 0-1, B bits 2-3)
//                           u8 reserved
#include <stdbool.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t ble_init(void);

typedef struct {
    bool advertising;
    int connected;
    char addr[18];
} ble_status_t;

void ble_get_status(ble_status_t *out);

#ifdef __cplusplus
}
#endif
