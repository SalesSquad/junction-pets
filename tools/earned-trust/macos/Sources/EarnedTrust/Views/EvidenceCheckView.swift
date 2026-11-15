import SwiftUI
import TrustCore

struct EvidenceCheckView: View {
    let packet: LoadedPacket
    let check: EvidenceCheck
    let integrity: LogIntegrity?
    @State private var expanded = false
    @State private var preview: EvidencePreview?
    @State private var error: String?

    var body: some View {
        Surface {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(check.title).font(.headline)
                        Text("\(check.kind.rawValue.capitalized) · \(check.evidence.rawValue.capitalized)").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if integrity?.verified == true {
                        Label("Bytes verified", systemImage: "checkmark.seal.fill").font(.caption).foregroundStyle(.green)
                    } else if check.kind == .structural {
                        Text("Source inspection").font(.caption).foregroundStyle(.secondary)
                    } else {
                        Label("Evidence incomplete", systemImage: "exclamationmark.circle").font(.caption).foregroundStyle(.orange)
                    }
                }
                HStack(spacing: 18) {
                    outcome("BASE", value: check.baseOutcome, sha: check.baseSourceSha)
                    Image(systemName: "arrow.right").font(.title3).foregroundStyle(.secondary)
                    outcome("CHANGE", value: check.headOutcome, sha: check.headSourceSha)
                }
                if check.baseLog != nil || check.headLog != nil {
                    HStack {
                        Button("View base evidence") { showEvidence(head: false) }.disabled(check.baseLog == nil)
                        Button("View change evidence") { showEvidence(head: true) }.disabled(check.headLog == nil)
                    }.buttonStyle(.bordered).controlSize(.small)
                }
                DisclosureGroup("Check details", isExpanded: $expanded) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Requirement: \(check.requirementId)").font(.caption.monospaced())
                        if let harness = check.baseHarnessSha256 {
                            Text("Frozen harness: \(harness)").font(.caption.monospaced()).textSelection(.enabled)
                        }
                        ForEach(Array(check.limitations.enumerated()), id: \.offset) { _, line in Text(line).font(.callout).foregroundStyle(.secondary) }
                        if check.kind != .structural {
                            ForEach(Array((integrity?.reasons ?? []).enumerated()), id: \.offset) { _, reason in
                                Text(reason).font(.callout).foregroundStyle(.orange)
                            }
                        }
                    }.padding(.top, 8).frame(maxWidth: .infinity, alignment: .leading)
                }.font(.callout)
            }
        }
        .sheet(item: $preview) { item in EvidenceTextView(preview: item) }
        .alert("Evidence unavailable", isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })) {
            Button("OK", role: .cancel) { error = nil }
        } message: { Text(error ?? "") }
    }

    private func showEvidence(head: Bool) {
        do {
            preview = EvidencePreview(title: head ? "Changed version evidence" : "Base version evidence",
                                      text: try PacketLoader.evidenceText(packet: packet, check: check, head: head))
        } catch { self.error = error.localizedDescription }
    }

    private func outcome(_ title: String, value: CheckOutcome, sha: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.caption2.weight(.semibold)).tracking(1.2).foregroundStyle(.secondary)
            Text(value.label).font(.title2.weight(.semibold)).foregroundStyle(value.color)
            Text(String(sha.prefix(12))).font(.caption.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
        }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(value.color.opacity(0.065), in: RoundedRectangle(cornerRadius: 9))
    }
}
