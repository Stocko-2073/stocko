"""The Bonjour advertisement must not outlive the server: a stale one sends the
phone to a dead port ("Sending to the Mac stalled")."""

import subprocess
import sys
import time
import uuid

SERVER = """
import asyncio, sys
from agentcam.bonjour import Advertisement

async def main():
    ad = Advertisement(1, "test")
    ad.command = [sys.executable, "-c", "import time; time.sleep(60)", "advert-" + sys.argv[1]]  # for dns-sd
    await ad.start()
    print("up", flush=True)
    if sys.argv[2] == "stop":
        await ad.stop()
        print("stopped", flush=True)
    await asyncio.sleep(60)

asyncio.run(main())
"""


def advertising(marker: str) -> bool:
    return subprocess.run(["pgrep", "-f", f"advert-{marker}"], capture_output=True).returncode == 0


def gone_soon(marker: str) -> bool:
    deadline = time.monotonic() + 3
    while advertising(marker):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def test_a_killed_server_takes_its_advertisement_with_it():
    marker = uuid.uuid4().hex
    server = subprocess.Popen([sys.executable, "-c", SERVER, marker, "run"], stdout=subprocess.PIPE)
    try:
        assert server.stdout.readline() == b"up\n"
        assert advertising(marker)
        server.kill()                                  # no cleanup runs
        server.wait()
        assert gone_soon(marker)
    finally:
        server.kill()
        subprocess.run(["pkill", "-f", f"advert-{marker}"])


def test_stop_ends_the_advertisement():
    marker = uuid.uuid4().hex
    server = subprocess.Popen([sys.executable, "-c", SERVER, marker, "stop"], stdout=subprocess.PIPE)
    try:
        assert server.stdout.readline() == b"up\n"
        assert server.stdout.readline() == b"stopped\n"
        assert gone_soon(marker)
    finally:
        server.kill()
        subprocess.run(["pkill", "-f", f"advert-{marker}"])
