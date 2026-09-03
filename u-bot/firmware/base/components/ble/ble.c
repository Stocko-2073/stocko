#include "ble.h"

#include <stdio.h>
#include <string.h>

#include "battery.h"
#include "drive.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "host/ble_hs.h"
#include "host/ble_uuid.h"
#include "host/util/util.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "services/bas/ble_svc_bas.h"
#include "services/dis/ble_svc_dis.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"
#include "sysinfo.h"

static const char *TAG = "ble";

// 7b1a00xx-6f4b-4c2e-9d3a-2e5f1c8a9b01, least significant byte first.
#define UBOT_UUID(xx) BLE_UUID128_INIT(0x01, 0x9b, 0x8a, 0x1c, 0x5f, 0x2e, 0x3a, 0x9d, \
                                       0x2e, 0x4c, 0x4b, 0x6f, xx, 0x00, 0x1a, 0x7b)

static const ble_uuid128_t UUID_SVC     = UBOT_UUID(0x00);
static const ble_uuid128_t UUID_DRIVE   = UBOT_UUID(0x01);
static const ble_uuid128_t UUID_CONTROL = UBOT_UUID(0x02);
static const ble_uuid128_t UUID_STATUS  = UBOT_UUID(0x03);

static uint16_t s_drive_handle, s_control_handle, s_status_handle;
static uint8_t s_own_addr_type;
static char s_addr[18] = "?";
static volatile int s_connections = 0;
static volatile bool s_advertising = false;
static bool s_status_subscribed = false;
static esp_timer_handle_t s_tick;

static const uint32_t DRIVE_HOLD_MS = 500;

void ble_store_config_init(void);

// -------------------------------------------------------------------- status

typedef struct __attribute__((packed)) {
    uint8_t flags;
    uint8_t fault;
    uint16_t batt_mv;
    uint8_t batt_pct;
    int16_t vel_a, vel_b;
    int16_t v_mmps, w_mradps;
} status_packet_t;

static int16_t clamp16(float v) {
    if (v > 32767.0f) return 32767;
    if (v < -32768.0f) return -32768;
    return (int16_t)v;
}

static void build_status(status_packet_t *p) {
    drive_status_t s;
    drive_get_status(&s);
    memset(p, 0, sizeof *p);
    if (s.enabled) p->flags |= 1 << 0;
    if (s.faulted) p->flags |= 1 << 1;
    if (s.cmd_active) p->flags |= 1 << 2;
    if (s.wheel[0].encoder_ok) p->flags |= 1 << 3;
    if (s.wheel[1].encoder_ok) p->flags |= 1 << 4;
    if (battery_present()) p->flags |= 1 << 5;
    p->fault = s.faulted ? s.wheel[s.fault_wheel].fault : 0;
    p->batt_mv = (uint16_t)(battery_voltage() * 1000.0f);
    int pct = battery_percent();
    p->batt_pct = pct < 0 ? 0 : (uint8_t)pct;
    p->vel_a = clamp16(s.wheel[0].vel_tps * 1000.0f);
    p->vel_b = clamp16(s.wheel[1].vel_tps * 1000.0f);
    p->v_mmps = clamp16(s.v_mps * 1000.0f);
    p->w_mradps = clamp16(s.w_radps * 1000.0f);
}

// ---------------------------------------------------------------------- gatt

static int gatt_access(uint16_t conn_handle, uint16_t attr_handle,
                       struct ble_gatt_access_ctxt *ctxt, void *arg) {
    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR && attr_handle == s_status_handle) {
        status_packet_t p;
        build_status(&p);
        return os_mbuf_append(ctxt->om, &p, sizeof p) == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
    }
    if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR && attr_handle == s_drive_handle) {
        int16_t vw[2];
        uint16_t len = 0;
        if (ble_hs_mbuf_to_flat(ctxt->om, vw, sizeof vw, &len) != 0 || len != sizeof vw) {
            return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
        }
        esp_err_t err = drive_set_normalized(vw[0] / 1000.0f, vw[1] / 1000.0f, DRIVE_HOLD_MS);
        if (err != ESP_OK) ESP_LOGD(TAG, "drive write refused: %s", drive_refusal());
        return 0;   // write-without-response: nothing to say back; status carries the fault
    }
    if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR && attr_handle == s_control_handle) {
        uint8_t op = 0xFF;
        uint16_t len = 0;
        if (ble_hs_mbuf_to_flat(ctxt->om, &op, 1, &len) != 0 || len != 1) {
            return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
        }
        esp_err_t err = ESP_OK;
        switch (op) {
            case 0: drive_stop(); break;
            case 1: err = drive_enable(true); break;
            case 2: err = drive_enable(false); break;
            case 3: drive_estop(); break;
            case 4: err = drive_clear_faults(); break;
            default: return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
        }
        ESP_LOGI(TAG, "control op %u: %s", op, err == ESP_OK ? "ok" : drive_refusal());
        return err == ESP_OK ? 0 : BLE_ATT_ERR_UNLIKELY;
    }
    return BLE_ATT_ERR_UNLIKELY;
}

