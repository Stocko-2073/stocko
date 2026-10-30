"""phone_girl's link: byte layouts shared by the MCU firmware, the phone app and the simulator.

The frames are the same over USB-C NCM, as UDP datagrams, and over BLE, as GATT
values. Behaviour is in robots/phone_girl/protocol/PROTOCOL.md; phone_girl_link.h
is the C side and is checked against vectors() byte for byte. Integers are
little-endian. Positions are servo ticks minus 2048, so zero is the home pose
once calibrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import struct

VERSION = 1
SERVOS = 17
HOME_TICKS = 2048
_BASE = "-77c3-4dbd-b507-83058991dbc6"
SERVICE = "a7470000" + _BASE
STATE, COMMAND, CONTROL, INFO, CAPTURE = (f"a747000{i}{_BASE}" for i in range(1, 6))
# USB-C NCM: one UDP datagram per frame, on the port matching each characteristic.
STATE_PORT, COMMAND_PORT, CONTROL_PORT, INFO_PORT, CAPTURE_PORT = range(47001, 47006)

# State flags.
TORQUE_ON, COMMAND_FRESH, HOLDING, DEADMAN, SERVO_ERROR, LOW_VOLTAGE = (1 << i for i in range(6))
# Command flags.
HOLD = 1  # keep the current goals; the app is pausing, not lost
# Control opcodes; a reply sets the top bit.
TORQUE, GAIN, LIMITS, CALIBRATE_HOME, SAFETY, REBOOT, CAPTURE_START, SOFT_LIMITS = range(1, 9)
OK, BAD_REQUEST, REFUSED, BUS_ERROR, BUSY = range(5)
UNKNOWN_LATENCY = 0xFFFF

_STATE_HEAD = struct.Struct("<BBHIHHHBbBB")
_SERVO = struct.Struct("<hhhh")
_COMMAND_HEAD = struct.Struct("<BBHH")
_CAPTURE_HEAD = struct.Struct("<BBBHIH")
_SAMPLE = struct.Struct("<hhhhh")


@dataclass
class ServoState:
    position: int  # ticks minus 2048
    velocity: int  # Present Velocity, 0.229 rpm
    current: int  # Present Current, mA, measured at the servo's power input
    pwm: int  # Present PWM, 0.113 % (885 is full duty)


@dataclass
class State:
    """Sent every tick, after the MCU reads every servo."""

    seq: int
    read_us: int  # MCU clock when the bus read began
    flags: int = 0
    command_seq: int = 0  # the last command applied
    command_latency: int = UNKNOWN_LATENCY  # 0.1 ms from the state it answered being read to it being applied
    bus_mv: int = 0
    slot: int = 0  # whose slow fields follow; round robin
    temperature_c: int = 0
    hardware_error: int = 0
    bus_errors: int = 0
    servos: list[ServoState] = field(default_factory=list)

    SIZE = _STATE_HEAD.size + SERVOS * _SERVO.size

    def pack(self) -> bytes:
        if len(self.servos) != SERVOS:
            raise ValueError(f"State needs {SERVOS} servos")
        head = _STATE_HEAD.pack(VERSION, self.flags, self.seq, self.read_us, self.command_seq,
                                self.command_latency, self.bus_mv, self.slot, self.temperature_c,
                                self.hardware_error, self.bus_errors)
        return head + b"".join(_SERVO.pack(s.position, s.velocity, s.current, s.pwm) for s in self.servos)

    @classmethod
    def unpack(cls, data: bytes) -> State:
        if len(data) != cls.SIZE or data[0] != VERSION:
            raise ValueError(f"Not a v{VERSION} state: {len(data)} bytes")
        (_, flags, seq, read_us, command_seq, latency, bus_mv, slot, temperature, error,
         bus_errors) = _STATE_HEAD.unpack_from(data)
        servos = [ServoState(*_SERVO.unpack_from(data, _STATE_HEAD.size + i * _SERVO.size)) for i in range(SERVOS)]
        return cls(seq, read_us, flags, command_seq, latency, bus_mv, slot, temperature, error, bus_errors, servos)


@dataclass
class Command:
    """Goal positions for every servo, written without response once per tick."""

    seq: int
    state_seq: int  # the state the policy acted on
    goals: list[int] = field(default_factory=list)  # ticks minus 2048
    flags: int = 0

    SIZE = _COMMAND_HEAD.size + SERVOS * 2

    def pack(self) -> bytes:
        if len(self.goals) != SERVOS:
            raise ValueError(f"Command needs {SERVOS} goals")
        return _COMMAND_HEAD.pack(VERSION, self.flags, self.seq, self.state_seq) + struct.pack(
            f"<{SERVOS}h", *self.goals)

    @classmethod
    def unpack(cls, data: bytes) -> Command:
        if len(data) != cls.SIZE or data[0] != VERSION:
            raise ValueError(f"Not a v{VERSION} command: {len(data)} bytes")
        _, flags, seq, state_seq = _COMMAND_HEAD.unpack_from(data)
        return cls(seq, state_seq, list(struct.unpack_from(f"<{SERVOS}h", data, _COMMAND_HEAD.size)), flags)


def control(opcode: int, request: int, payload: bytes = b"") -> bytes:
    """A control request: opcode, request id, then the opcode's payload."""
    return struct.pack("<BB", opcode, request) + payload


