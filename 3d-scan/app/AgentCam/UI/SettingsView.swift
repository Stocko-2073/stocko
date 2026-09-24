import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(Settings.self) private var settings
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        @Bindable var settings = settings
        NavigationStack {
            Form {
                Section {
                    TextField("Found automatically", text: $settings.manualServer)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .onSubmit { model.manualServerChanged() }
                } header: {
                    Text("Mac address")
                } footer: {
                    Text("Leave empty to find the Mac over Bonjour. Otherwise its name or IP, e.g. Honeypot.local or 192.168.1.20:47815.")
                }
                if let problem = model.networkProblem {
                    Section("Network") {
                        Text(problem)
                        Button("Open Settings") {
                            if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                        }
                    }
                }
                Section {
                    Toggle("Show tracking details", isOn: $settings.showDebug)
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        model.manualServerChanged()
                        dismiss()
                    }
                }
            }
        }
    }
}
