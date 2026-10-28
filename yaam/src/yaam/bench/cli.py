"""yaam-bench: drive the SG90 bench from the command line.

  yaam-bench ports                     list serial ports
  yaam-bench selftest                  check every sensor and the pulse timing
  yaam-bench hold 1500                 hold a pulse width between runs
  yaam-bench limp                      stop sending pulses
  yaam-bench monitor                   live readings, ten lines a second
  yaam-bench run steps --unit S01 --load "arm + 2x50g @ 70mm"
  yaam-bench index-cal --unit S01      encoder calibration on the index plate
  yaam-bench show data/S01/...npz      summarise a recording
"""

import argparse
import sys
import time

import numpy as np

from . import experiments as ex
from . import protocol as p
from . import record, units
from .link import Bench, BenchError, Recording

AS_MD, AS_ML, AS_MH = 0x20, 0x10, 0x08


def _bench(args):
    return Bench.open(args.port)


def cmd_ports(args):
    from serial.tools import list_ports

    for port in list_ports.comports():
        tag = "  <- RP2040" if port.vid == 0x2E8A else ""
        print(f"{port.device}  {port.description}{tag}")


def magnet_text(status):
    if not status & AS_MD:
        return "no magnet"
    if status & AS_ML:
        return "too weak: magnet too far or off-axis"
    if status & AS_MH:
        return "too strong: magnet too close"
    return "ok"


def cmd_selftest(args):
    with _bench(args) as bench:
        hello = bench.ping()
        bench.loadcell(True)
        time.sleep(0.6)
        s = bench.selftest()
        bench.loadcell(False)
    adc = s["adc"] / 16.0

    def line(ok, label, text):
        tag = "    " if ok is None else "ok  " if bool(ok) else "FAIL"
        print(f"  {tag}  {label:<16} {text}")

    print(f"firmware: {hello['firmware'].decode(errors='replace').rstrip(chr(0))}, "
          f"{hello['sys_hz'] / 1e6:.0f} MHz")
    print("AS5600")
    line(bool(s["as_present"]), "present", f"CONF 0x{s['as_conf']:04X} (want 0x0300)")
    line(magnet_text(s["as_status"]) == "ok", "magnet", magnet_text(s["as_status"]))
    line(20 <= s["as_agc"] <= 108, "AGC", f"{s['as_agc']} of 0-128, aim for the middle; "
         "lower it by moving the magnet closer")
    line(None, "angle", f"{s['as_raw']} counts = {s['as_raw'] * 360 / 4096:.2f} deg, "
         f"magnitude {s['as_magnitude']}")
    print("INA219")
    line(bool(s["ina_present"]), "present", f"CONFIG 0x{s['ina_config']:04X} (want 0x119F)")
    line(None, "servo supply", f"{units.bus_volts(s['ina_bus']):.3f} V, "
         f"{units.shunt_amps(s['ina_shunt']) * 1e3:.1f} mA")
    print("taps (servo powered and idle: both motor taps read the same, about +1.65 V if the "
          "bridge lets the motor float, about 0 V if it brakes)")
    line(None, "motor A", f"{units.motor_tap_volts(adc[0]):+.3f} V")
    line(None, "motor B", f"{units.motor_tap_volts(adc[1]):+.3f} V")
    line(None, "wiper", f"{units.wiper_volts(adc[2]):.3f} V")
    line(None, "RP2040", f"{units.rp2040_celsius(adc[3]):.1f} C")
    print("timing")
    line(abs(int(s["frame_us"]) - int(hello["frame_us"])) <= 2, "frame",
         f"{s['frame_us']} us measured, {hello['frame_us']} us set")
    pulse = int(s["pulse_us"])
    line(abs(pulse - int(hello["idle_us"])) <= 2, "pulse on D9",
         "stuck high" if pulse == 0xFFFF else f"{pulse} us measured on the pin, {hello['idle_us']} us set"
         + (" (0 = no pulses: limp)" if not hello["idle_us"] else ""))
    line(s["overruns"] == 0, "tick overruns", str(s["overruns"]))
    line(s["drops"] == 0, "USB drops", str(s["drops"]))
    line(None, "HX711", f"{'reading ' + str(s['hx_value']) if s['hx_present'] else 'not seen'}")


def cmd_hold(args):
    with _bench(args) as bench:
        bench.set_idle(args.width)
    print(f"holding {args.width} us" if args.width else "limp: no pulses")


