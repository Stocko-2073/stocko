#pragma once
#include <esp_system.h>
#include <esp_core_dump.h>
#include <esp_flash.h>

// The Arduino ESP32-C6 libraries are built with core dumps to flash (ELF
// format), and the board's default partition table reserves 64 KB for them at
// 0x3F0000. A panic therefore already leaves a dump behind; this module reports
// it at boot and lets the USB console read or clear it. Flashing a new sketch
// does not erase the coredump partition.
namespace CrashLog {
char startupReason[40] = "Startup";

const char *resetName(esp_reset_reason_t r) {
  switch (r) {
    case ESP_RST_POWERON: return "power-on";
    case ESP_RST_EXT: return "external reset";
    case ESP_RST_SW: return "software reset";
    case ESP_RST_PANIC: return "panic";
    case ESP_RST_INT_WDT: return "interrupt watchdog";
    case ESP_RST_TASK_WDT: return "task watchdog";
    case ESP_RST_WDT: return "watchdog";
    case ESP_RST_BROWNOUT: return "brownout";
    case ESP_RST_USB: return "USB reset";
    case ESP_RST_JTAG: return "JTAG reset";
    case ESP_RST_PWR_GLITCH: return "power glitch";
    case ESP_RST_CPU_LOCKUP: return "CPU lockup";
    default: return "unknown reset";
  }
}
bool crashReset(esp_reset_reason_t r) {
  return r == ESP_RST_PANIC || r == ESP_RST_INT_WDT || r == ESP_RST_TASK_WDT || r == ESP_RST_WDT ||
         r == ESP_RST_BROWNOUT || r == ESP_RST_PWR_GLITCH || r == ESP_RST_CPU_LOCKUP;
}
bool stored() { return esp_core_dump_image_check() == ESP_OK; }

void begin() {
  const esp_reset_reason_t r = esp_reset_reason();
  if (crashReset(r)) snprintf(startupReason, sizeof(startupReason), "Restarted after %s", resetName(r));
  Serial.printf("RESET %s%s\n", resetName(r),
                stored() ? "; crash log stored: CRASH INFO | CRASH DUMP | CRASH CLEAR" : "");
}

void base64Line(const uint8_t *in, size_t n, char *out) {
  static const char *table = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  size_t o = 0;
  for (size_t i = 0; i < n; i += 3) {
    const uint32_t v = uint32_t(in[i]) << 16 | (i+1 < n ? uint32_t(in[i+1]) << 8 : 0) | (i+2 < n ? in[i+2] : 0);
    out[o++] = table[v >> 18 & 63]; out[o++] = table[v >> 12 & 63];
    out[o++] = i+1 < n ? table[v >> 6 & 63] : '='; out[o++] = i+2 < n ? table[v & 63] : '=';
  }
  out[o] = 0;
}

void info() {
  size_t addr = 0, size = 0;
  if (esp_core_dump_image_get(&addr, &size) != ESP_OK) {
    Serial.printf("CRASH none stored; this boot followed a %s, up %lu s\n", resetName(esp_reset_reason()), (unsigned long)(millis()/1000)); return;
  }
  char reason[96] = "unknown";
  esp_core_dump_get_panic_reason(reason, sizeof(reason));
  static esp_core_dump_summary_t s;
  if (esp_core_dump_get_summary(&s) != ESP_OK) {
    Serial.printf("CRASH stored %u bytes; summary unavailable, use CRASH DUMP\nCRASH END\n", unsigned(size)); return;
  }
  Serial.printf("CRASH reason=%s\n", reason);
  Serial.printf("CRASH task=%s pc=0x%08x ra=0x%08x sp=0x%08x mcause=0x%x mtval=0x%08x\n",
                s.exc_task, unsigned(s.exc_pc), unsigned(s.ex_info.ra), unsigned(s.ex_info.sp),
                unsigned(s.ex_info.mcause), unsigned(s.ex_info.mtval));
  Serial.printf("CRASH a0-a7=%08x %08x %08x %08x %08x %08x %08x %08x\n",
                unsigned(s.ex_info.exc_a[0]), unsigned(s.ex_info.exc_a[1]), unsigned(s.ex_info.exc_a[2]), unsigned(s.ex_info.exc_a[3]),
                unsigned(s.ex_info.exc_a[4]), unsigned(s.ex_info.exc_a[5]), unsigned(s.ex_info.exc_a[6]), unsigned(s.ex_info.exc_a[7]));
  Serial.printf("CRASH elf_sha256=%.16s size=%u\n", s.app_elf_sha256, unsigned(size));
  // Stack words, oldest last; the host tool symbolises the ones that look like code.
  Serial.printf("CRASH stack=");
  for (uint32_t i = 0; i + 4 <= s.exc_bt_info.dump_size; i += 4) {
    uint32_t word; memcpy(&word, s.exc_bt_info.stackdump + i, 4);
    Serial.printf("%08x ", unsigned(word));
  }
  Serial.printf("\nCRASH END\n");
}

void dump() {
  size_t addr = 0, size = 0;
  if (esp_core_dump_image_get(&addr, &size) != ESP_OK) { Serial.println("CRASH none stored"); return; }
  Serial.printf("COREDUMP BEGIN %u\n", unsigned(size));
  uint8_t buffer[48]; char line[68];
  for (size_t offset = 0; offset < size; offset += sizeof(buffer)) {
    const size_t n = min(sizeof(buffer), size - offset);
    if (esp_flash_read(NULL, buffer, addr + offset, n) != ESP_OK) { Serial.println("COREDUMP ERR read"); return; }
    base64Line(buffer, n, line);
    Serial.println(line);
  }
  Serial.println("COREDUMP END");
}

void command(const char *what) {
  if (!strcmp(what, "INFO")) info();
  else if (!strcmp(what, "DUMP")) dump();
  else if (!strcmp(what, "CLEAR")) Serial.println(esp_core_dump_image_erase() == ESP_OK ? "OK crash log cleared" : "ERR clearing crash log");
  else Serial.println("ERR CRASH [INFO|DUMP|CLEAR]");
}
}
