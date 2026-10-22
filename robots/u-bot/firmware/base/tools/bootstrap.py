#!/usr/bin/env python3
"""Install management into the unused slot, preserving application and NVS.

Requires the verified full-flash backup created immediately before installation.
Does not enable motors. Confirmation must be done over Wi-Fi or BLE within 120s.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib
from release_manifest import inspect_image


def record(seq, state):
    return struct.pack('<I20sII', seq, bytes([255]) * 20, state,
                       zlib.crc32(struct.pack('<I', seq), 0xffffffff))


def prepare(backup, image):
    data = backup.read_bytes()
    if len(data) != 0x400000:
        raise ValueError('full 4 MB backup required')
    entries = [struct.unpack('<I20xII', data[o:o+32]) for o in (0xf000, 0x10000)]
    seq, state, crc = entries[0]
    if (seq, state) != (1, 2) or crc != zlib.crc32(struct.pack('<I', seq), 0xffffffff):
        raise ValueError('this bootstrap requires confirmed ota_0 sequence 1')
    if data[0x200000:0x3e0000] != b'\xff' * 0x1e0000:
        raise ValueError('ota_1 is not empty; inspect layout before installing')
    if entries[1] != (0xffffffff, 0xffffffff, 0xffffffff):
        raise ValueError('second OTA record is not erased')
    metadata = inspect_image(image.read_bytes())
    ota = bytearray(data[0xf000:0x11000])
    ota[4096:4096+32] = record(2, 0)  # NEW: bootloader moves to pending verify
    return ota, metadata


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backup', type=Path, required=True)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--port', required=True)
    p.add_argument('--cli', type=Path, required=True)
    p.add_argument('--wifi', default='ubot.local')
    p.add_argument('--install', action='store_true', help='otherwise only prepare/validate')
    a = p.parse_args()
    ota, metadata = prepare(a.backup, a.image)
    output = a.backup.parent / 'bootstrap-otadata.bin'
    output.write_bytes(ota)
    (a.backup.parent / 'bootstrap-manifest.json').write_text(json.dumps(metadata, indent=2))
    print('Prepared pending', metadata['version'], 'in ota_1; ota_0 and NVS preserved.', flush=True)
    if a.install:
        subprocess.run([sys.executable, '-m', 'esptool', '--chip', 'esp32s3',
                        '--port', a.port, '--baud', '460800', 'write-flash',
                        '0x200000', str(a.image), '0xf000', str(output)], check=True)
        # Native CLI opens a fresh management session and supplies the local
        # image identity. Retry read/connect failures; never replay an update.
        import time
        for _ in range(8):
            time.sleep(3)
            completed = subprocess.run([str(a.cli), 'ota', 'confirm', metadata['version'],
                                        metadata['image'], '--wifi', a.wifi, '--timeout', '8'])
            if completed.returncode == 0:
                print('Bootstrap confirmed over Wi-Fi.', flush=True)
                return
        raise SystemExit('Bootstrap unconfirmed: candidate will roll back. Inspect radio startup; USB remains recovery.')


if __name__ == '__main__':
    main()
