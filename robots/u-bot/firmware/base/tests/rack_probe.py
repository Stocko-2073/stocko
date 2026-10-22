#!/usr/bin/env python3
"""Rack-only motion acceptance: wheels MUST be safely clear. Never opens USB."""
import argparse
import json
import time
from wireless_client import Client

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--host', default='ubot.local')
p.add_argument('--rack-ready', action='store_true', required=True)
a = p.parse_args()
results = []
observer = Client(a.host)
boot = observer.hello['boot']


def record(name, **fields):
    result = dict(test=name, **fields)
    results.append(result)
    print(json.dumps(result), flush=True)


def disconnected_job(words, limit=65):
    initiator = Client(a.host)
    rid = initiator.send('exec', args=words)
    accepted = initiator.wait('accepted', rid)
    jid = accepted['job']
    initiator.close()
    end = time.monotonic() + limit
    while time.monotonic() < end:
        state, text = observer.result(jid)
        if state['done']:
            record('disconnected-' + words[0], job=jid, code=state['code'], result=text)
            assert state['code'] == 0, text
            return
        time.sleep(.5)
    raise TimeoutError(words)


try:
    state, text = observer.execute(['enable'])
    assert state['code'] == 0, text
    disconnected_job(['cal', 'A'])
    state, text = observer.execute(['cal', 'show'])
    record('calibration-result', code=state['code'], result=text)
    disconnected_job(['demo', 'short'])
    disconnected_job(['wheel', 'A', 'move', '0.1'])
    # Keep the socket, but deliberately stop renewing its lease.
    initiator = Client(a.host)
    rid = initiator.send('exec', args=['drive', '0.03', '0', '0'])
    jid = initiator.wait('accepted', rid)['job']
    time.sleep(.25)
    renewal = initiator.send('renew', job=jid, seq=1)
    assert initiator.wait('finished', renewal)['code'] == 0
    renewal = initiator.send('renew', job=jid, seq=1)
    assert initiator.wait('finished', renewal)['code'] == 1
    time.sleep(1.5)
    state, text = observer.result(jid)
    assert state['done'] and state['code'] == 124, state
    renewal = initiator.send('renew', job=jid, seq=2)
    assert initiator.wait('finished', renewal)['code'] == 1
    initiator.close()
    state, text = observer.execute(['status'])
    assert 'command: idle' in text
    record('lease-expiry-and-replay', code=124, status=text)
    # Cancellation is independently callable while the command worker is free.
    rid = observer.send('exec', args=['demo', 'short'])
    jid = observer.wait('accepted', rid)['job']
    time.sleep(.4)
    cancel = observer.send('cancel', job=jid)
    assert observer.wait('finished', cancel)['code'] == 0
    time.sleep(.4)
    state, text = observer.result(jid)
    assert state['done'] and state['code'] == 130, state
    record('job-cancellation', code=130)
finally:
    try:
        rid = observer.send('estop')
        observer.wait('finished', rid)
    finally:
        observer.close()
