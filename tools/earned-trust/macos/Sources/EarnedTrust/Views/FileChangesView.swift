import SwiftUI
import TrustCore

struct FileChangesView: View {
    let packet: LoadedPacket
    @State private var search = ""
    @State private var showGenerated = false

    private var matching: [ChangedFile] {
        packet.packet.files.filter { search.isEmpty || $0.path.localizedCaseInsensitiveContains(search) }
    }
    private var authored: [ChangedFile] { matching.filter { $0.role != .generatedSnapshot } }
    private var generated: [ChangedFile] { matching.filter { $0.role == .generatedSnapshot } }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeading(title: "Find the cause. Verify the consequences.", subtitle: "Generated snapshots are grouped separately; file count is not a measure of risk.")
            Surface {
                HStack(spacing: 28) {
                    count("Source, tests & docs", number: packet.packet.files.count - packet.generatedFiles)
                    Image(systemName: "arrow.right").foregroundStyle(.secondary)
                    count("Generated snapshots", number: packet.generatedFiles)
                    Spacer(minLength: 0)
                }
            }
            TextField("Filter changed paths", text: $search).textFieldStyle(.roundedBorder)
                .accessibilityLabel("Filter changed paths")
            Surface {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Review the authored change").font(.headline)
                    ForEach(authored) { file in row(file) }
                    if authored.isEmpty { Text("No matching authored paths.").foregroundStyle(.secondary) }
                }
            }
            if !generated.isEmpty {
                Surface {
                    DisclosureGroup(isExpanded: $showGenerated) {
                        LazyVStack(alignment: .leading, spacing: 13) { ForEach(generated) { file in row(file) } }.padding(.top, 16)
                    } label: {
                        Label("\(generated.count) generated snapshots", systemImage: "square.stack.3d.up")
                            .font(.headline)
                    }
                }
            }
            Text("Grouping is a source-derived inspection aid. It does not prove equivalence, coverage or runtime safety.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func count(_ label: String, number: Int) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(number, format: .number).font(.system(.largeTitle, design: .rounded).weight(.medium))
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
    }
    private func row(_ file: ChangedFile) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: file.role == .test ? "checkmark.square" : file.role == .documentation ? "doc.text" : "chevron.left.forwardslash.chevron.right")
                .foregroundStyle(.secondary).frame(width: 16)
            VStack(alignment: .leading, spacing: 4) {
                Text(file.path).font(.caption.monospaced()).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                Text(file.group).font(.caption2).foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Text("+\(file.additions)").foregroundStyle(.green)
            Text("−\(file.deletions)").foregroundStyle(.secondary)
        }.font(.caption.monospaced())
    }
}
