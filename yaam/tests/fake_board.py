"""A stand-in for the bench firmware at the message level, for testing the host
side without hardware. Runs play instantly: all their frames and ticks are
queued at once."""

import struct
import threading
import time

import numpy as np

from yaam.bench import protocol as p


class FakeBoard:
    capacity = 32768

    def __init__(self):
        self.out = bytearray()
        self.lock = threading.Lock()
        self.decoder = p.Decoder()
        self.schedule = np.zeros(self.capacity, np.uint16)
        self.loaded = 0
        self.frame_us = 20000
        self.idle_us = 0
        self.streaming = False
        self.raw = False
        self.t_us = 1000
        self.frame = 0
        self.adc_idx = 0
        self.angle = 2048.0
        self.commands = []

    # --- transport ---

    @property
    def in_waiting(self):
        with self.lock:
            return len(self.out)

    def read(self, n):
        with self.lock:
            data = bytes(self.out[:n])
            del self.out[:n]
        if not data:
            time.sleep(0.001)
        return data

    def write(self, data):
        for kind, payload in self.decoder.feed(data):
            self.commands.append(kind)
            self.handle(kind, payload)
        return len(data)

    def close(self):
        pass

    # --- firmware behaviour ---

    def send(self, kind, payload):
        with self.lock:
            self.out += p.encode(kind, payload)

    def reply(self, cmd, code=p.OK):
        self.send(p.REPLY, bytes([cmd, code]))

    def handle(self, kind, payload):
        if kind == p.CMD_PING:
            hello = np.zeros(1, p.HELLO_DTYPE)
            hello["version"] = p.VERSION
            hello["firmware"] = b"fake"
            hello["sys_hz"] = 125_000_000
            hello["tick_hz"] = 2000
            hello["adc_hz"] = 80000
            hello["sched_capacity"] = self.capacity
            hello["frame_us"] = self.frame_us
            self.send(p.HELLO, hello.tobytes())
            self.reply(kind)
        elif kind == p.CMD_SET_FRAME:
            (us,) = struct.unpack("<H", payload)
            if us < 2700:
                return self.reply(kind, p.ERR_RANGE)
            self.frame_us = us
            self.reply(kind)
        elif kind == p.CMD_SCHED_CLEAR:
            self.loaded = 0
            self.reply(kind)
        elif kind == p.CMD_SCHED_DATA:
            offset, n = struct.unpack_from("<IH", payload)
            w = np.frombuffer(payload, "<u2", count=n, offset=6)
            if offset > self.loaded or offset + n > self.capacity:
                return self.reply(kind, p.ERR_RANGE)
            self.schedule[offset:offset + n] = w
            self.loaded = max(self.loaded, offset + n)
            self.reply(kind)
        elif kind == p.CMD_SET_IDLE:
            (self.idle_us,) = struct.unpack("<H", payload)
            self.reply(kind)
        elif kind == p.CMD_STREAM:
            self.streaming = bool(payload[0])
            self.reply(kind)
        elif kind == p.CMD_RAW_TAPS:
            self.raw = bool(payload[0])
            self.reply(kind)
        elif kind in (p.CMD_LOADCELL, p.CMD_STOP):
            self.reply(kind)
        elif kind == p.CMD_SELFTEST:
            self.reply(kind)
            s = np.zeros(1, p.SELFTEST_DTYPE)
            s["as_present"], s["as_status"], s["as_agc"], s["as_conf"] = 1, 0x20, 64, 0x0300
            s["ina_present"], s["ina_config"] = 1, 0x119F
            s["frame_us"] = self.frame_us
            self.send(p.SELFTEST, s.tobytes())
        elif kind == p.CMD_RUN:
            frames, end_us = struct.unpack("<IH", payload)
            if frames == 0 or frames > self.loaded:
                return self.reply(kind, p.ERR_RANGE)
            self.reply(kind)
            for i in range(frames):
                self.play_frame(int(self.schedule[i]), i)
            self.idle_us = end_us
            self.play_frame(end_us, -1)
            self.send(p.RUN_DONE, struct.pack("<IIB", self.t_us, frames, 0))
        else:
            self.reply(kind, p.ERR_UNKNOWN)

    def play_frame(self, width, idx):
        if self.streaming:
            self.send(p.FRAME, struct.pack("<IIHi", self.frame, self.t_us, width, idx))
        target = 2048 + (width - 1500) * 4096 / 360 / (2000 / 180) if width else self.angle
        for k in range(self.frame_us // 500):
            self.angle += 0.2 * (target - self.angle)
            if self.streaming:
                tick = np.zeros(1, p.TICK_DTYPE)
                tick["t_us"], tick["adc_idx"] = self.t_us, self.adc_idx
                tick["angle"] = int(round(self.angle)) & 0x0FFF
                tick["ina"] = 1234 if k % 2 == 0 else (1250 << 3)   # 12.34 mA; 5.000 V
                tick["flags"] = p.TICK_ANGLE_OK | p.TICK_INA_OK | (p.TICK_INA_BUS if k % 2 else 0)
                tick["adc"] = 1600
                tick["n"] = 10
                self.send(p.TICK, tick.tobytes())
                if self.raw:
                    samples = np.full(40, 100, "<u2")
                    self.send(p.TAPS, struct.pack("<IH", self.adc_idx, 40) + samples.tobytes())
            self.t_us = (self.t_us + 500) & 0xFFFFFFFF
            self.adc_idx += 40
        self.frame += 1
