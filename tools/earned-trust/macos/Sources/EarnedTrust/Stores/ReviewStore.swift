import Foundation
import Observation
import TrustCore

@Observable @MainActor
final class ReviewStore {
    var packets: [LoadedPacket] = []
    var selection: String?
    var error: String?
    var loading = false
    var decisions: [String: ReviewDecision] = [:]
    private var started = false

    var selected: LoadedPacket? { packets.first { $0.id == selection } }
    var selectedDecision: ReviewDecision? {
        guard let selected else { return nil }
        return decisions[selected.sha256]
    }

    func loadBundled() {
        guard !started else { return }
        started = true
        guard let root = Bundle.module.url(forResource: "Packets", withExtension: nil),
              let enumerator = FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey], options: [.skipsHiddenFiles]) else {
            error = "Bundled review packets are unavailable. Import a packet to begin."
            return
        }
        var failures: [String] = []
        for case let url as URL in enumerator where url.lastPathComponent == "packet.json" {
            do { try append(PacketLoader.load(url: url)) }
            catch { failures.append("\(url.deletingLastPathComponent().lastPathComponent): \(error.localizedDescription)") }
        }
        packets.sort {
            let first = Int($0.packet.source.issueId) ?? 0
            let second = Int($1.packet.source.issueId) ?? 0
            return first == second ? $0.id < $1.id : first < second
        }
        selection = packets.first(where: { $0.id == "tieto-2283" })?.id ?? packets.first?.id
        if !failures.isEmpty { error = failures.joined(separator: "\n") }
    }

    func importPacket(_ url: URL) {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do {
            let packet = try PacketLoader.load(url: url)
            try append(packet)
            selection = packet.id
        } catch { self.error = error.localizedDescription }
    }

    func reload() {
        guard let selected else { return }
        do { try append(PacketLoader.load(url: selected.url)) }
        catch {
            decisions.removeValue(forKey: selected.sha256)
            packets.removeAll { $0.id == selected.id }
            selection = packets.first?.id
            self.error = "Reload failed; the previous assessment was removed. \(error.localizedDescription)"
        }
    }

    func record(reviewer: String, decision: LocalDecision, rationale: String) throws -> ReviewDecision {
        guard let selected else { throw PacketError.invalid("Select a review packet first.") }
        let result = try ReviewDecision.record(packet: selected, reviewer: reviewer, decision: decision, rationale: rationale)
        decisions[selected.sha256] = result
        return result
    }

    private func append(_ packet: LoadedPacket) throws {
        if let index = packets.firstIndex(where: { $0.id == packet.id }) {
            let previous = packets[index]
            if previous.sha256 != packet.sha256 || previous.integrity != packet.integrity {
                decisions.removeValue(forKey: previous.sha256)
            }
            packets[index] = packet
        } else {
            guard packets.count < 50 else { throw PacketError.invalid("This window can hold at most 50 review packets.") }
            packets.append(packet)
        }
    }
}
