#!/usr/bin/env python3
"""Serial harness for the pet servo console.

Sends each command in order, printing everything the board says. Unless
--no-stop is given, always sends 'x' (disable motors) before exiting so a test
can't leave a motor running.

Usage:
  ./talk.py [-w SECS] "cmd" ["cmd" ...]     send commands, watch SECS after each
  ./talk.py -w 0.5 "s"                      quick status check
  ./talk.py "o 1 80 200"                    open-loop pulse test
  ./talk.py -w 6 "v 2" "g 1 2" "s"          closed-loop move, watch 6s per cmd

A command of the form 'sleep N' is handled locally (waits N seconds while
still printing serial output) rather than sent to the board.
"""
import argparse
import sys
import time

import serial

DEFAULT_PORT = "/dev/cu.usbmodem2101"


def drain(ser, seconds):
    """Print whatever arrives on the port for `seconds`."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        line = ser.readline()
        if line:
            print(line.decode(errors="replace").rstrip())
            sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-p", "--port", default=DEFAULT_PORT)
    ap.add_argument("-w", "--watch", type=float, default=2.0,
                    help="seconds of output to watch after each command (default 2)")
    ap.add_argument("--no-stop", action="store_true",
                    help="don't send 'x' (disable motors) on exit")
    ap.add_argument("cmds", nargs="+")
    args = ap.parse_args()

    try:
        ser = serial.Serial(args.port, 115200, timeout=0.05)
    except serial.SerialException as e:
        print(f"[could not open {args.port}: {e}]")
        return 1

    try:
        drain(ser, 0.5)  # boot banner / leftovers
        for cmd in args.cmds:
            if cmd.startswith("sleep "):
                drain(ser, float(cmd.split()[1]))
                continue
            print(f">>> {cmd}")
            ser.write((cmd + "\n").encode())
            drain(ser, args.watch)
    except serial.SerialException:
        print("[port closed mid-session (board reset?)]")
        return 0
    finally:
        if not args.no_stop:
            try:
                ser.write(b"x\n")
                drain(ser, 0.3)
            except serial.SerialException:
                pass
        ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
