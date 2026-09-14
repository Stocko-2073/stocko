#!/usr/bin/env python3
"""Run one small commissioning jog, then disable all drivers (macOS/POSIX)."""
import argparse
import os
import select
import termios
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("motor", choices=["M0", "M1", "M2", "M3", "X", "Y", "Z", "A"])
parser.add_argument("steps", type=int)
parser.add_argument("--rate", type=int, help="cruise pulses/sec; default 500, capped per motor")
parser.add_argument("--port", default="/dev/cu.usbmodem2101")
parser.add_argument("--return-to-start", action="store_true",
                    help="after DONE, pause 0.5 s while enabled, then send the opposite jog once")
args = parser.parse_args()
step_limit = 6000 if args.motor in ("M2", "A") else (2000 if args.motor in ("M1", "Y") else (500 if args.motor in ("M3", "Z") else 1000))
rate_limit = 3000 if args.motor in ("M0", "M1", "X", "Y") else (2000 if args.motor in ("M3", "Z") else 1000)
if args.rate is None:
    args.rate = min(500, rate_limit)
if not 1 <= abs(args.steps) <= step_limit or not 1 <= args.rate <= rate_limit:
    parser.error(f"{args.motor} requires 1–{step_limit} signed pulses and 1–{rate_limit} pulses/sec")

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
    exchange("STATUS\n", "A motor=")
    exchange("ARM\n", "OK armed")
    started = time.monotonic()
    exchange(f"JOG {args.motor} {args.steps} {args.rate}\n", "DONE",
             timeout=abs(args.steps) / args.rate + 5)
    print(f"Command-to-DONE elapsed: {time.monotonic() - started:.3f} s", flush=True)
    if args.return_to_start:
        time.sleep(0.5)
        started = time.monotonic()
        exchange(f"JOG {args.motor} {-args.steps} {args.rate}\n", "DONE",
                 timeout=abs(args.steps) / args.rate + 5)
        print(f"Return command-to-DONE elapsed: {time.monotonic() - started:.3f} s", flush=True)
    exchange("OFF\n", "OK disabled")
    exchange("STATUS\n", "A motor=")
finally:
    try:
        os.write(fd, b"!\nSTOP\n")
        termios.tcdrain(fd)
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, original)
        os.close(fd)
