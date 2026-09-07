import Foundation
import UBotCore

// ubotctl -- the bench harness for the U-BOT BLE contract.
//
// This exists so the GATT layer can be verified against real hardware from a
// Mac, with nothing but the Command Line Tools installed. It uses the same
// BLERobotLink and DriveTicker the iPhone app does, so when the phone
// misbehaves later there is a known-good reference on the desk.
//
//   ubotctl selftest              codec vectors, no radio, no robot
//   ubotctl scan                  list matching peripherals
//   ubotctl status                stream the 5 Hz status table
//   ubotctl enable | disable | estop | clear | stop
//   ubotctl drive <v> <w> <secs>  run the real ticker, then release

// stdout is block-buffered when it is not a terminal, so piping this to a file
// or a log would swallow the status table for seconds at a time. The bracketed
// progress lines go to stderr, which is unbuffered, which is exactly why they
// showed up and the table did not. Line-buffer stdout so both behave the same
// way whether or not there is a TTY on the other end.
setvbuf(stdout, nil, _IOLBF, 0)

let args = Array(CommandLine.arguments.dropFirst())
let command = args.first ?? "status"

func usage() -> Never {
    FileHandle.standardError.write(Data("""
    usage: ubotctl <command>

      selftest              decode/encode vectors, no radio
      scan                  find robots and print what they advertise
      status                stream status at 5 Hz until interrupted
      enable                energise the motor drivers (also clears faults)
      disable               drop the drivers
      stop                  ramp to a stop
      estop                 cut EN immediately
      clear                 clear latched faults
      drive <v> <w> <secs>  drive at v,w in -1..1 for <secs>, then release

    """.utf8))
    exit(2)
}

// MARK: - selftest

