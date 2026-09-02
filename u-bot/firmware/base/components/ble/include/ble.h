#pragma once
// BLE peripheral (NimBLE). Advertises as the device name and serves:
//
//   Device Information 0x180A   manufacturer, model, serial, firmware rev,
//                               hardware rev
//   Battery Service    0x180F   battery level 0x2A19, notify
//   U-BOT drive        7b1a0000-6f4b-4c2e-9d3a-2e5f1c8a9b01
//     drive   7b1a0001-...  write (no response): int16 v, int16 w, each in
//                           thousandths of the current limit (-1000..1000),
//                           little-endian. Held 500 ms; keep sending.
//     control 7b1a0002-...  write: 0 stop, 1 enable, 2 disable, 3 estop,
//                           4 clear faults
//     status  7b1a0003-...  read / notify at 5 Hz, packed little-endian:
//                           u8 flags (b0 enabled, b1 faulted, b2 cmd active,
//                                     b3 enc A ok, b4 enc B ok, b5 batt present)
//                           u8 fault (drive_fault_t of the faulting wheel)
//                           u16 battery mV
//                           u8 battery %
//                           i16 wheel A velocity, i16 wheel B velocity
//                              (thousandths of a turn/s)
//                           i16 v mm/s, i16 w mrad/s (command in force)
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
