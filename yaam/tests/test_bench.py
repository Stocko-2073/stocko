import struct

import numpy as np
import pytest

from fake_board import FakeBoard
from yaam.bench import experiments as ex
from yaam.bench import protocol as p
from yaam.bench import record, units
from yaam.bench.link import Bench, BenchError


def test_crc_is_ccitt_false():
    assert p.crc(b"123456789") == 0x29B1


def test_round_trip_resyncs_after_garbage_and_bad_crc():
    good = p.encode(p.TICK, bytes(22))
    corrupt = bytearray(p.encode(p.FRAME, bytes(14)))
    corrupt[5] ^= 0xFF
    stream = b"\x00\xA5\x07junk" + bytes(corrupt) + good + p.encode(p.TEXT, b"hi")
    d = p.Decoder()
    got = []
    for i in range(0, len(stream), 7):   # arrives in awkward pieces
        got += d.feed(stream[i:i + 7])
    assert got == [(p.TICK, bytes(22)), (p.TEXT, b"hi")]
    assert d.bad >= 1


def test_struct_sizes_match_firmware():
    assert {k: v.itemsize for k, v in p.DTYPES.items()} == p.SIZES
    assert p.TAPS_HEAD_DTYPE.itemsize == 6


@pytest.fixture
def bench():
    b = Bench(FakeBoard())
    yield b
    b.close()


def test_ping_and_selftest(bench):
    hello = bench.ping()
    assert hello["tick_hz"] == 2000
    s = bench.selftest()
    assert s["as_conf"] == 0x0300 and s["ina_config"] == 0x119F


def test_errors_are_raised(bench):
    with pytest.raises(BenchError, match="out of range"):
        bench.set_frame(1000)


def test_run_records_every_frame(bench, tmp_path):
    exp = ex.steps(ex.PulseMap(), amplitudes_deg=(5, 20), starts_deg=(0,), dwell_s=0.2)
    rec = bench.run(exp.widths, exp.frame_us, raw=True, settle_s=0, pre_s=0, post_s=0.05)
    a = rec.arrays()
    scheduled = a["frames"][a["frames"]["sched_idx"] >= 0]
    assert np.array_equal(scheduled["width_us"], exp.widths)
    assert len(a["ticks"]) >= len(exp.widths) * 40
    assert a["run_done"]["frames"][0] == len(exp.widths)
    assert a["taps_n"].sum() == len(a["taps"])

    path = record.save(rec, "T01", exp.name, dict(exp.meta, load="none"), exp.widths, tmp_path)
    arrays, meta = record.load(path)
    assert meta["unit"] == "T01" and meta["load"] == "none"
    assert np.array_equal(arrays["schedule"], exp.widths)
    assert path.with_suffix(".json").exists()


def test_upload_spans_several_messages(bench):
    widths = np.full(2000, 1500, np.uint16)
    bench.upload(widths)
    board = bench.transport
    assert board.loaded == 2000
    assert board.commands.count(p.CMD_SCHED_DATA) == -(-2000 // p.SCHED_CHUNK)


@pytest.mark.parametrize("name", sorted(ex.EXPERIMENTS))
def test_experiments_stay_in_range_and_fit(name):
    pm = ex.PulseMap()
    exp = ex.EXPERIMENTS[name](pm)
    w = exp.widths
    assert w.dtype == np.uint16 and 0 < len(w) <= 32768
    pulses = w[w > 0]
    assert pulses.min() >= pm.lo_us and pulses.max() <= pm.hi_us
    if name == "lift-and-drop":
        assert (w == 0).any()
    else:
        assert (w > 0).all()


def test_pulse_map_refuses_out_of_range():
    with pytest.raises(ValueError):
        ex.PulseMap().widths([0, 120])


def test_unit_conversions():
    assert units.bus_volts(5000 << 3) == pytest.approx(20.0)
    assert units.shunt_amps(1000) == pytest.approx(0.1)
    # The motor tap's offset divider: 0 V at the tap reads 1.1 V at the pin.
    assert units.motor_tap_volts(1.1 / 3.3 * 4096) == pytest.approx(0.0, abs=1e-9)
    assert record.unwrap_us([4294967000, 100, 600]).tolist() == [4294967000, 4294967396, 4294967896]


def test_run_payload_layout():
    # CMD_RUN is u32 frames then u16 end width, as ServoPwm::run reads it.
    assert struct.pack("<IH", 3, 1500) == bytes([3, 0, 0, 0, 0xDC, 0x05])
