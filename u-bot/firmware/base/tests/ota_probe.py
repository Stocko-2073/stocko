#!/usr/bin/env python3
"""Non-motion wireless negative OTA checks. USB is never opened."""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import socket
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from release_manifest import inspect_image


def headers(m):
    return {'Content-Length': str(m['size']), **{
        'X-Ubot-' + header: m[key] for header, key in
        [('Version', 'version'), ('Project', 'project'), ('Target', 'target'),
         ('SHA256', 'sha256'), ('Image', 'image')]}}


def open_upload(host, m):
    c = http.client.HTTPConnection(host, timeout=30)
    c.putrequest('POST', '/ota')
    for k, v in headers(m).items():
        c.putheader(k, v)
    c.endheaders()
    return c


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default='ubot.local')
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('mode', choices=['corrupt', 'interrupt', 'wrong-target', 'wrong-project', 'wrong-size', 'wrong-image-target', 'wrong-image-project', 'withhold'])
    a = p.parse_args()
    data = bytearray(a.image.read_bytes())
    m = inspect_image(data)
    if a.mode == 'wrong-target':
        m['target'] = 'esp32'
    if a.mode == 'wrong-project':
        m['project'] = 'different_project'
    if a.mode == 'wrong-size':
        m['size'] = 0x1e0001
    if a.mode == 'corrupt':
        data[-1] ^= 1
    if a.mode.startswith('wrong-image-'):
        data[12 if a.mode.endswith('target') else 80] ^= 1
        m['sha256'] = hashlib.sha256(data).hexdigest()
    c = open_upload(a.host, m)
    if a.mode.startswith('wrong-image-'):
        c.send(data[:288])
        r = c.getresponse()
        assert r.status == 409, r.status
        print(json.dumps(dict(test=a.mode, status=r.status, passed=True)))
        c.close()
        return
    if a.mode.startswith('wrong-'):
        c.send(data[:1])
        r = c.getresponse()
        assert r.status == 400, r.status
        print(json.dumps(dict(test=a.mode, status=r.status, passed=True)))
        c.close()
        return
    if a.mode == 'interrupt':
        c.send(data[:8192])
        c.close()
        print(json.dumps(dict(test=a.mode, sent=8192, disconnected=True)))
        return
    for off in range(0, len(data), 4096):
        c.send(data[off:off + 4096])
        if a.mode == 'corrupt':
            time.sleep(.01)  # leave time to probe the update interlock
    r = c.getresponse()
    response = r.read().decode()
    expected = 200 if a.mode == 'withhold' else 409
    assert r.status == expected, (r.status, response)
    print(json.dumps(dict(test=a.mode, status=r.status, response=response, passed=True)), flush=True)
    c.close()
    if a.mode == 'withhold':
        print('Candidate deliberately not confirmed; wait 120 seconds and inspect diagnostics.', flush=True)


if __name__ == '__main__':
    main()
