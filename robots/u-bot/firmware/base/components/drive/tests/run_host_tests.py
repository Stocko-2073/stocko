#!/usr/bin/env python3
"""Build and run every drive host test (tests/test_*.cpp), each as its own binary.

The drive code compiles unmodified against a handful of generated IDF stubs.
Time is tests/fake_clock.h: esp_timer_get_time() reads it and vTaskDelay /
esp_rom_delay_us advance it, so a blocking firmware routine (calibrate()'s
pumps, VelGen::begin()'s delays) moves a simulated plant instead of sleeping.

Firmware sources a test may need (AS5600.cpp) go into a static library, so the
linker pulls them into the tests that use them and leaves the rest alone.

Usage: run_host_tests.py [name ...]   e.g. `plant` builds and runs test_plant.cpp only.
Exits nonzero if any test fails to build, fails, or times out.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile

here = Path(__file__).resolve().parent
drive = here.parent

CXX = os.environ.get('CXX', 'c++')
# -fno-sanitize-recover makes undefined behaviour fail the test instead of
# printing a warning and exiting 0.
FLAGS = ['-std=c++17', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
         '-fno-sanitize-recover=all', '-g']
LIBRARY = ['AS5600.cpp']
TIMEOUT_S = 300

stubs = {
    'driver/uart.h': 'typedef int uart_port_t;\n',
    'driver/i2c_master.h': 'typedef struct i2c_master_bus_t *i2c_master_bus_handle_t;\n'
                           'typedef struct i2c_master_dev_t *i2c_master_dev_handle_t;\n',
    'freertos/FreeRTOS.h': '#define pdMS_TO_TICKS(x) (x)\n',
    'freertos/semphr.h': 'typedef void* SemaphoreHandle_t;\n',
    # One tick is 1 ms, as sdkconfig.defaults sets it on the robot.
    'freertos/task.h': '#include <stdint.h>\n#include "fake_clock.h"\n'
                       'inline void vTaskDelay(unsigned ticks) { FakeClock::advance((int64_t)ticks * 1000); }\n',
    'esp_rom_sys.h': '#include "fake_clock.h"\n'
                     'inline void esp_rom_delay_us(unsigned us) { FakeClock::advance(us); }\n',
    'esp_task_wdt.h': 'inline void esp_task_wdt_reset() {}\n',
    'esp_timer.h': '#include <stdint.h>\n#include "fake_clock.h"\n'
                   'inline int64_t esp_timer_get_time() { return FakeClock::now(); }\n',
    # Logging compiles away, but its arguments still count as used.
    'esp_log.h': 'template <typename... A> inline void esp_log_discard(const char *, A &&...) {}\n'
                 + ''.join(f'#define ESP_LOG{level}(tag, ...) esp_log_discard(tag, __VA_ARGS__)\n'
                           for level in 'EWIDV'),
}


def run(cmd, **kw):
    """Run a command, returning (ok, combined stdout+stderr)."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kw)
        return p.returncode == 0, p.stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or '')
        return False, out + f'\n*** timed out after {kw.get("timeout")} s\n'


def main():
    wanted = sys.argv[1:]
    tests = sorted(p for p in here.glob('test_*.cpp')
                   if not wanted or any(w in p.stem for w in wanted))
    if not tests:
        print(f'no tests match {wanted}' if wanted else f'no test_*.cpp in {here}')
        return 2

    env = dict(os.environ)
    env.setdefault('UBSAN_OPTIONS', 'print_stacktrace=1')
    env.setdefault('MallocNanoZone', '0')   # macOS: silences ASan's nano-zone warning

    with tempfile.TemporaryDirectory(prefix='ubot-drive-tests-') as tmp:
        root = Path(tmp)
        for name, body in stubs.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('#pragma once\n' + body)
        includes = ['-I', str(root), '-I', str(drive), '-I', str(here)]

        objs = []
        for src in LIBRARY:
            obj = root / (Path(src).stem + '.o')
            ok, out = run([CXX, *FLAGS, *includes, '-c', str(drive / src), '-o', str(obj)])
            if not ok:
                print(f'== {src}: build failed ==\n{out}')
                return 1
            objs.append(str(obj))
        lib = root / 'libdrive_host.a'
        ok, out = run(['ar', 'rcs', str(lib), *objs])
        if not ok:
            print(f'== ar failed ==\n{out}')
            return 1

        def build(test):
            exe = root / test.stem
            ok, out = run([CXX, *FLAGS, *includes, str(test), str(lib), '-o', str(exe)])
            return ok, exe, out

        def build_and_run(test):
            ok, exe, out = build(test)
            if not ok:
                return 'build failed', out
            ok, out = run([str(exe)], env=env, timeout=TIMEOUT_S)
            return ('ok' if ok else 'FAILED'), out

        workers = min(len(tests), os.cpu_count() or 2)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [(t, pool.submit(build_and_run, t)) for t in tests]
            results = []
            for test, fut in futures:
                verdict, out = fut.result()
                print(f'== {test.stem}: {verdict} ==')
                if out:
                    print(out.rstrip())
                sys.stdout.flush()
                results.append((test.stem, verdict))

    failed = [f'{name} ({verdict})' for name, verdict in results if verdict != 'ok']
    print(f'\n{len(results) - len(failed)}/{len(results)} host tests passed'
          + (f'; failed: {", ".join(failed)}' if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
