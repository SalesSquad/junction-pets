import AppKit
import SwiftUI
import TrustCore

struct ProvenanceView: View {
    let packet: LoadedPacket

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 23) {
                Label("Evidence provenance", systemImage: "link").font(.headline)
                item("Requirement", value: packet.packet.requirement.id)
                item("Source branch", value: packet.packet.source.branch)
                item("Base commit", value: packet.packet.source.baseSha, mono: true)
                item("Changed commit", value: packet.packet.source.headSha, mono: true)
                Divider()
                item("Toolchain", value: packet.packet.provenance.toolchain)
                item("Evidence origin", value: packet.packet.provenance.origin)
                item("Packet SHA-256", value: packet.sha256, mono: true)
                item("Recorded", value: packet.packet.generatedAt)
                Text(packet.packet.provenance.note).font(.caption).foregroundStyle(.secondary)
                Divider()
                VStack(alignment: .leading, spacing: 10) {
                    if let url = PacketLoader.approvedGitHubURL(packet.packet.source.issueURL) {
                        Link(destination: url) { Label("Original requirement", systemImage: "arrow.up.right.square") }
                    }
                    if let url = PacketLoader.approvedGitHubURL(packet.packet.source.repository + "/commit/" + packet.packet.source.headSha) {
                        Link(destination: url) { Label("Pinned change", systemImage: "arrow.up.right.square") }
                    }
                    Button {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(packet.packet.source.repository + "@" + packet.packet.source.headSha, forType: .string)
                    } label: { Label("Copy source reference", systemImage: "doc.on.doc") }
                }.font(.callout).buttonStyle(.plain)
                Text("Local integrity verified where shown. Runner identity, log truthfulness and human identity are not authenticated.")
                    .font(.caption).foregroundStyle(.secondary)
            }.padding(22)
        }
    }

    private func item(_ title: String, value: String, mono: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.caption.weight(.medium)).foregroundStyle(.secondary)
            Text(value).font(mono ? .caption.monospaced() : .callout)
                .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
        }
    }
}
