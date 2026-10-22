#!/usr/bin/env python3
"""Deliberate wireless OTA rollback; requires a confirmed image and valid fallback."""
import argparse
import json
from pathlib import Path
import time
from ota_probe import inspect_image, open_upload
from wireless_client import Client

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--host', default='ubot.local')
p.add_argument('--image',type=Path,required=True)
a=p.parse_args()
start=time.monotonic()
def record(kind,**fields):
    print(json.dumps(dict(test=kind,elapsed=round(time.monotonic()-start,2),**fields)),flush=True)

before=Client(a.host)
original=before.hello
state,text=before.execute(['ota'])
assert state['code']==0 and '(valid)' in text and 'verified fallback available' in text,text
record('before',hello=original,ota=text)
before.close()
data=a.image.read_bytes()
m=inspect_image(data)
c=open_upload(a.host,m)
for off in range(0,len(data),4096):
    c.send(data[off:off+4096])
r=c.getresponse()
assert r.status==200,(r.status,r.read())
record('written-unconfirmed',response=r.read().decode())
c.close()

def next_boot(prior,limit):
    end=time.monotonic()+limit
    while time.monotonic()<end:
        peer=None
        try:
            peer=Client(a.host,timeout=3)
            if peer.hello['boot']!=prior:
                return peer
        except (OSError,EOFError):
            pass
        finally:
            if peer and peer.hello['boot']==prior:
                peer.close()
        time.sleep(2)
    raise TimeoutError('no new boot')

candidate=next_boot(original['boot'],45)
assert candidate.hello['version']==m['version'] and candidate.hello['image']==m['image']
state,text=candidate.execute(['ota'])
assert 'pending updater confirmation' in text and 'verified fallback available' in text,text
record('candidate-pending',hello=candidate.hello,ota=text)
state,text=candidate.execute(['enable'])
assert state['code']==1 and 'firmware update in progress' in text,text
record('pending-motor-interlock',code=state['code'],output=text)
rid=candidate.send('confirm',version=m['version'],image='0'*64,boot=candidate.hello['boot'])
state=candidate.wait('finished',rid)
assert state['code']==1,state
record('wrong-confirmation-rejected',code=state['code'])
candidate_boot=candidate.hello['boot']
candidate.close()
restored=next_boot(candidate_boot,145)
assert restored.hello['version']==original['version'] and restored.hello['image']==original['image']
state,text=restored.execute(['ota'])
assert '(valid)' in text and 'rollback: confirmation timeout' in text,text
record('rollback-passed',hello=restored.hello,ota=text)
restored.close()
