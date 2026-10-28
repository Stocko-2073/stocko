"""Wire format shared with firmware/sg90_bench/Protocol.h.

Every message is ``0xA5, type, len (u16 LE), payload, crc (u16 LE)`` with
CRC-16/CCITT-FALSE over type, len and payload. Payload layouts are packed
little-endian structs, decoded here with numpy dtypes of the same sizes (the
firmware static_asserts the sizes).
"""

import binascii
import struct

import numpy as np

SYNC = 0xA5
VERSION = 1
MAX_PAYLOAD = 1024

HELLO, TICK, FRAME, TAPS, STATUS, REPLY, LOAD, RUN_DONE, SELFTEST = range(0x01, 0x0A)
TEXT = 0x7F

CMD_PING = 0x81
CMD_SET_FRAME = 0x82
CMD_SCHED_CLEAR = 0x83
CMD_SCHED_DATA = 0x84
CMD_RUN = 0x85
CMD_STOP = 0x86
CMD_SELFTEST = 0x87
CMD_SET_IDLE = 0x88
CMD_LOADCELL = 0x89
CMD_RAW_TAPS = 0x8A
CMD_STREAM = 0x8B

OK, ERR_BUSY, ERR_RANGE, ERR_LENGTH, ERR_UNKNOWN, ERR_EMPTY = range(6)
ERRORS = {
    ERR_BUSY: "busy: not allowed while a run is going",
    ERR_RANGE: "argument out of range",
    ERR_LENGTH: "payload has the wrong length",
    ERR_UNKNOWN: "unknown command",
    ERR_EMPTY: "no schedule loaded",
}

TICK_INA_BUS = 0x01
TICK_INA_OK = 0x02
TICK_ANGLE_OK = 0x04
TICK_OVERRUN = 0x08

# Round-robin order of the ADC inputs: sample i comes from ADC_INPUTS[i % 4].
ADC_INPUTS = (0, 1, 2, 4)
SCHED_CHUNK = (MAX_PAYLOAD - 6) // 2

HELLO_DTYPE = np.dtype([
    ("version", "u1"), ("firmware", "S32"), ("sys_hz", "<u4"), ("tick_hz", "<u2"),
    ("adc_hz", "<u4"), ("sched_capacity", "<u4"), ("frame_us", "<u2"), ("idle_us", "<u2"),
])
TICK_DTYPE = np.dtype([
    ("t_us", "<u4"), ("adc_idx", "<u4"), ("angle", "<u2"), ("ina", "<i2"),
    ("adc", "<u2", (4,)), ("flags", "u1"), ("n", "u1"),
])
FRAME_DTYPE = np.dtype([("frame", "<u4"), ("t_us", "<u4"), ("width_us", "<u2"), ("sched_idx", "<i4")])
TAPS_HEAD_DTYPE = np.dtype([("first_idx", "<u4"), ("n", "<u2")])
STATUS_DTYPE = np.dtype([
    ("t_us", "<u4"), ("as_status", "u1"), ("as_agc", "u1"), ("as_magnitude", "<u2"),
    ("overruns", "<u4"), ("drops", "<u4"), ("angle_errors", "<u2"), ("ina_errors", "<u2"),
])
LOAD_DTYPE = np.dtype([("t_us", "<u4"), ("value", "<i4")])
RUN_DONE_DTYPE = np.dtype([("t_us", "<u4"), ("frames", "<u4"), ("stopped", "u1")])
SELFTEST_DTYPE = np.dtype([
    ("as_present", "u1"), ("as_status", "u1"), ("as_agc", "u1"), ("as_magnitude", "<u2"),
    ("as_conf", "<u2"), ("as_raw", "<u2"), ("ina_present", "u1"), ("ina_config", "<u2"),
    ("ina_shunt", "<i2"), ("ina_bus", "<u2"), ("adc", "<u2", (4,)), ("frame_us", "<u4"),
    ("sys_hz", "<u4"), ("overruns", "<u4"), ("drops", "<u4"), ("hx_present", "u1"),
    ("hx_value", "<i4"), ("pulse_us", "<u2"),
])
REPLY_DTYPE = np.dtype([("cmd", "u1"), ("code", "u1")])

SIZES = {HELLO: 51, TICK: 22, FRAME: 14, STATUS: 20, LOAD: 8, RUN_DONE: 9, SELFTEST: 47, REPLY: 2}
DTYPES = {
    HELLO: HELLO_DTYPE, TICK: TICK_DTYPE, FRAME: FRAME_DTYPE, STATUS: STATUS_DTYPE,
    LOAD: LOAD_DTYPE, RUN_DONE: RUN_DONE_DTYPE, SELFTEST: SELFTEST_DTYPE, REPLY: REPLY_DTYPE,
}
assert all(DTYPES[k].itemsize == n for k, n in SIZES.items())


def crc(data):
    return binascii.crc_hqx(data, 0xFFFF)


def encode(kind, payload=b""):
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload of {len(payload)} bytes exceeds {MAX_PAYLOAD}")
    head = struct.pack("<BH", kind, len(payload))
    return bytes([SYNC]) + head + payload + struct.pack("<H", crc(head + payload))


def decode_one(kind, payload):
    """A single fixed-size message as a numpy record."""
    return np.frombuffer(payload, DTYPES[kind], count=1)[0]


class Decoder:
    """Splits a byte stream into messages. On a bad length or CRC it drops one
    byte and looks for the next sync byte, so it recovers from line noise or
    from joining a stream part way through a message."""

    def __init__(self):
        self.buffer = bytearray()
        self.bad = 0

    def feed(self, data):
        self.buffer += data
        out = []
        buf = self.buffer
        i = 0
        while True:
            j = buf.find(SYNC, i)
            if j < 0:
                i = len(buf)
                break
            if len(buf) - j < 6:
                i = j
                break
            kind, n = struct.unpack_from("<BH", buf, j + 1)
            if n > MAX_PAYLOAD:
                self.bad += 1
                i = j + 1
                continue
            if len(buf) - j < 6 + n:
                i = j
                break
            (c,) = struct.unpack_from("<H", buf, j + 4 + n)
            if crc(bytes(buf[j + 1:j + 4 + n])) != c:
                self.bad += 1
                i = j + 1
                continue
            out.append((kind, bytes(buf[j + 4:j + 4 + n])))
            i = j + 6 + n
        del buf[:i]
        return out
