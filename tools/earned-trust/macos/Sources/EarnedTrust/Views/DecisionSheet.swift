import SwiftUI
import TrustCore

struct DecisionSheet: View {
    let packet: LoadedPacket
    let save: (String, LocalDecision, String) throws -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var reviewer = ""
    @State private var decision: LocalDecision = .requestEvidence
    @State private var rationale = ""
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                Image(systemName: "person.crop.circle.badge.checkmark").font(.largeTitle).foregroundStyle(.tint)
                VStack(alignment: .leading, spacing: 5) {
                    Text("Your judgment, recorded").font(.title2.weight(.semibold))
                    Text("Issue #\(packet.packet.source.issueId) · Local declaration").foregroundStyle(.secondary)
                }
            }
            Text("A review records what you concluded and why. It does not verify your identity or approve a repository change.")
                .font(.callout).foregroundStyle(.secondary)
            Form {
                TextField("Reviewer name", text: $reviewer)
                Picker("Decision", selection: $decision) {
                    ForEach(LocalDecision.allCases, id: \.self) { value in
                        Text(value.rawValue).tag(value).disabled(value == .accept && packet.verdict != .ready)
                    }
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("Why this decision?").font(.callout)
                    TextEditor(text: $rationale).frame(height: 110)
                        .overlay(RoundedRectangle(cornerRadius: 5).strokeBorder(.quaternary))
                }
            }.formStyle(.grouped)
            if packet.verdict != .ready {
                Label("Acceptance is unavailable until every behavioral claim has evidence.", systemImage: "lock")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let error { Text(error).font(.callout).foregroundStyle(.red) }
            HStack {
                Text("The packet and logs are rechecked before export.").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Record & Export…") {
                    do { try save(reviewer, decision, rationale) } catch { self.error = error.localizedDescription }
                }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .disabled(reviewer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || rationale.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }.padding(28).frame(width: 620)
    }
}
