#!/usr/bin/env python3
"""Compile the pure battery model with its tests under ASan/UBSan and run them."""
from pathlib import Path
import subprocess
import tempfile

here = Path(__file__).resolve().parent
component = here.parent
include = component / 'include'
model = component / 'battery_model.c'
with tempfile.TemporaryDirectory(prefix='ubot-battery-tests-') as tmp:
    root = Path(tmp)
    # The model promises plain C99 and a header drive.cpp can include; check
    # both before testing behaviour.
    subprocess.run(['cc', '-std=c99', '-pedantic', '-Wall', '-Wextra', '-Werror', '-fsyntax-only',
                    '-I', str(include), str(model)], check=True)
    header = root / 'header.cpp'
    header.write_text('#include "battery_model.h"\n')
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fsyntax-only',
                    '-I', str(include), str(header)], check=True)
    exe = root / 'battery-tests'
    # -fno-sanitize-recover makes undefined behaviour fail the run instead of
    # printing a warning and passing.
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all', '-g', '-I', str(include),
                    str(model), str(here / 'test_battery_model.c'), '-lm', '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=60)