static const struct ble_gatt_svc_def gatt_svcs[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = &UUID_SVC.u,
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = &UUID_DRIVE.u,
                .access_cb = gatt_access,
                .flags = BLE_GATT_CHR_F_WRITE_NO_RSP | BLE_GATT_CHR_F_WRITE,
                .val_handle = &s_drive_handle,
            },
            {
                .uuid = &UUID_CONTROL.u,
                .access_cb = gatt_access,
                .flags = BLE_GATT_CHR_F_WRITE,
                .val_handle = &s_control_handle,
            },
            {
                .uuid = &UUID_STATUS.u,
                .access_cb = gatt_access,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY,
                .val_handle = &s_status_handle,
            },
            { 0 },
        },
    },
    { 0 },
};

// ----------------------------------------------------------------------- gap

static int gap_event(struct ble_gap_event *event, void *arg);

static void advertise(void) {
    struct ble_hs_adv_fields fields;
    memset(&fields, 0, sizeof fields);
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.tx_pwr_lvl_is_present = 1;
    fields.tx_pwr_lvl = BLE_HS_ADV_TX_PWR_LVL_AUTO;
    const char *name = ble_svc_gap_device_name();
    fields.name = (uint8_t *)name;
    fields.name_len = strlen(name);
    fields.name_is_complete = 1;
    fields.uuids16 = (ble_uuid16_t[]) { BLE_UUID16_INIT(BLE_SVC_DIS_UUID16), BLE_UUID16_INIT(0x180F) };
    fields.num_uuids16 = 2;
    fields.uuids16_is_complete = 1;
    int rc = ble_gap_adv_set_fields(&fields);
    if (rc != 0) { ESP_LOGE(TAG, "adv fields: rc=%d", rc); return; }

    // The 128-bit drive service goes in the scan response; it does not fit
    // beside the name in the 31-byte advertisement.
    struct ble_hs_adv_fields rsp;
    memset(&rsp, 0, sizeof rsp);
    rsp.uuids128 = (ble_uuid128_t *)&UUID_SVC;
    rsp.num_uuids128 = 1;
    rsp.uuids128_is_complete = 1;
    rc = ble_gap_adv_rsp_set_fields(&rsp);
    if (rc != 0) ESP_LOGW(TAG, "scan response: rc=%d", rc);

    struct ble_gap_adv_params adv;
    memset(&adv, 0, sizeof adv);
    adv.conn_mode = BLE_GAP_CONN_MODE_UND;
    adv.disc_mode = BLE_GAP_DISC_MODE_GEN;
    rc = ble_gap_adv_start(s_own_addr_type, NULL, BLE_HS_FOREVER, &adv, gap_event, NULL);
    if (rc != 0 && rc != BLE_HS_EALREADY) { ESP_LOGE(TAG, "adv start: rc=%d", rc); return; }
    s_advertising = true;
}

