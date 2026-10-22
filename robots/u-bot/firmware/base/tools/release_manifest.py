#!/usr/bin/env python3
"""Read ESP application identity and produce the exact OTA manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def inspect_image(data):
    if len(data) < 288 or len(data) > 0x1E0000:
        raise ValueError('image does not fit the existing OTA slot')
    if data[0] != 0xE9 or struct.unpack_from('<H', data, 12)[0] != 9:
        raise ValueError('not an ESP32-S3 application')
    if struct.unpack_from('<I', data, 32)[0] != 0xABCD5432:
        raise ValueError('application descriptor missing')
    def field(start):
        value = data[start:start + 32]
        if b'\0' not in value:
            raise ValueError('unterminated application identity')
        return value.split(b'\0', 1)[0].decode('utf8')
    version, project = field(48), field(80)
    if project != 'ubot_base' or not version:
        raise ValueError('wrong project or empty version')
    return dict(version=version, project=project, target='esp32s3', size=len(data),
                sha256=hashlib.sha256(data).hexdigest(), image=data[176:208].hex())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('--base', required=True)
    p.add_argument('--version', required=True)
    a = p.parse_args()
    m = inspect_image(a.image.read_bytes())
    if m['version'] != a.version:
        p.error('image version differs from release version')
    if not a.base.startswith('https://'):
        p.error('HTTPS source required')
    m['url'] = f"{a.base.rstrip('/')}/releases/{m['version']}/{m['sha256']}.bin"
    print(json.dumps(m, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
