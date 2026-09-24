import SwiftUI
import UBotCore

struct RobotSettingsView: View {
    let controller: RobotController

    var body: some View {
        Form {
            Section {
                if let values = controller.driveSettings {
                    ForEach(DriveSetting.allCases) { setting in
                        NavigationLink {
                            DriveSettingEditor(controller: controller, setting: setting,
                                               initialValue: values[setting])
                        } label: {
                            LabeledContent(setting.title,
                                value: "\(setting.display(values[setting])) \(setting.unit)")
                        }
                        .accessibilityIdentifier("setting-\(setting.rawValue)")
                    }
                } else if controller.settingsBusy {
                    ProgressView("Reading robot settings…")
                } else {
                    Text("Refresh to read the robot's current settings.")
                        .foregroundStyle(.secondary)
                }
            } header: { Text("Wheel motion") } footer: {
                Text("These settings apply to both wheels and are saved on the robot across restarts. Turn the motors off before saving a change.")
            }
            if let notice = controller.settingsNotice {
                Section { Label(notice, systemImage: "checkmark.circle").foregroundStyle(.green) }
            }
            if let error = controller.settingsError {
                Section { Text(error).foregroundStyle(.red) }
            }
            Section {
                Button("Refresh from robot") { Task { await controller.refreshDriveSettings() } }
                    .disabled(controller.settingsBusy || !controller.linkState.isReady)
                if controller.status?.isEnabled == true {
                    Button("Turn motors off") { controller.send(.disable) }
                        .disabled(controller.settingsBusy || !controller.linkState.isReady)
                }
            }
        }
        .navigationTitle("Motion settings")
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(controller.settingsBusy)
        .task(id: controller.linkState) {
            if controller.driveSettings == nil { await controller.refreshDriveSettings() }
        }
    }
}

private struct DriveSettingEditor: View {
    let controller: RobotController
    let setting: DriveSetting
    @Environment(\.dismiss) private var dismiss
    @State private var input: String

    init(controller: RobotController, setting: DriveSetting, initialValue: Double) {
        self.controller = controller
        self.setting = setting
        _input = State(initialValue: setting.display(initialValue))
    }

    private var value: Double? {
        let decimal = Locale.current.decimalSeparator ?? "."
        return Double(input.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: decimal, with: "."))
    }
    private var valid: Bool { value.map(setting.accepts) ?? false }

    var body: some View {
        Form {
            Section {
                HStack {
                    TextField(setting.title, text: $input)
                        .keyboardType(.decimalPad)
                        .accessibilityIdentifier("setting-value")
                    Text(setting.unit).foregroundStyle(.secondary)
                }
                .disabled(controller.settingsBusy)
                if let current = controller.driveSettings?[setting] {
                    LabeledContent("On robot", value: "\(setting.display(current)) \(setting.unit)")
                }
            } footer: {
                Text("\(setting.detail) Allowed: \(setting.display(setting.range.lowerBound))–\(setting.display(setting.range.upperBound)) \(setting.unit).")
            }
            if !valid {
                Section { Text("Enter a number within the allowed range.").foregroundStyle(.red) }
            }
            if let error = controller.settingsError {
                Section { Text(error).foregroundStyle(.red) }
            }
            if controller.settingsBusy {
                Section { ProgressView("Saving and checking the robot…") }
            } else if controller.status?.isEnabled == true {
                Section {
                    Button("Turn motors off") { controller.send(.disable) }
                        .disabled(!controller.linkState.isReady)
                } footer: { Text("Turn the motors off to save this change.") }
            } else if controller.driveSettings == nil {
                Section {
                    Button("Refresh from robot") { Task { await controller.refreshDriveSettings() } }
                        .disabled(!controller.linkState.isReady)
                }
            }
        }
        .navigationTitle(setting.title)
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(controller.settingsBusy)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") {
                    guard let value else { return }
                    Task {
                        if await controller.saveDriveSetting(setting, value: value) { dismiss() }
                    }
                }
                .disabled(!valid || !controller.canSaveSettings)
            }
        }
    }
}