def cmd_monitor(args):
    latest = {}

    def on_message(kind, payload):
        if kind == p.TICK:
            t = p.decode_one(kind, payload)
            latest["angle"] = t["angle"]
            latest["adc"] = t["adc"] / 16.0
            if t["flags"] & p.TICK_INA_OK:
                latest["bus" if t["flags"] & p.TICK_INA_BUS else "shunt"] = t["ina"]
        elif kind == p.STATUS:
            s = p.decode_one(kind, payload)
            latest["status"] = s

    with _bench(args) as bench:
        bench.on_message = on_message
        bench.stream(True)
        print("angle deg   current mA   supply V   motor A V   motor B V   wiper V   AGC")
        end = time.monotonic() + (args.seconds or 1e9)
        try:
            while time.monotonic() < end:
                time.sleep(0.1)
                if "adc" not in latest:
                    continue
                adc = latest["adc"]
                st = latest.get("status")
                print(f"{latest['angle'] * 360 / 4096:9.2f}   "
                      f"{units.shunt_amps(latest.get('shunt', 0)) * 1e3:10.1f}   "
                      f"{units.bus_volts(latest.get('bus', 0)):8.3f}   "
                      f"{units.motor_tap_volts(adc[0]):+9.3f}   {units.motor_tap_volts(adc[1]):+9.3f}   "
                      f"{units.wiper_volts(adc[2]):7.3f}   {st['as_agc'] if st is not None else '-'}")
        except KeyboardInterrupt:
            pass
        finally:
            bench.stream(False)


def pulse_map(args):
    return ex.PulseMap(center_us=args.center_us, us_per_deg=args.us_per_deg, lo_us=args.lo_us, hi_us=args.hi_us)


def summarize(arrays):
    ticks = arrays["ticks"]
    if not len(ticks):
        return "no samples"
    t = record.unwrap_us(ticks["t_us"])
    ok = ticks["flags"] & p.TICK_ANGLE_OK != 0
    deg = np.degrees(units.unwrap_angle(ticks["angle"][ok])) if ok.any() else np.array([0.0])
    shunt = ticks["ina"][(ticks["flags"] & (p.TICK_INA_OK | p.TICK_INA_BUS)) == p.TICK_INA_OK]
    amps = units.shunt_amps(shunt) if len(shunt) else np.array([0.0])
    over = int(np.count_nonzero(ticks["flags"] & p.TICK_OVERRUN))
    drops = int(arrays["status"]["drops"].max()) if len(arrays["status"]) else 0
    return (f"{(t[-1] - t[0]) / 1e6:.1f} s, {len(ticks)} ticks, {len(arrays['frames'])} frames, "
            f"angle {deg.min():.1f}..{deg.max():.1f} deg, current peak {amps.max() * 1e3:.0f} mA, "
            f"overruns {over}, drops {drops}")


def cmd_run(args):
    pm = pulse_map(args)
    exp = ex.EXPERIMENTS[args.experiment](pm, frame_us=args.frame_us)
    w = exp.widths[exp.widths > 0]
    print(f"{exp.name}: {len(exp.widths)} frames of {exp.frame_us} us = {exp.seconds:.1f} s, "
          f"pulses {w.min()}-{w.max()} us")
    if args.dry_run:
        return
    meta = dict(exp.meta, load=args.load, supply_v=args.supply_v, frame_us=exp.frame_us,
                pulse_map=vars(pm), raw_taps=args.raw, loadcell=args.loadcell, note=args.note)
    with _bench(args) as bench:
        hello = bench.ping()
        meta["firmware"] = hello["firmware"].decode(errors="replace").rstrip("\0")
        # The selftest also (re)writes the AS5600's filter setting, which a
        # sensor plugged in after boot wouldn't have.
        s = bench.selftest()
        problems = []
        if not s["as_present"] or s["as_conf"] != 0x0300:
            problems.append("AS5600 missing or not configured")
        elif magnet_text(s["as_status"]) != "ok":
            problems.append(f"AS5600 magnet {magnet_text(s['as_status'])}")
        if not s["ina_present"] or s["ina_config"] != 0x119F:
            problems.append("INA219 missing or not configured")
        if problems and not args.force:
            raise BenchError("; ".join(problems) + ". Run selftest, or --force to record anyway.")
        meta["selftest"] = {k: s[k].tolist() for k in s.dtype.names}
        for i in range(args.repeat):
            if args.reference:
                ref = ex.reference(pm, exp.frame_us)
                rec = bench.run(ref.widths, ref.frame_us, raw=args.raw)
                record.save(rec, args.unit, "reference", dict(meta, of=exp.name), ref.widths, args.data)
            rec = bench.run(exp.widths, exp.frame_us, exp.end_us, raw=args.raw, loadcell=args.loadcell)
            path = record.save(rec, args.unit, exp.name, dict(meta, repeat=i), exp.widths, args.data)
            print(f"[{i + 1}/{args.repeat}] {path}: {summarize(rec.arrays())}")
            if i + 1 < args.repeat and args.rest_s:
                time.sleep(args.rest_s)