func selftest() -> Never {
    var failures = 0
    func check(_ ok: Bool, _ what: String) {
        print(ok ? "  ok    \(what)" : "  FAIL  \(what)")
        if !ok { failures += 1 }
    }

    print("status decode")
    // enabled | cmd active | encA | encB = 0b0001_1101, no battery,
    // wheel A +1.000 turns/s, wheel B -1.000 turns/s, command -0.250 m/s.
    let frame: [UInt8] = [0b0001_1101, 0x00, 0x00, 0x00, 0x00,
                          0xE8, 0x03,
                          0x18, 0xFC,
                          0x06, 0xFF,
                          0x00, 0x00]
    guard let s = UBotStatus(Data(frame)) else {
        print("  FAIL  13 bytes did not decode"); exit(1)
    }
    check(s.isEnabled, "enabled flag")
    check(s.isCommandActive, "command active flag")
    check(s.encoderAOK && s.encoderBOK, "both encoder flags")
    check(!s.isFaulted, "not faulted")
    check(!s.batteryIsSensed, "battery reported as not sensed")
    check(s.fault == .none, "fault none")
    check(s.wheelATurnsPerSec == 1.0, "wheel A +1.000 turns/s")
    check(s.wheelBTurnsPerSec == -1.0, "wheel B -1.000 turns/s (two's complement)")
    check(s.commandedMetersPerSec == -0.250, "commanded -0.250 m/s")
    check(s.commandedRadiansPerSec == 0.0, "commanded 0 rad/s")

    print("status decode, defensive")
    check(UBotStatus(Data([0x01, 0x00])) == nil, "short frame rejected")
    check(UBotStatus(Data(frame + [0xAA, 0xBB])) != nil,
          "longer frame accepted (firmware may widen the packet)")
    // A sliced Data keeps its parent's indices; the decoder must not trap.
    let sliced = Data([0xFF, 0xFF] + frame).dropFirst(2)
    check(UBotStatus(sliced)?.wheelATurnsPerSec == 1.0, "sliced Data decodes")

    print("fault enum")
    check(DriveFault(rawValue: 1) == .slip, "1 is slip")
    check(DriveFault(rawValue: 4) == .peer, "4 is peer")
    check(UBotStatus(Data([0, 99] + frame.dropFirst(2)))?.fault == DriveFault.none,
          "unknown fault byte degrades to none")

    print("drive encode")
    check(DriveCommand(v: 0, w: 0).frame == Data([0, 0, 0, 0]), "zero is four zero bytes")
    check(DriveCommand(v: 1, w: 0).frame == Data([0xE8, 0x03, 0x00, 0x00]), "+1.0 is 1000 LE")
    check(DriveCommand(v: -1, w: 0).frame == Data([0x18, 0xFC, 0x00, 0x00]), "-1.0 is -1000 LE")
    check(DriveCommand(v: 0, w: 1).frame == Data([0x00, 0x00, 0xE8, 0x03]), "w lands in bytes 2-3")
    check(DriveCommand(v: 5, w: -5).frame == Data([0xE8, 0x03, 0x18, 0xFC]), "out of range clamps")
    check(DriveCommand(v: 0, w: 0).frame.count == 4, "always exactly 4 bytes")

    print("stick math (joystick.html: v = -y, w = -x, clamped to the unit disc)")
    let up = DriveCommand(stickX: 0, stickY: -1)
    check(up.v == 1 && up.w == 0, "up is full forward")
    let left = DriveCommand(stickX: -1, stickY: 0)
    check(left.v == 0 && left.w == 1, "left is positive w (anticlockwise)")
    let corner = DriveCommand(stickX: 1, stickY: 1)
    check(abs(corner.magnitude - 1) < 1e-9, "diagonal clamps to the unit circle")
    check(abs(corner.v + 0.7071067) < 1e-5 && abs(corner.w + 0.7071067) < 1e-5,
          "diagonal splits evenly")

    print("control ops")
    check(ControlOp.stop.frame == Data([0]), "stop is 0")
    check(ControlOp.enable.frame == Data([1]), "enable is 1")
    check(ControlOp.disable.frame == Data([2]), "disable is 2")
    check(ControlOp.estop.frame == Data([3]), "estop is 3")
    check(ControlOp.clearFaults.frame == Data([4]), "clear is 4")

    print("lock model")
    let off = UBotStatus(flags: [])
    check(DriveLock.derive(linkState: .ready(name: "ubot"), status: off)?.remedy == .enable,
          "motors off -> Enable")
    let faultedOn = UBotStatus(flags: [.enabled, .faulted], fault: .slip)
    check(DriveLock.derive(linkState: .ready(name: "ubot"), status: faultedOn)?.remedy == .clearFaults,
          "faulted while enabled -> Clear")
    let faultedOff = UBotStatus(flags: [.faulted], fault: .magnet)
    check(DriveLock.derive(linkState: .ready(name: "ubot"), status: faultedOff)?.remedy == .enable,
          "faulted while disabled -> Enable (enabling clears)")
    check(DriveLock.derive(linkState: .ready(name: "ubot"),
                           status: UBotStatus(flags: [.enabled])) == nil,
          "enabled and healthy -> unlocked")
    check(DriveLock.derive(linkState: .stalled(name: "ubot"),
                           status: UBotStatus(flags: [.enabled])) != nil,
          "stale telemetry locks even when the status looks fine")
    check(DriveLock.derive(linkState: .ready(name: "ubot"),
                           status: UBotStatus(flags: [.enabled, .commandActive])) == nil,
          "another controller driving does not lock us out")

    print("")
    if failures == 0 {
        print("all checks passed")
        exit(0)
    }
    print("\(failures) check(s) failed")
    exit(1)
}

if command == "selftest" { selftest() }
if command == "help" || command == "-h" || command == "--help" { usage() }

// MARK: - Live commands

final class Runner: @unchecked Sendable {
    let link = BLERobotLink()
    var lastStatus: UBotStatus?
    var firmware = "?"
    var rowCount = 0
    var announced = false

