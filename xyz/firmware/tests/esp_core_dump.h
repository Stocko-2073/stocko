#pragma once
#include <cstdint>
#include <cstring>
#include <vector>
#include "esp_system.h"
// Fake core dump partition: bytes present mean a dump is stored.
inline std::vector<uint8_t> fakeCoreDump;
constexpr uint32_t fakeCoreDumpAddress = 0x3F0000;
typedef struct { uint8_t stackdump[1024]; uint32_t dump_size; } esp_core_dump_bt_info_t;
typedef struct { uint32_t mstatus, mtvec, mcause, mtval, ra, sp, exc_a[8]; } esp_core_dump_summary_extra_info_t;
typedef struct {
  uint32_t exc_tcb; char exc_task[16]; uint32_t exc_pc; esp_core_dump_bt_info_t exc_bt_info;
  uint32_t core_dump_version; uint8_t app_elf_sha256[65]; esp_core_dump_summary_extra_info_t ex_info;
} esp_core_dump_summary_t;
inline esp_err_t esp_core_dump_image_check() { return fakeCoreDump.empty() ? ESP_ERR_NOT_FOUND : ESP_OK; }
inline esp_err_t esp_core_dump_image_get(size_t *addr, size_t *size) {
  if (fakeCoreDump.empty()) return ESP_ERR_NOT_FOUND;
  *addr = fakeCoreDumpAddress; *size = fakeCoreDump.size(); return ESP_OK;
}
inline esp_err_t esp_core_dump_image_erase() { fakeCoreDump.clear(); return ESP_OK; }
inline esp_err_t esp_core_dump_get_panic_reason(char *buffer, size_t size) {
  if (fakeCoreDump.empty()) return ESP_ERR_NOT_FOUND;
  snprintf(buffer, size, "Test panic (fake)"); return ESP_OK;
}
inline esp_err_t esp_core_dump_get_summary(esp_core_dump_summary_t *s) {
  if (fakeCoreDump.empty()) return ESP_ERR_NOT_FOUND;
  memset(s, 0, sizeof(*s));
  snprintf(s->exc_task, sizeof(s->exc_task), "loopTask");
  s->exc_pc = 0x42001234; s->ex_info.ra = 0x42005678; s->ex_info.sp = 0x40810000;
  s->ex_info.mcause = 7; s->ex_info.mtval = 0xdeadbeef;
  const uint32_t words[] = {0x00000001, 0x4200abcd, 0x40800100};
  memcpy(s->exc_bt_info.stackdump, words, sizeof(words)); s->exc_bt_info.dump_size = sizeof(words);
  memcpy(s->app_elf_sha256, "0123456789abcdef0123456789abcdef", 33);
  return ESP_OK;
}
