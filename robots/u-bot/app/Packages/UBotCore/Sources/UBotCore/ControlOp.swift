import Foundation

/// The one-byte ops accepted by `7B1A0002`.
///
/// Unlike the drive characteristic, these are written *with* a response, so a
/// refusal actually reaches us as `BLE_ATT_ERR_UNLIKELY` (0x0E). This is the
/// only channel on which the robot can say no.
public enum ControlOp: UInt8, Sendable, CaseIterable {
    case stop        = 0
    case enable      = 1
    case disable     = 2
    case estop       = 3
    case clearFaults = 4

    public var frame: Data { Data([rawValue]) }

    public var title: String {
        switch self {
        case .stop:        return "Stop"
        case .enable:      return "Enable motors"
        case .disable:     return "Disable motors"
        case .estop:       return "E-STOP"
        case .clearFaults: return "Clear fault"
        }
    }

    /// The firmware logs a refusal sentence but does not put it on the wire --
    /// `drive_refusal()` never crosses BLE, only the ATT error code does. So we
    /// synthesise the most likely explanation per op.
    public var refusalText: String {
        switch self {
        case .enable:
            return "The robot would not enable the motors. A driver may not be "
                 + "answering on the bus, or a calibration is running. Check motor power."
        case .clearFaults:
            return "The robot would not clear the fault. It may still be present."
        case .stop, .disable, .estop:
            return "The robot refused the command."
        }
    }
}
