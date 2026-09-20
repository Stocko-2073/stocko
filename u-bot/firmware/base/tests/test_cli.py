#!/usr/bin/env python3
"""Exercise the actual native Mac executable against a small WebSocket peer."""
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / 'app/Packages/UBotCore/.build/debug/ubotctl'


def send(sock, obj):
    data = json.dumps(obj).encode()
    sock.sendall(bytes([0x81]) + (bytes([len(data)]) if len(data) < 126 else b'\x7e' + struct.pack('!H', len(data))) + data)


def exact(sock, n):
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise EOFError()
        data += chunk
    return data


def receive(sock):
    a, b = exact(sock, 2)
    n = b & 127
    if n == 126:
        n = struct.unpack('!H', exact(sock, 2))[0]
    if n == 127:
        n = struct.unpack('!Q', exact(sock, 8))[0]
    assert b & 128 and a & 15 == 1, 'client must use masked text frames'
    mask = exact(sock, 4)
    data = exact(sock, n)
    return json.loads(bytes(v ^ mask[i % 4] for i, v in enumerate(data)))


class Peer:
    def __init__(self, scenario, protocol=1):
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        self.error = None
        self.scenario = scenario
        self.protocol = protocol
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            s, _ = self.sock.accept()
            with s:
                s.settimeout(5)
                req = b''
                while b'\r\n\r\n' not in req:
                    req += s.recv(4096)
                assert req.startswith(b'GET /manage HTTP/1.1')
                headers = dict(line.split(': ', 1) for line in req.decode().split('\r\n')[1:] if ': ' in line)
                key = next(v for k, v in headers.items() if k.lower() == 'sec-websocket-key')
                accept = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                s.sendall(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + '\r\n\r\n').encode())
                send(s, dict(type='hello', protocol=self.protocol, boot='test', session=42, version='test', project='ubot_base', target='esp32s3'))
                self.scenario(s)
        except Exception as e:
            self.error = e
        finally:
            self.sock.close()


class CLIContract(unittest.TestCase):
    def run_cli(self, args, scenario, protocol=1, expected=0):
        peer = Peer(scenario, protocol)
        p = subprocess.run([str(CLI), *args, '--wifi', f'127.0.0.1:{peer.port}', '--timeout', '1'], capture_output=True, text=True, timeout=7)
        peer.thread.join(6)
        if peer.error:
            raise peer.error
        self.assertEqual(p.returncode, expected, p.stderr + p.stdout)
        return p

    def test_acceptance_is_not_completion(self):
        def peer(s):
            r = receive(s)
            self.assertEqual(r['session'], 42)
            self.assertEqual(r['args'], ['drive', '0.1', '0', '2'])
            send(s, dict(type='accepted', id=r['id'], job=8))
            time.sleep(.1)
            send(s, dict(type='output', id=r['id'], job=8, data='physical units\n'))
            send(s, dict(type='finished', id=r['id'], job=8, code=0))
            time.sleep(.1)
        p = self.run_cli(['exec', 'drive', '0.1', '0', '2'], peer)
        self.assertIn('physical units', p.stdout)

    def test_refusal_exit(self):
        def peer(s):
            r = receive(s)
            send(s, dict(type='finished', id=r['id'], code=1, error='busy'))
            time.sleep(.1)
        self.run_cli(['exec', 'enable'], peer, expected=1)

    def test_timeout(self):
        def peer(s):
            receive(s)
            time.sleep(1.3)
        self.run_cli(['exec', 'status'], peer, expected=124)

    def test_explicit_ota_timeout(self):
        image = bytearray(512)
        image[0], image[12] = 0xe9, 9
        image[48:53] = b'1.2.3'
        image[80:89] = b'ubot_base'
        with tempfile.NamedTemporaryFile(suffix='.bin') as file:
            file.write(image)
            file.flush()
            self.run_cli(['ota', 'upload', file.name], lambda s: time.sleep(1.4), expected=124)

    def test_lost_connection(self):
        self.run_cli(['exec', 'status'], lambda s: receive(s), expected=4)

    def test_unsupported(self):
        self.run_cli(['diagnostics'], lambda s: time.sleep(.1), protocol=9, expected=3)

    def test_json_and_credential_arguments(self):
        def peer(s):
            r = receive(s)
            self.assertEqual(r['args'], ['wifi', 'set', 'test network', 'test password'])
            send(s, dict(type='finished', id=r['id'], code=0))
            time.sleep(.1)
        p = self.run_cli(['wifi', 'set', 'test network', 'test password', '--json'], peer)
        for line in p.stdout.splitlines():
            json.loads(line)
        self.assertNotIn('test password', p.stdout + p.stderr)

    def test_paginated_retained_result(self):
        def peer(s):
            r = receive(s)
            self.assertEqual(r['op'], 'result')
            send(s, dict(type='result', id=r['id'], job=3, data='abc', next=3, total=6, done=True, code=0))
            r = receive(s)
            self.assertEqual(r['offset'], 3)
            send(s, dict(type='result', id=r['id'], job=3, data='def', next=6, total=6, done=True, code=0))
            time.sleep(.1)
        self.assertEqual(self.run_cli(['jobs', 'result', '3'], peer).stdout, 'abcdef')


if __name__ == '__main__':
    unittest.main(verbosity=2)
