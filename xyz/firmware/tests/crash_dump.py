#!/usr/bin/env python3
"""Read the crash log stored by the XYZ controller over USB (macOS/POSIX).

  crash_dump.py            summary of the last panic, symbolised with addr2line
  crash_dump.py dump       save the raw core dump partition image to build/coredump.bin
  crash_dump.py clear      erase the stored core dump

The ESP32-C6 Arduino libraries write an ELF core dump to the 64 KB coredump
partition on every panic. The summary needs only the toolchain's addr2line;
the full dump can be opened with `pip install esp-coredump`.
"""
import argparse
import base64
import glob
import os
import re
import select
import subprocess
import sys
import termios
import time

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("mode", nargs="?", choices=["info", "dump", "clear"], default="info")
parser.add_argument("--port", default="/dev/cu.usbmodem2101")
parser.add_argument("--elf", default=os.path.join(os.path.dirname(__file__), "..", "build", "xyza.ino.elf"))
parser.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "build", "coredump.bin"))
args = parser.parse_args()

TOOLS = os.path.expanduser("~/Library/Arduino15/packages/esp32/tools")
# ESP32-C6 code lives in flash-mapped IROM and in IRAM.
CODE_RANGES = ((0x42000000, 0x42800000), (0x40800000, 0x40880000))

fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
original = termios.tcgetattr(fd)


def exchange(command, terminator, timeout=20):
    termios.tcflush(fd, termios.TCIFLUSH)
    os.write(fd, command.encode("ascii"))
    output = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        readable, _, _ = select.select([fd], [], [], 0.1)
        if readable:
            output += os.read(fd, 65536)
        text = output.decode("ascii", errors="replace")
        if terminator in text or "ERR" in text or "none stored" in text:
            return text
    raise TimeoutError(f"Expected {terminator!r}; received {output[-200:]!r}")


def symbolise(addresses):
    tool = sorted(glob.glob(f"{TOOLS}/esp-rv32/*/bin/riscv32-esp-elf-addr2line"))
    if not tool or not os.path.exists(args.elf):
        print(f"(addr2line or {args.elf} not found; addresses left raw)")
        return
    result = subprocess.run([tool[-1], "-pfiaC", "-e", args.elf] + [f"0x{a:08x}" for a in addresses],
                            capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if "??" not in line:
            print("  " + line)


try:
    settings = termios.tcgetattr(fd)
    settings[3] &= ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSANOW, settings)
    if args.mode == "clear":
        print(exchange("CRASH CLEAR\n", "OK").strip())
    elif args.mode == "dump":
        text = exchange("CRASH DUMP\n", "COREDUMP END", timeout=120)
        if "COREDUMP BEGIN" not in text:
            print(text.strip()); sys.exit(1)
        body = text.split("COREDUMP BEGIN", 1)[1].split("\n", 1)[1].split("COREDUMP END")[0]
        data = base64.b64decode("".join(body.split()))
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "wb") as f:
            f.write(data)
        gdb = sorted(glob.glob(f"{TOOLS}/riscv32-esp-elf-gdb/*/bin/riscv32-esp-elf-gdb"))
        print(f"Wrote {len(data)} bytes to {args.out}")
        print("Decode with:  pip install esp-coredump && esp-coredump"
              + (f" --gdb {gdb[-1]}" if gdb else "")
              + f" info_corefile --core {args.out} --core-format raw {args.elf}")
    else:
        text = exchange("CRASH INFO\n", "CRASH END")
        print(text.strip())
        if "CRASH END" not in text:
            sys.exit(0 if "none stored" in text else 1)
        head = re.search(r"pc=0x([0-9a-f]+) ra=0x([0-9a-f]+)", text)
        stack = re.search(r"CRASH stack=([0-9a-f ]*)", text)
        words = [int(h, 16) for h in ([head.group(1), head.group(2)] if head else []) + (stack.group(1).split() if stack else [])]
        code = []
        for w in words:
            if any(lo <= w < hi for lo, hi in CODE_RANGES) and w not in code:
                code.append(w)
        if code:
            print("Code addresses (pc, ra, then stack words that point into code; newest first):")
            symbolise(code)
        print("The ELF must be the build that crashed: compare elf_sha256 with `shasum -a 256 build/xyza.ino.elf`.")
finally:
    termios.tcsetattr(fd, termios.TCSANOW, original)
    os.close(fd)
