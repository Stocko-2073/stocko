#!/usr/bin/env python3
"""Wireless-only stability test: telemetry/logs, concurrent clients, BLE and reconnects."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import threading
import time
from wireless_client import Client

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--host', default='ubot.local')
p.add_argument('--ble', default='ubot')
p.add_argument('--minutes', type=float, default=30)
p.add_argument('--cli', type=Path, required=True)
a = p.parse_args()
lock = threading.Lock()
stop = threading.Event()
failures = []
started = time.monotonic()


def record(kind, **fields):
    with lock:
        print(json.dumps(dict(test=kind, elapsed=round(time.monotonic()-started, 2), **fields)), flush=True)


primary = Client(a.host, timeout=5)
boot = primary.hello['boot']
record('start', hello=primary.hello, seconds=a.minutes*60)
assert primary.execute(['stats', 'reset'])[0]['code'] == 0
assert primary.execute(['stream', 'on', '20'])[0]['code'] == 0
rid = primary.send('logs', since=0)
assert primary.wait('finished', rid)['code'] == 0


def secondary():
    try:
        while not stop.is_set():
            client = Client(a.host)
            assert client.hello['boot'] == boot, client.hello
            state, output = client.execute(['free'])
            assert state['code'] == 0
            record('reconnect', boot=boot, output=output)
            client.close()
            command = subprocess.run([str(a.cli), 'exec', 'version', '--ble', a.ble,
                                      '--json', '--timeout', '20'],
                                     capture_output=True, text=True, timeout=25)
            assert command.returncode == 0, command.stdout + command.stderr
            events = [json.loads(line) for line in command.stdout.splitlines()]
            hello = next(event for event in events if event['type'] == 'hello')
            assert hello['boot'] == boot, hello
            record('ble', boot=hello['boot'], code=command.returncode)
            stop.wait(60)
    except Exception as error:
        failures.append(repr(error))
        record('secondary-failed', error=repr(error))
        stop.set()


def slow_reader():
    try:
        client = Client(a.host)
        client.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        assert client.execute(['stream', 'on', '50'])[0]['code'] == 0
        # The robot must continue serving primary and BLE while this fills TCP buffers.
        stop.wait(90)
        client.close()
        record('slow-reader-disconnected')
    except Exception as error:
        failures.append(repr(error))
        record('slow-reader-failed', error=repr(error))
        stop.set()


threads = [threading.Thread(target=secondary), threading.Thread(target=slow_reader)]
for thread in threads:
    thread.start()
counts = dict(stream=0, log=0, completed=0, stream_gaps=0, log_lost=0, reported_dropped=0)
last_seq = 0
pending = None
next_command = time.monotonic()
next_report = next_command + 60
commands = [['status'], ['set'], ['wheel', 'A', 'reg', '6F'], ['free'], ['stats']]
try:
    while not stop.is_set() and (time.monotonic()-started < a.minutes*60 or pending):
        now = time.monotonic()
        if pending is None and now >= next_command and now-started < a.minutes*60:
            args = commands[counts['completed'] % len(commands)]
            pending = dict(id=primary.send('exec', args=args), sent=now, output='', args=args)
            next_command = now + 10
        event = primary.receive()
        counts['reported_dropped'] = max(counts['reported_dropped'], event.get('dropped', 0))
        kind = event['type']
        if kind == 'stream':
            counts['stream'] += 1
            seq = event['seq']
            if last_seq:
                assert seq > last_seq, event
                counts['stream_gaps'] += seq-last_seq-1
            last_seq = seq
        elif kind == 'log':
            counts['log'] += 1
            counts['log_lost'] += event.get('lost', 0)
        elif pending and event.get('id') == pending['id']:
            if kind == 'output':
                pending['output'] += event['data']
            elif kind == 'finished':
                assert event['code'] == 0, (event, pending)
                counts['completed'] += 1
                record('command', args=pending['args'], code=0,
                       latency=round(time.monotonic()-pending['sent'], 3), output=pending['output'])
                pending = None
        if pending:
            assert time.monotonic()-pending['sent'] < 15, pending
        if now >= next_report:
            record('minute', boot=boot, **counts)
            next_report += 60
    assert not failures, failures
    assert pending is None, pending
    assert counts['stream'] > a.minutes*60*10, counts
    state, output = primary.execute(['stats'])
    record('final-stats', code=state['code'], output=output)
    state, output = primary.execute(['free'])
    record('final-heap', code=state['code'], output=output)
    check = Client(a.host)
    assert check.hello['boot'] == boot
    check.close()
    record('passed', boot=boot, **counts)
finally:
    stop.set()
    primary.close()
    for thread in threads:
        thread.join(30)