    func begin(_ onReady: @escaping () -> Void) {
        link.onEvent = { [self] event in
            switch event {
            case .state(let s):
                FileHandle.standardError.write(Data("[\(s.summary)]\n".utf8))
                if s.isReady, !announced { announced = true; onReady() }
            case .status(let s):
                lastStatus = s
            case .firmware(let f):
                firmware = f
            case .model(let m):
                FileHandle.standardError.write(Data("[model \(m)]\n".utf8))
            case .controlAccepted(let op):
                print("accepted: \(op.title)")
            case .controlRefused(let op, let why):
                print("REFUSED: \(op.title) -- \(why)")
            case .linkQuality(let w, let d, let e):
                if d > 0 || e > 0 {
                    FileHandle.standardError.write(
                        Data("[link: \(w) written, \(d) dropped, \(e) escalated]\n".utf8))
                }
            case .batteryLevel:
                break
            }
        }
        link.start()
    }

    func printStatusLine() {
        guard let s = lastStatus else { return }
        func pad(_ t: String, _ n: Int) -> String {
            t.count >= n ? t : t + String(repeating: " ", count: n - t.count)
        }
        func num(_ d: Double) -> String {
            pad(String(format: "%.3f", d), 9)
        }
        if rowCount % 20 == 0 {
            print(pad("state", 9) + pad("flags", 8) + pad("fault", 8) + pad("battery", 13)
                  + pad("velA", 9) + pad("velB", 9) + pad("cmd m/s", 9) + "cmd rad/s")
        }
        rowCount += 1
        let state = s.isEnabled ? (s.isCommandActive ? "driving" : "on") : "off"
        let battery = s.batteryIsSensed
            ? String(format: "%d%% %.1fV", Int(s.batteryPercent), s.batteryVolts)
            : "not sensed"
        // Uppercase letter = bit set. E enabled, F faulted, C command active,
        // A/B encoder ok, P battery present. Without these on screen the table
        // cannot distinguish "the wheel is stationary" from "that encoder is
        // not answering", which are very different problems.
        let flags = [("E", s.isEnabled), ("F", s.isFaulted), ("C", s.isCommandActive),
                     ("A", s.encoderAOK), ("B", s.encoderBOK), ("P", s.batteryIsSensed)]
            .map { $0.1 ? $0.0 : "\u{00B7}" }.joined()
        print(pad(state, 9) + pad(flags, 8) + pad(s.isFaulted ? s.fault.title : "-", 8)
              + pad(battery, 13)
              + num(s.wheelATurnsPerSec) + num(s.wheelBTurnsPerSec)
              + num(s.commandedMetersPerSec) + String(format: "%.3f", s.commandedRadiansPerSec))
    }
}

let runner = Runner()

switch command {
case "scan":
    print("scanning; ^C to stop")
    runner.begin { print("connected") }

case "status":
    runner.begin {}
    let t = DispatchSource.makeTimerSource(queue: .main)
    t.schedule(deadline: .now() + 0.2, repeating: 0.2)
    t.setEventHandler { runner.printStatusLine() }
    t.resume()
    withExtendedLifetime(t) { dispatchMain() }

case "enable", "disable", "stop", "estop", "clear":
    let op: ControlOp = {
        switch command {
        case "enable":  return .enable
        case "disable": return .disable
        case "stop":    return .stop
        case "estop":   return .estop
        default:        return .clearFaults
        }
    }()
    runner.begin {
        runner.link.send(op)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            runner.printStatusLine()
            exit(0)
        }
    }

case "drive":
    guard args.count >= 4,
          let v = Double(args[1]), let w = Double(args[2]), let secs = Double(args[3])
    else { usage() }
    print("driving v=\(v) w=\(w) for \(secs)s -- ^C releases")
    runner.begin {
        let c = DriveCommand(v: v, w: w)
        runner.link.engage(c)
        let t = DispatchSource.makeTimerSource(queue: .main)
        t.schedule(deadline: .now() + 0.2, repeating: 0.2)
        t.setEventHandler { runner.printStatusLine() }
        t.resume()
        DispatchQueue.main.asyncAfter(deadline: .now() + secs) {
            t.cancel()
            runner.link.releaseStick()
            print("released; the robot ramps to a stop")
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { exit(0) }
        }
    }

default:
    usage()
}

dispatchMain()
