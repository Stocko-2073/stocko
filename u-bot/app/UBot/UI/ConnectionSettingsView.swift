import SwiftUI
import UBotCore

struct ConnectionSettingsView: View {
    @Environment(AppSettings.self) private var settings
    @Environment(\.dismiss) private var dismiss
    let controller: RobotController
    @State private var address = ""

    var body: some View {
        NavigationStack {
            Form {
                if let firmware = controller.firmware {
                    LabeledContent("Firmware", value: firmware)
                }
                Section {
                    TextField("Robot address", text: $address)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    Button("Reset to ubot.local") { address = "ubot.local" }
                } header: { Text("Wi-Fi") } footer: {
                    Text("Enter the robot hostname or IP address, optionally with a port. Your phone and robot must be on a reachable local network.")
                }
                if WiFiProtocol.endpoint(address) == nil {
                    Text("Enter a hostname or IP address without a URL path.")
                        .foregroundStyle(.red)
                }
            }
            .navigationTitle("Connection")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        let value = address.trimmingCharacters(in: .whitespacesAndNewlines)
                        let changed = settings.wifiAddress != value
                        settings.wifiAddress = value
                        if changed && settings.transport == .wifi {
                            controller.selectTransport(.wifi, address: value)
                        }
                        dismiss()
                    }
                    .disabled(WiFiProtocol.endpoint(address) == nil)
                }
            }
        }
        .onAppear { address = settings.wifiAddress }
    }
}