def cmd_index_cal(args):
    holes = [args.first_deg + k * args.step_deg for k in range(args.holes)]
    with _bench(args) as bench:
        bench.ping()
        bench.set_idle(0)
        print("The servo is limp. For each hole: turn the arm by hand, push the pin through the arm "
              "into the plate, take your hand off, then press Enter. 's' skips, 'q' finishes early.")
        rec = Recording()
        bench.recording = rec
        bench.stream(True)
        try:
            for k, deg in enumerate(holes):
                answer = input(f"hole {k + 1}/{len(holes)} at {deg:+.0f} deg: ").strip().lower()
                if answer == "q":
                    break
                if answer == "s":
                    continue
                rec.mark(bench.last_tick_us, f"hole {k} {deg}")
                time.sleep(1.0)
                rec.mark(bench.last_tick_us, f"end {k}")
        finally:
            bench.stream(False)
            bench.recording = None
    path = record.save(rec, args.unit, "index-cal", dict(holes_deg=holes, note=args.note), directory=args.data)
    print(f"saved {path}")


def cmd_show(args):
    arrays, meta = record.load(args.path)
    print(f"{meta.get('unit')} {meta.get('experiment')} {meta.get('saved')}: load {meta.get('load')!r}")
    print(summarize(arrays))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="yaam-bench", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="serial port; default: the first RP2040 found")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("ports").set_defaults(func=cmd_ports)
    sub.add_parser("selftest").set_defaults(func=cmd_selftest)
    h = sub.add_parser("hold")
    h.add_argument("width", type=int, help="pulse width in us, 400-2600")
    h.set_defaults(func=cmd_hold)
    sub.add_parser("limp").set_defaults(func=cmd_hold, width=0)
    m = sub.add_parser("monitor")
    m.add_argument("--seconds", type=float)
    m.set_defaults(func=cmd_monitor)

    r = sub.add_parser("run")
    r.add_argument("experiment", choices=sorted(ex.EXPERIMENTS))
    r.add_argument("--unit", required=True, help="servo id, e.g. S01")
    r.add_argument("--load", required=True, help='what hangs on the arm, e.g. "arm + 2x50g @ 70mm"')
    r.add_argument("--supply-v", type=float, default=5.0, help="servo supply setting, for the record")
    r.add_argument("--frame-us", type=int, default=20000)
    r.add_argument("--repeat", type=int, default=2)
    r.add_argument("--rest-s", type=float, default=30.0, help="pause between repeats")
    r.add_argument("--reference", action="store_true", help="run the drift check before each repeat")
    r.add_argument("--raw", action="store_true", help="also stream raw 20 kS/s taps")
    r.add_argument("--loadcell", action="store_true")
    r.add_argument("--center-us", type=float, default=1500.0)
    r.add_argument("--us-per-deg", type=float, default=2000 / 180)
    r.add_argument("--lo-us", type=int, default=600)
    r.add_argument("--hi-us", type=int, default=2400)
    r.add_argument("--note", default="")
    r.add_argument("--data", default=record.DATA)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--force", action="store_true", help="record even if the selftest finds a problem")
    r.set_defaults(func=cmd_run)

    i = sub.add_parser("index-cal")
    i.add_argument("--unit", required=True)
    i.add_argument("--holes", type=int, default=13)
    i.add_argument("--first-deg", type=float, default=-90.0)
    i.add_argument("--step-deg", type=float, default=15.0)
    i.add_argument("--note", default="")
    i.add_argument("--data", default=record.DATA)
    i.set_defaults(func=cmd_index_cal)

    s = sub.add_parser("show")
    s.add_argument("path")
    s.set_defaults(func=cmd_show)

    args = ap.parse_args(argv)
    try:
        args.func(args)
    except BenchError as exc:
        sys.exit(f"bench: {exc}")


if __name__ == "__main__":
    main()
