import Foundation

public enum LocalDecision: String, Codable, CaseIterable, Sendable {
    case accept = "Accept for review"
    case requestEvidence = "Request evidence"
    case reject = "Reject"
}

public struct ReviewDecision: Codable, Sendable {
    public let schemaVersion: Int
    public let packetId: String
    public let packetSHA256: String
    public let source: ChangeSource
    public let declaredReviewer: String
    public let decision: LocalDecision
    public let rationale: String
    public let recordedAt: String
    public let verdictAtDecision: ReviewVerdict
    public let claims: [ClaimAssessment]
    public let logIntegrity: [String: LogIntegrity]
    public let reviewerAuthenticated: Bool
    public let codeChangeApproved: Bool
    public let remoteWritePerformed: Bool

    public static func record(packet: LoadedPacket, reviewer: String, decision: LocalDecision, rationale: String) throws -> ReviewDecision {
        let name = reviewer.trimmingCharacters(in: .whitespacesAndNewlines)
        let reason = rationale.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, name.count <= 150, !reason.isEmpty, reason.count <= 5000 else {
            throw PacketError.invalid("Enter a reviewer name and a short rationale.")
        }
        let current = try PacketLoader.load(url: packet.url)
        guard current.sha256 == packet.sha256, current.integrity == packet.integrity else {
            throw PacketError.invalid("The packet or evidence changed. Reload it before recording a decision.")
        }
        if decision == .accept && current.verdict != .ready {
            throw PacketError.invalid("Accept for review requires verified evidence for every behavioral claim.")
        }
        return ReviewDecision(schemaVersion: 1, packetId: current.id, packetSHA256: current.sha256,
                              source: current.packet.source, declaredReviewer: name, decision: decision, rationale: reason,
                              recordedAt: ISO8601DateFormatter().string(from: Date()), verdictAtDecision: current.verdict,
                              claims: current.assessments, logIntegrity: current.integrity,
                              reviewerAuthenticated: false, codeChangeApproved: false, remoteWritePerformed: false)
    }

    public func data() throws -> Data {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        return try encoder.encode(self)
    }
}
