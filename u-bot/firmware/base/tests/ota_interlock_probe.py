#!/usr/bin/env python3
"""Corrupt streamed upload, competing upload and zero-motion refusal on both radios."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import subprocess
import threading
import time
from ota_probe import inspect_image, open_upload

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--host', default='ubot.local')
p.add_argument('--ble', default='ubot')
p.add_argument('--image', type=Path, required=True)
p.add_argument('--cli', type=Path, required=True)
a = p.parse_args()
data = bytearray(a.image.read_bytes())
metadata = inspect_image(data)
data[-1] ^= 1
started = threading.Event()


def upload():
    c = open_upload(a.host, metadata)
    for off in range(0, len(data), 4096):
        c.send(data[off:off + 4096])
        if off >= 8192:
            started.set()
        time.sleep(.04)
    r = c.getresponse()
    body = r.read().decode()
    c.close()
    assert r.status == 409, (r.status, body)
    return {'test': 'corrupt-upload', 'status': r.status, 'passed': True}


def refuse(mode, value):
    result = subprocess.run([str(a.cli), 'exec', 'drive', '0', '0', '1', mode, value,
                             '--timeout', '15'], capture_output=True, text=True, timeout=20)
    output = result.stdout + result.stderr
    passed = result.returncode == 1 and 'motion or update already active' in output
    return dict(test='ota-motion-refusal', transport=mode, code=result.returncode,
                passed=passed, output=output)


with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    transfer = pool.submit(upload)
    assert started.wait(10)
    time.sleep(.5)
    checks = [pool.submit(refuse, '--wifi', a.host), pool.submit(refuse, '--ble', a.ble)]
    second = open_upload(a.host, metadata)
    second.send(data[:1])  # ESP-IDF dispatches a body-bearing request on its first body byte.
    response = second.getresponse()
    assert response.status == 409, response.status
    second.close()
    results = [dict(test='concurrent-upload', status=response.status, passed=True)]
    results += [check.result() for check in checks]
    results.append(transfer.result())
print(json.dumps(results, indent=2))
assert all(r['passed'] for r in results), results
