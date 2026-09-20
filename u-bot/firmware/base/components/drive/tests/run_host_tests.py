#!/usr/bin/env python3
"""Compile real VelGen/MotorCurrent with a simulated UART and minimal IDF types."""
from pathlib import Path
import subprocess
import tempfile

here = Path(__file__).resolve().parent
stubs = {
    'driver/uart.h': 'typedef int uart_port_t;\n',
    'freertos/FreeRTOS.h': '#define pdMS_TO_TICKS(x) (x)\n',
    'freertos/semphr.h': 'typedef void* SemaphoreHandle_t;\n',
    'freertos/task.h': 'inline void vTaskDelay(unsigned) {}\n',
    'esp_rom_sys.h': 'inline void esp_rom_delay_us(unsigned) {}\n',
    'esp_task_wdt.h': 'inline void esp_task_wdt_reset() {}\n',
    'esp_timer.h': '#include <stdint.h>\ninline int64_t esp_timer_get_time() { static int64_t t=0; return ++t; }\n',
}
with tempfile.TemporaryDirectory(prefix='ubot-drive-tests-') as tmp:
    root = Path(tmp)
    for name, body in stubs.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('#pragma once\n' + body)
    exe = root / 'drive-tests'
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-I', str(root), '-I', str(here.parent),
                    str(here / 'test_velgen.cpp'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
