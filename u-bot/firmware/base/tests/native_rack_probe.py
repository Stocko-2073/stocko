#!/usr/bin/env python3
"""Final native CLI rack checks; requires both wheels clear."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import time
from wireless_client import Client
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--host',default='ubot.local')
p.add_argument('--cli',type=Path,required=True)
p.add_argument('--rack-ready',action='store_true',required=True)
a=p.parse_args()
cli=str(a.cli)
observer=Client(a.host)
try:
    assert observer.execute(['enable'])[0]['code']==0
    process=subprocess.Popen([cli,'exec','demo','short','--wifi',a.host],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    time.sleep(1)
    process.send_signal(signal.SIGINT)
    out,err=process.communicate(timeout=8)
    assert process.returncode==130,(process.returncode,out,err)
    time.sleep(.2)
    _,status=observer.execute(['status'])
    assert 'command: idle' in status,status
    print(json.dumps(dict(test='native-ctrl-c',code=process.returncode,output=out+err)),flush=True)
    for radio in [['--wifi',a.host],[]]:
        process=subprocess.run([cli,'drive','0.1','0','1',*radio],capture_output=True,text=True,timeout=20)
        assert process.returncode==0,(process.returncode,process.stdout,process.stderr)
        assert '0.020' in process.stdout,process.stdout
        print(json.dumps(dict(test='legacy-normalized-drive',transport='wifi' if radio else 'ble',code=0,output=process.stdout+process.stderr)),flush=True)
finally:
    rid=observer.send('estop')
    observer.wait('finished',rid)
    observer.close()
