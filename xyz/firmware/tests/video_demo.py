#!/usr/bin/env python3
"""Five-second camera lead-in, then the firmware's XY square/circle demo x3."""
import argparse
import os
import select
import termios
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", default="/dev/cu.usbmodem2101")
args = parser.parse_args()
fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
original = termios.tcgetattr(fd)


def exchange(command, expected, timeout=3):
    termios.tcflush(fd, termios.TCIFLUSH)
    os.write(fd, command.encode("ascii"))
    output = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        readable, _, _ = select.select([fd], [], [], 0.1)
        if readable:
            output += os.read(fd, 4096)
        response = output.decode("ascii", errors="replace")
        if "ERR" in response:
            raise RuntimeError(response)
        if expected in response:
            print(response.strip(), flush=True)
            return response
    raise TimeoutError(f"Expected {expected!r}; received {output!r}")


try:
    attrs = termios.tcgetattr(fd)
    attrs[0] = attrs[1] = attrs[3] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[4] = attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    time.sleep(1)
    exchange("\nSTOP\n", "OK disabled")
    status = exchange("STATUS\n", "A motor=")
    if "X motor=0" not in status or "Y motor=1" not in status:
        raise RuntimeError("Demo requires X=M0 and Y=M1")
    for seconds in range(5, 0, -1):
        print(f"Motion starts in {seconds}...", flush=True)
        time.sleep(1)
    exchange("ARM\n", "OK armed")
    started = time.monotonic()
    exchange("DEMO\n", "DONE", timeout=45)
    print(f"Demo completed in {time.monotonic()-started:.3f} s", flush=True)
    exchange("OFF\n", "OK disabled")
    exchange("STATUS\n", "A motor=")
finally:
    try:
        os.write(fd, b"!\nSTOP\n")
        termios.tcdrain(fd)
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, original)
        os.close(fd)
