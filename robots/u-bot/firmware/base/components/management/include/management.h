#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#ifdef __cplusplus
extern "C" {
#endif
#define MGMT_FRAME 768
#define MGMT_REQUEST 768
#define MGMT_CLIENTS 7
/* Handles include a generation; queued output never crosses reconnects. */
typedef uint32_t mgmt_client_t;
typedef struct { mgmt_client_t client; uint32_t job; } command_context_t;
typedef int (*command_handler_t)(command_context_t *, int, char **);
esp_err_t management_init(command_handler_t handler);
mgmt_client_t management_open(void);
void management_close(mgmt_client_t client);
esp_err_t management_receive(mgmt_client_t client, const char *json);
bool management_pop(mgmt_client_t client, char out[MGMT_FRAME]);
void command_printf(command_context_t *ctx, const char *fmt, ...) __attribute__((format(printf,2,3)));
int management_stream(mgmt_client_t client, float hz);
const char *management_boot_id(void);
bool management_ready(void);
void management_stop(bool emergency);
#ifdef __cplusplus
}
#endif
