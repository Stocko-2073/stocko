#pragma once
#include <stdbool.h>

#include "esp_err.h"

esp_err_t ws_server_start(void);
bool ws_server_up(void);
int ws_client_count(void);
