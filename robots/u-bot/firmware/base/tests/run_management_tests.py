#!/usr/bin/env python3
"""Run the production command service on pthread-backed FreeRTOS fakes."""
from pathlib import Path
import subprocess
import tempfile

base = Path(__file__).resolve().parents[1]
stubs = {
'esp_err.h': '''typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_INVALID_ARG 1
#define ESP_ERR_INVALID_STATE 2
#define ESP_ERR_NO_MEM 3
''',
'freertos/FreeRTOS.h': '''#include <stdint.h>
#define pdMS_TO_TICKS(x) (x)
#define pdTRUE 1
#define pdPASS 1
#define portMAX_DELAY 0xffffffff
''',
'freertos/queue.h': '''typedef struct queue *QueueHandle_t;
QueueHandle_t xQueueCreate(unsigned,unsigned);
int xQueueSend(QueueHandle_t,const void*,unsigned);
int xQueueReceive(QueueHandle_t,void*,unsigned);
unsigned uxQueueSpacesAvailable(QueueHandle_t);
void xQueueReset(QueueHandle_t);
void vQueueDelete(QueueHandle_t);
''',
'freertos/semphr.h': '''typedef void *SemaphoreHandle_t;
SemaphoreHandle_t xSemaphoreCreateMutex(void);
int xSemaphoreTake(SemaphoreHandle_t,unsigned);
void xSemaphoreGive(SemaphoreHandle_t);
''',
'freertos/task.h': '''typedef void *TaskHandle_t;
int xTaskCreate(void(*)(void*),const char*,unsigned,void*,unsigned,TaskHandle_t*);
void vTaskDelay(unsigned);
''',
'esp_app_desc.h': 'int esp_app_get_elf_sha256(char*,unsigned);\n',
'esp_random.h': '#include <stdint.h>\nuint32_t esp_random(void);\n',
'esp_timer.h': '#include <stdint.h>\nint64_t esp_timer_get_time(void);\n',
'sysinfo.h': '''const char *sysinfo_fw_version(void);
void sysinfo_image_id(char out[65]);
const char *sysinfo_project(void);
const char *sysinfo_reset_reason(void);
''',
'net.h': '''#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
void net_ota_outcome(char*,size_t);
esp_err_t net_ota_confirm(void);
bool net_wifi_trial_busy(void);
int net_wifi_trial_result(void);
void net_wifi_trial_cancel(void);
void net_ota_cancel(void);
bool net_ota_busy(void);
const char *net_ota_status(void);
''',
}
with tempfile.TemporaryDirectory(prefix='ubot-management-tests-') as tmp:
    root = Path(tmp)
    for name, text in stubs.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('#pragma once\n' + text)
    exe = root / 'management-tests'
    cjson = base / 'managed_components/espressif__cjson/cJSON'
    subprocess.run(['cc', '-std=c11', '-g', '-fsanitize=address,undefined',
                    '-Wall', '-Wextra', '-Wno-deprecated-declarations', '-Wno-unused-parameter', '-pthread',
                    '-I', str(root), '-I', str(cjson),
                    '-I', str(base / 'components/management/include'),
                    '-I', str(base / 'components/drive/include'),
                    '-I', str(base / 'components/ulog/include'),
                    str(base / 'tests/test_management.c'),
                    str(base / 'components/management/management.c'),
                    str(cjson / 'cJSON.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=20)