def reply(opcode: int, request: int, status: int, payload: bytes = b"") -> bytes:
    return struct.pack("<BBB", opcode | 0x80, request, status) + payload


@dataclass
class Capture:
    """High-rate samples of one servo for system identification, sent in bursts."""

    slot: int
    seq: int
    start_us: int
    period_us: int
    samples: list[tuple[int, int, int, int, int]]  # goal, position, velocity, current, pwm

    def pack(self) -> bytes:
        return _CAPTURE_HEAD.pack(VERSION, self.slot, len(self.samples), self.seq, self.start_us,
                                  self.period_us) + b"".join(_SAMPLE.pack(*s) for s in self.samples)

    @classmethod
    def unpack(cls, data: bytes) -> Capture:
        version, slot, count, seq, start, period = _CAPTURE_HEAD.unpack_from(data)
        if version != VERSION or len(data) != _CAPTURE_HEAD.size + count * _SAMPLE.size:
            raise ValueError("Not a capture frame")
        return cls(slot, seq, start, period,
                   [_SAMPLE.unpack_from(data, _CAPTURE_HEAD.size + i * _SAMPLE.size) for i in range(count)])


TICK_RAD = 2 * math.pi / 4096
VELOCITY_RAD_S = 0.229 * 2 * math.pi / 60
PWM_FULL = 885


def goals(targets_rad, home_rad) -> list[int]:
    """What the app sends for joint targets: ticks from home, rounded."""
    return [max(-32768, min(32767, round((t - h) / TICK_RAD))) for t, h in zip(targets_rad, home_rad)]


def servo_si(state: State) -> dict[str, list[float]]:
    """What the app reads from a state: SI units, positions relative to home."""
    return dict(position=[s.position * TICK_RAD for s in state.servos],
                velocity=[s.velocity * VELOCITY_RAD_S for s in state.servos],
                current=[s.current * 1e-3 for s in state.servos],
                pwm=[s.pwm / PWM_FULL for s in state.servos], voltage=state.bus_mv * 1e-3)


def vectors() -> dict:
    """Golden frames the C header must reproduce byte for byte."""
    servos = [ServoState(position=-1000 + 117 * i, velocity=(-1) ** i * (3 * i), current=-500 + 61 * i,
                         pwm=-885 + 104 * i) for i in range(SERVOS)]
    state = State(seq=0xBEEF, read_us=0x12345678, flags=TORQUE_ON | COMMAND_FRESH, command_seq=0xBEEE,
                  command_latency=163, bus_mv=3912, slot=5, temperature_c=-3, hardware_error=0x20,
                  bus_errors=1, servos=servos)
    command = Command(seq=0xBEEE, state_seq=0xBEED, goals=[-2047 + 255 * i for i in range(SERVOS)], flags=HOLD)
    capture = Capture(slot=3, seq=7, start_us=0xCAFEF00D, period_us=1000,
                      samples=[(10 * i, 10 * i - 3, -i, 20 * i, -50 * i) for i in range(4)])
    return dict(state=state.pack().hex(), command=command.pack().hex(), capture=capture.pack().hex(),
                control=control(SAFETY, 9, struct.pack("<HBH", 300, 1, 2000)).hex(),
                reply=reply(CALIBRATE_HOME, 4, OK, struct.pack(f"<{SERVOS}i", *range(-8, 9))).hex(),
                ports=",".join(map(str, (STATE_PORT, COMMAND_PORT, CONTROL_PORT, INFO_PORT, CAPTURE_PORT))),
                sizes=dict(state=State.SIZE, command=Command.SIZE))


if __name__ == "__main__":
    print(json.dumps(vectors(), indent=1))
