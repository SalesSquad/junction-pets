import SwiftUI
import TrustCore

struct SidebarView: View {
    @Bindable var store: ReviewStore

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 9) {
                Label("EARNED TRUST", systemImage: "checkmark.shield.fill")
                    .font(.caption.weight(.bold)).tracking(1.6).foregroundStyle(.tint)
                Text("A change.\nA reason to trust it.").font(.title2.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                Text("Tieto · Junction 2026").font(.caption).foregroundStyle(.secondary)
            }.padding(20)

            List(selection: $store.selection) {
                Section("Review cases") {
                    ForEach(store.packets) { packet in
                        HStack(spacing: 9) {
                            Image(systemName: packet.verdict.icon).foregroundStyle(packet.verdict.color).frame(width: 18)
                            VStack(alignment: .leading, spacing: 3) {
                                Text("Issue #\(packet.packet.source.issueId)").fontWeight(.medium)
                                Text(packet.packet.title).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                            }
                        }
                        .padding(.vertical, 4)
                        .tag(packet.id)
                    }
                }
            }.listStyle(.sidebar)

            VStack(alignment: .leading, spacing: 6) {
                Label("Offline review desk", systemImage: "desktopcomputer").font(.caption.weight(.medium))
                Text("Evidence stays on this Mac.\nYour decision stays yours.").font(.caption).foregroundStyle(.secondary)
            }.padding(20)
        }
    }
}
