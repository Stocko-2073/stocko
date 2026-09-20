/* Included by ble.c: all peer state runs on the NimBLE host event queue. */
#include "management.h"
#include "management_fragment.h"
static const ble_uuid128_t UUID_REQUEST = UBOT_UUID(0x04),
                           UUID_RESPONSE = UBOT_UUID(0x05);
static uint16_t s_request_handle, s_response_handle;
typedef struct {
  bool used, subscribed, inflight;
  uint16_t conn, tx_id, tx_off, tx_next;
  int64_t tx_time;
  mgmt_client_t client;
  management_fragment_t rx;
  char tx[MGMT_FRAME];
} management_peer_t;
static management_peer_t management_peers[CONFIG_BT_NIMBLE_MAX_CONNECTIONS];
static struct ble_npl_event management_event;
static esp_timer_handle_t management_timer;
static management_peer_t *management_peer(uint16_t conn) {
  for (int i = 0; i < CONFIG_BT_NIMBLE_MAX_CONNECTIONS; i++)
    if (management_peers[i].used && management_peers[i].conn == conn)
      return &management_peers[i];
  return NULL;
}
static void management_disconnect(uint16_t conn) {
  management_peer_t *p = management_peer(conn);
  if (p) {
    management_close(p->client);
    memset(p, 0, sizeof *p);
  }
}
static void management_connected(uint16_t conn) {
  for (int i = 0; i < CONFIG_BT_NIMBLE_MAX_CONNECTIONS; i++)
    if (!management_peers[i].used) {
      management_peers[i] = (management_peer_t){.used = true, .conn = conn};
      break;
    }
}
static int management_write(uint16_t conn, struct ble_gatt_access_ctxt *ctxt) {
  management_peer_t *p = management_peer(conn);
  if (!p || !p->client || !p->subscribed)
    return BLE_ATT_ERR_UNLIKELY;
  uint8_t buf[512];
  uint16_t len = 0;
  if (ble_hs_mbuf_to_flat(ctxt->om, buf, sizeof buf, &len) || len <= 5)
    return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
  int result =
      management_fragment_feed(&p->rx, buf, len, esp_timer_get_time() / 1000);
  if (result < 0)
    return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
  if (result == 0)
    return 0;
  return management_receive(p->client, p->rx.data) == ESP_OK
             ? 0
             : BLE_ATT_ERR_UNLIKELY;
}

static void management_tx(struct ble_npl_event *ev) {
  for (int i = 0; i < CONFIG_BT_NIMBLE_MAX_CONNECTIONS; i++) {
    management_peer_t *p = &management_peers[i];
    if (!p->used || !p->subscribed)
      continue;
    if (p->inflight) {
      if (esp_timer_get_time() - p->tx_time > 5000000)
        ble_gap_terminate(p->conn, BLE_ERR_REM_USER_CONN_TERM);
      continue;
    }
    if (!p->tx[0]) {
      if (!management_pop(p->client, p->tx))
        continue;
      p->tx_off = 0;
      p->tx_id++;
    }
    unsigned mtu = ble_att_mtu(p->conn), remaining = strlen(p->tx) - p->tx_off;
    unsigned n = mtu > 8 ? mtu - 8 : 15;
    if (n > remaining)
      n = remaining;
    if (n > 504)
      n = 504;
    uint8_t b[512];
    b[0] = (p->tx_off == 0 ? 1 : 0) | (n == remaining ? 2 : 0);
    b[1] = p->tx_id;
    b[2] = p->tx_id >> 8;
    b[3] = p->tx_off;
    b[4] = p->tx_off >> 8;
    memcpy(b + 5, p->tx + p->tx_off, n);
    struct os_mbuf *om = ble_hs_mbuf_from_flat(b, n + 5);
    if (!om)
      continue;
    p->inflight = true;
    p->tx_time = esp_timer_get_time();
    p->tx_next = p->tx_off + n;
    if (ble_gatts_indicate_custom(p->conn, s_response_handle, om) != 0)
      p->inflight = false;
  }
}
static void management_schedule(void *arg) {
  ble_npl_eventq_put(nimble_port_get_dflt_eventq(), &management_event);
}
static void management_ack(struct ble_gap_event *event) {
  if (!event->notify_tx.indication ||
      event->notify_tx.attr_handle != s_response_handle)
    return;
  management_peer_t *p = management_peer(event->notify_tx.conn_handle);
  if (!p)
    return;
  /* status zero is sent, EDONE is acknowledged by the peer. */
  if (event->notify_tx.status == BLE_HS_EDONE) {
    p->inflight = false;
    p->tx_off = p->tx_next;
    if (p->tx_off >= strlen(p->tx))
      p->tx[0] = 0;
    management_schedule(NULL);
  } else if (event->notify_tx.status != 0) {
    p->inflight = false;
    ble_gap_terminate(p->conn, BLE_ERR_REM_USER_CONN_TERM);
  }
}
