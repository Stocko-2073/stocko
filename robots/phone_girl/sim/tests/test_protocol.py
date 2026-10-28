"""The BLE frames: round trips, sizes, the C header, and agreement with the simulator."""

import shutil
import subprocess

import numpy as np
import pytest
import torch

from phone_girl import ROBOT_DIR, protocol
from phone_girl.xl330 import CURRENT_LSB, PWM_LIMIT, TICK, VELOCITY_LSB


def test_frames_round_trip():
    vectors = protocol.vectors()
    state = protocol.State.unpack(bytes.fromhex(vectors["state"]))
    assert state.pack().hex() == vectors["state"] and state.servos[5].velocity == -15
    command = protocol.Command.unpack(bytes.fromhex(vectors["command"]))
    assert command.pack().hex() == vectors["command"] and command.flags == protocol.HOLD
    capture = protocol.Capture.unpack(bytes.fromhex(vectors["capture"]))
    assert capture.pack().hex() == vectors["capture"] and len(capture.samples) == 4
    with pytest.raises(ValueError):
        protocol.Command.unpack(bytes.fromhex(vectors["command"])[:-1])


def test_frames_fit_one_notification():
    # iOS negotiates an ATT MTU of at least 185; a value is MTU - 3 bytes.
    assert protocol.State.SIZE <= 182 and protocol.Command.SIZE <= 182
    assert protocol.State.SIZE == 154 and protocol.Command.SIZE == 40


@pytest.mark.skipif(shutil.which("cc") is None, reason="needs a C compiler")
def test_c_header_matches_python(tmp_path):
    source = ROBOT_DIR / "protocol" / "check_vectors.c"
    binary = tmp_path / "check_vectors"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Werror", "-o", str(binary), str(source)], check=True)
    printed = dict(line.split() for line in subprocess.run([str(binary)], capture_output=True, text=True,
                                                            check=True).stdout.splitlines())
    expected = protocol.vectors()
    for name in ("state", "command", "capture", "control", "reply"):
        assert printed[name] == expected[name], name


def test_units_match_the_servo_model():
    assert protocol.TICK_RAD == TICK and protocol.VELOCITY_RAD_S == pytest.approx(VELOCITY_LSB)
    assert protocol.PWM_FULL == PWM_LIMIT and CURRENT_LSB == 1e-3


def test_goal_and_state_encoding_match_the_simulator():
    """The sim quantizes exactly as the app encodes goals and decodes servo registers."""
    rng = np.random.default_rng(3)
    home = rng.uniform(-2, 2, protocol.SERVOS)
    targets = home + rng.uniform(-1, 1, protocol.SERVOS)
    ticks = protocol.goals(targets, home)
    sim_ticks = torch.round(torch.tensor(targets - home) / TICK).long().tolist()
    assert ticks == sim_ticks
    servos = [protocol.ServoState(t, -t // 10, t // 3, max(-885, min(885, t))) for t in ticks]
    state = protocol.State(seq=1, read_us=0, bus_mv=3870, servos=servos)
    si = protocol.servo_si(protocol.State.unpack(state.pack()))
    np.testing.assert_allclose(si["position"], np.array(ticks) * TICK)
    assert si["voltage"] == pytest.approx(3.87)