static int gap_event(struct ble_gap_event *event, void *arg) {
    switch (event->type) {
        case BLE_GAP_EVENT_CONNECT:
            if (event->connect.status == 0) {
                s_connections++;
                ESP_LOGI(TAG, "connected (handle %d), %d total", event->connect.conn_handle, s_connections);
            } else {
                ESP_LOGW(TAG, "connect failed: %d", event->connect.status);
            }
            s_advertising = false;
            advertise();   // keep accepting a second peer, e.g. a phone and a laptop
            return 0;
        case BLE_GAP_EVENT_DISCONNECT:
            if (s_connections > 0) s_connections--;
            ESP_LOGI(TAG, "disconnected (reason %d), %d left", event->disconnect.reason, s_connections);
            // The deadman stops the robot 500 ms after the last drive write,
            // so nothing to do for motion here.
            s_advertising = false;
            advertise();
            return 0;
        case BLE_GAP_EVENT_ADV_COMPLETE:
            s_advertising = false;
            advertise();
            return 0;
        case BLE_GAP_EVENT_SUBSCRIBE:
            if (event->subscribe.attr_handle == s_status_handle) {
                s_status_subscribed = event->subscribe.cur_notify;
                ESP_LOGI(TAG, "status notifications %s", s_status_subscribed ? "on" : "off");
            }
            return 0;
        case BLE_GAP_EVENT_MTU:
            ESP_LOGD(TAG, "mtu %d", event->mtu.value);
            return 0;
        default:
            return 0;
    }
}

static void on_reset(int reason) { ESP_LOGW(TAG, "host reset, reason %d", reason); }

static void on_sync(void) {
    int rc = ble_hs_util_ensure_addr(0);
    if (rc != 0) { ESP_LOGE(TAG, "no address: rc=%d", rc); return; }
    rc = ble_hs_id_infer_auto(0, &s_own_addr_type);
    if (rc != 0) { ESP_LOGE(TAG, "address type: rc=%d", rc); return; }
    uint8_t a[6] = {0};
    ble_hs_id_copy_addr(s_own_addr_type, a, NULL);
    snprintf(s_addr, sizeof s_addr, "%02x:%02x:%02x:%02x:%02x:%02x", a[5], a[4], a[3], a[2], a[1], a[0]);
    ESP_LOGI(TAG, "advertising as \"%s\", address %s", ble_svc_gap_device_name(), s_addr);
    advertise();
}

static void host_task(void *param) {
    nimble_port_run();   // returns only after nimble_port_stop()
    nimble_port_freertos_deinit();
}

// 5 Hz: push the status packet to whoever subscribed, and the battery level
// once a second through the standard service.
static void tick(void *arg) {
    static int n = 0;
    if (s_connections > 0 && s_status_subscribed) ble_gatts_chr_updated(s_status_handle);
    if ((++n % 5) == 0) {
        int pct = battery_percent();
        ble_svc_bas_battery_level_set(pct < 0 ? 0 : (uint8_t)pct);
    }
}

esp_err_t ble_init(void) {
    esp_err_t err = nimble_port_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nimble_port_init: %s", esp_err_to_name(err));
        return err;
    }
    ble_hs_cfg.reset_cb = on_reset;
    ble_hs_cfg.sync_cb = on_sync;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;
    ble_hs_cfg.sm_io_cap = BLE_SM_IO_CAP_NO_IO;
    ble_hs_cfg.sm_bonding = 0;
    ble_hs_cfg.sm_sc = 0;

    ble_svc_gap_init();
    ble_svc_gatt_init();
    ble_svc_dis_init();
    ble_svc_bas_init();

    int rc = ble_gatts_count_cfg(gatt_svcs);
    if (rc == 0) rc = ble_gatts_add_svcs(gatt_svcs);
    if (rc != 0) {
        ESP_LOGE(TAG, "gatt services: rc=%d", rc);
        return ESP_FAIL;
    }

    ble_svc_dis_manufacturer_name_set("Stocko");
    ble_svc_dis_model_number_set("U-BOT base");
    ble_svc_dis_serial_number_set(sysinfo_serial());
    ble_svc_dis_firmware_revision_set(sysinfo_fw_version());
    ble_svc_dis_hardware_revision_set(sysinfo_hw_rev());
    ble_svc_gap_device_name_set(sysinfo_name());

    ble_store_config_init();
    nimble_port_freertos_init(host_task);

    const esp_timer_create_args_t targs = { .callback = tick, .name = "ble_tick" };
    err = esp_timer_create(&targs, &s_tick);
    if (err == ESP_OK) err = esp_timer_start_periodic(s_tick, 200000);
    return err;
}

void ble_get_status(ble_status_t *out) {
    if (!out) return;
    out->advertising = s_advertising;
    out->connected = s_connections;
    strncpy(out->addr, s_addr, sizeof out->addr - 1);
    out->addr[sizeof out->addr - 1] = 0;
}
