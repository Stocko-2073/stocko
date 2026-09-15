#pragma once
#include "esp_core_dump.h"
typedef struct esp_flash_t esp_flash_t;
inline esp_err_t esp_flash_read(esp_flash_t *, void *buffer, uint32_t address, uint32_t length) {
  if (address < fakeCoreDumpAddress || address - fakeCoreDumpAddress + length > fakeCoreDump.size()) return ESP_FAIL;
  memcpy(buffer, fakeCoreDump.data() + (address - fakeCoreDumpAddress), length); return ESP_OK;
}
