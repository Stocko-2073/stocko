#!/usr/bin/env python3
"""USB console smoke test; never enables drivers or requests an enabled move."""
import os
import select
import sys
import termios
import time

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbmodem2101"
fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
original = termios.tcgetattr(fd)


def exchange(command, expected):
    termios.tcflush(fd, termios.TCIFLUSH)
    os.write(fd, command.encode("ascii"))
    output = b""
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        readable, _, _ = select.select([fd], [], [], 0.1)
        if readable:
            output += os.read(fd, 4096)
        if expected in output.decode("ascii", errors="replace"):
            print(output.decode("ascii", errors="replace").strip())
            return
    raise AssertionError(f"Expected {expected!r}; received {output!r}")


try:
    attrs = termios.tcgetattr(fd)
    attrs[0] = attrs[1] = attrs[3] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[4] = attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    time.sleep(1)
    exchange("STOP\n", "OK disabled")
    exchange("STATUS\n", "A motor=-1")
    exchange("HELP\n", "No homing")
    exchange("JOG M0 1\n", "ERR disabled; ARM first")
    exchange("DEMO\n", "ERR disabled; ARM first")
    exchange("JOG M0 1001\n", "ERR invalid jog")
    exchange("JOG Y -2001\n", "ERR invalid jog")
    exchange("JOG Z 501\n", "ERR invalid jog")
    exchange("JOG X 1 3001\n", "ERR invalid jog")
    exchange("JOG Z 1 2001\n", "ERR invalid jog")
    exchange("!\n", "OK stopped")
    exchange("x" * 100 + "\n", "ERR invalid/overlong line; disabled")
    exchange("STATUS\n", "STATUS armed=0 busy=0 remaining=0 position=UNKNOWN")
    print("USB smoke test passed; drivers disabled.")
finally:
    os.write(fd, b"STOP\n")
    termios.tcsetattr(fd, termios.TCSANOW, original)
    os.close(fd)
