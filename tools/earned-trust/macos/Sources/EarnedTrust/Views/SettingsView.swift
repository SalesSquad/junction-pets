import SwiftUI

struct SettingsView: View {
    var body: some View {
        Form {
            Section("Earned Trust") {
                LabeledContent("Runtime", value: "Offline · No model or network execution")
                LabeledContent("Evidence", value: "Source and local file integrity")
                LabeledContent("Decisions", value: "Declared by a person · Exported as JSON")
            }
            Section("Review shortcuts") {
                LabeledContent("Import a packet", value: "⌘O")
                LabeledContent("Reload evidence", value: "⌘R")
                LabeledContent("Record a decision", value: "⇧⌘R")
            }
            Text("This reference illustrates accountable review. It does not authenticate a runner, verify a person, execute code or merge a change.")
                .font(.caption).foregroundStyle(.secondary)
        }.formStyle(.grouped).padding(10).frame(width: 520, height: 340)
    }
}
