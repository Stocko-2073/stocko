"""Small synchronous management client for hardware acceptance (stdlib only)."""
import base64
import hashlib
import json
import os
import socket
import struct
import time


class Client:
    def __init__(self, host='ubot.local', timeout=10):
        self.sock = socket.create_connection((host, 80), timeout=timeout)
        self.buf = bytearray()
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f'GET /manage HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        while b'\r\n\r\n' not in self.buf:
            self.buf.extend(self.sock.recv(4096))
        header, rest = bytes(self.buf).split(b'\r\n\r\n', 1)
        self.buf = bytearray(rest)
        assert b'101 Switching Protocols' in header, header
        accept = base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        assert accept in header
        self.hello = self.receive()
        assert self.hello['type'] == 'hello' and self.hello['protocol'] == 1
        self.id = 0

    def exact(self, n):
        while len(self.buf) < n:
            data = self.sock.recv(4096)
            if not data:
                raise EOFError('WebSocket closed')
            self.buf.extend(data)
        data = bytes(self.buf[:n])
        del self.buf[:n]
        return data

    def frame(self, data, opcode=1):
        mask = os.urandom(4)
        size = len(data)
        header = bytes([0x80 | opcode])
        header += bytes([0x80 | size]) if size < 126 else b'\xfe' + struct.pack('!H', size)
        self.sock.sendall(header + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(data)))

    def receive(self):
        while True:
            a, b = self.exact(2)
            n = b & 127
            if n == 126:
                n = struct.unpack('!H', self.exact(2))[0]
            elif n == 127:
                n = struct.unpack('!Q', self.exact(8))[0]
            assert n < 4096 and not b & 128
            data = self.exact(n)
            if a & 15 == 8:
                raise EOFError('WebSocket close frame')
            if a & 15 == 9:
                self.frame(data, 10)
                continue
            return json.loads(data)

    def send(self, op, **fields):
        self.id += 1
        self.frame(json.dumps(dict(op=op, id=self.id, session=self.hello['session'], **fields)).encode())
        return self.id

    def wait(self, kind, request):
        while True:
            r = self.receive()
            if r.get('id') == request and r.get('type') == kind:
                return r
            if r.get('id') == request and r.get('type') == 'finished' and kind != 'finished':
                raise RuntimeError(r)

    def execute(self, args, **options):
        rid = self.send('exec', args=args, **options)
        output = ''
        while True:
            r = self.receive()
            if r.get('id') != rid:
                continue
            if r['type'] == 'output':
                output += r['data']
            elif r['type'] == 'finished':
                return r, output

    def result(self, job):
        offset, text = 0, ''
        while True:
            rid = self.send('result', job=job, offset=offset)
            r = self.wait('result', rid)
            text += r['data']
            offset = r['next']
            if offset >= r['total']:
                return r, text

    def close(self):
        try:
            self.frame(b'', 8)
        except OSError:
            pass
        self.sock.close()
