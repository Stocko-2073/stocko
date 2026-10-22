#include "esp_http_server.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "management.h"
#include <stdlib.h>
#include <string.h>

/* Each socket has a generation-scoped service handle. Only the sender task
 * writes responses; timeout/queue bounds contain slow clients. */
typedef struct {
  int fd;
  mgmt_client_t client;
} peer_t;
static peer_t peers[4];
static httpd_handle_t server;
static SemaphoreHandle_t mutex;
static void lock(void) { xSemaphoreTake(mutex, portMAX_DELAY); }
static void unlock(void) { xSemaphoreGive(mutex); }
void manage_ws_close(int fd) {
  if (!mutex)
    return;
  lock();
  for (int i = 0; i < 4; i++)
    if (peers[i].client && peers[i].fd == fd) {
      management_close(peers[i].client);
      peers[i].client = 0;
    }
  unlock();
}
static esp_err_t opened(httpd_req_t *req) {
  lock();
  esp_err_t err = ESP_ERR_NO_MEM;
  for (int i = 0; i < 4; i++)
    if (!peers[i].client) {
      peers[i].fd = httpd_req_to_sockfd(req);
      peers[i].client = management_open();
      if (peers[i].client)
        err = ESP_OK;
      break;
    }
  unlock();
  return err;
}
static esp_err_t receive(httpd_req_t *req) {
  if (req->method == HTTP_GET)
    return ESP_OK;
  httpd_ws_frame_t f = {0};
  esp_err_t err = httpd_ws_recv_frame(req, &f, 0);
  if (err != ESP_OK)
    return err;
  if (f.type != HTTPD_WS_TYPE_TEXT || !f.final || f.len == 0 ||
      f.len >= MGMT_REQUEST)
    return ESP_FAIL;
  char buf[MGMT_REQUEST];
  f.payload = (uint8_t *)buf;
  err = httpd_ws_recv_frame(req, &f, f.len);
  if (err != ESP_OK)
    return err;
  if (memchr(buf, 0, f.len))
    return ESP_FAIL;
  buf[f.len] = 0;
  mgmt_client_t client = 0;
  lock();
  for (int i = 0; i < 4; i++)
    if (peers[i].fd == httpd_req_to_sockfd(req))
      client = peers[i].client;
  unlock();
  return management_receive(client, buf);
}
static void sender(void *arg) {
  char frame[MGMT_FRAME];
  for (;;) {
    /* Serialize against close/reuse; sends have a finite socket timeout. */
    for (int i = 0; i < 4; i++) {
      lock();
      peer_t p = peers[i];
      if (p.client && management_pop(p.client, frame)) {
        httpd_ws_frame_t f = {.final = true,
                              .type = HTTPD_WS_TYPE_TEXT,
                              .payload = (uint8_t *)frame,
                              .len = strlen(frame)};
        if (httpd_ws_send_frame_async(server, p.fd, &f) != ESP_OK)
          httpd_sess_trigger_close(server, p.fd);
      }
      unlock();
    }
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}
esp_err_t manage_ws_start(httpd_handle_t s) {
  server = s;
  mutex = xSemaphoreCreateMutex();
  if (!mutex)
    return ESP_ERR_NO_MEM;
  const httpd_uri_t uri = {.uri = "/manage",
                           .method = HTTP_GET,
                           .handler = receive,
                           .is_websocket = true,
                           .ws_post_handshake_cb = opened};
  esp_err_t err = httpd_register_uri_handler(s, &uri);
  if (err != ESP_OK)
    return err;
  return xTaskCreate(sender, "manage_tx", 4096, NULL, 3, NULL) == pdPASS
             ? ESP_OK
             : ESP_ERR_NO_MEM;
}
