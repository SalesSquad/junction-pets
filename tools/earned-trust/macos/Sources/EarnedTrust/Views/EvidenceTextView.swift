import AppKit
import SwiftUI

struct EvidencePreview: Identifiable {
    let id = UUID()
    let title: String
    let text: String
}

struct EvidenceTextView: View {
    let preview: EvidencePreview
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 5) {
                    Text(preview.title).font(.title2.weight(.semibold))
                    Text("Local bytes match the packet digest. The source is not authenticated.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button("Copy text") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(preview.text, forType: .string)
                }
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
            ScrollView([.horizontal, .vertical]) {
                Text(preview.text).font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .topLeading).padding(16)
            }.background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
        }.padding(24).frame(minWidth: 780, idealWidth: 880, minHeight: 540, idealHeight: 640)
    }
}
