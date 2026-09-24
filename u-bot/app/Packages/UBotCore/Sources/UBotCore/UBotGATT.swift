import CoreBluetooth
import Foundation

/// The GATT contract served by the robot, mirrored from
/// `firmware/base/components/ble/ble.c` and its header. When the firmware
/// changes, this is the one file to diff against `ble.h`.
public enum UBotGATT {

    // MARK: Identity

    /// The default advertised local name. Settable on the robot with
    /// `set name`, so the app treats it as a filter, not a constant.
    public static let defaultName = "ubot"

    // MARK: The U-BOT drive service

    /// `7b1a0000-6f4b-4c2e-9d3a-2e5f1c8a9b01`
    ///
    /// Advertised in the SCAN RESPONSE only -- it does not fit in the 31-byte
    /// advertisement alongside the local name. See the discovery note in
    /// `BLERobotLink`.
    public static let service = CBUUID(string: "7B1A0000-6F4B-4C2E-9D3A-2E5F1C8A9B01")

    /// Write / write-without-response. Exactly 4 bytes; anything else is
    /// rejected with `BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN`.
    public static let drive = CBUUID(string: "7B1A0001-6F4B-4C2E-9D3A-2E5F1C8A9B01")

    /// Write with response. Exactly 1 byte. Returns `BLE_ATT_ERR_UNLIKELY`
    /// (0x0E) when the drive layer refuses -- the only channel on which the
    /// robot tells us "no".
    public static let control = CBUUID(string: "7B1A0002-6F4B-4C2E-9D3A-2E5F1C8A9B01")

    /// Read / notify at 5 Hz. 13 bytes, packed little-endian.
    public static let status = CBUUID(string: "7B1A0003-6F4B-4C2E-9D3A-2E5F1C8A9B01")

    public static let managementRequest = CBUUID(string: "7B1A0004-6F4B-4C2E-9D3A-2E5F1C8A9B01")
    public static let managementResponse = CBUUID(string: "7B1A0005-6F4B-4C2E-9D3A-2E5F1C8A9B01")

    // MARK: Standard services

    public static let batteryService  = CBUUID(string: "180F")
    public static let batteryLevel    = CBUUID(string: "2A19")
    public static let deviceInfo      = CBUUID(string: "180A")
    public static let modelNumber     = CBUUID(string: "2A24")
    public static let firmwareRevision = CBUUID(string: "2A26")

    // MARK: Timing

    /// `DRIVE_HOLD_MS` in ble.c. Miss this and the robot ramps itself to a
    /// stop -- which is a feature, not a failure mode.
    public static let deadman: TimeInterval = 0.5

    /// 20 Hz. The web joystick uses 10 Hz over TCP, but a BLE
    /// write-without-response can be deferred by the radio scheduler, and at
    /// 20 Hz we can lose nine consecutive packets and still stay inside the
    /// deadman. Four bytes twenty times a second costs nothing.
    public static let tickInterval: TimeInterval = 0.05

    /// The status characteristic notifies at 5 Hz (200 ms). Silence past this
    /// means something is wrong even though CoreBluetooth still calls the link
    /// healthy -- see the `s_status_subscribed` note in `BLERobotLink`.
    public static let statusStaleAfter: TimeInterval = 1.5

    /// How long the write-without-response queue may stay shut before we
    /// escalate to an acknowledged write. Half the deadman.
    public static let backpressureEscapeAfter: TimeInterval = 0.25
}
