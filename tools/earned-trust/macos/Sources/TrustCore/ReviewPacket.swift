import Foundation

public struct ReviewPacket: Codable, Sendable {
    public let schemaVersion: Int
    public let packetId: String
    public let title: String
    public let generatedAt: String
    public let source: ChangeSource
    public let requirement: Requirement
    public let checks: [EvidenceCheck]
    public let claims: [ReviewClaim]
    public let files: [ChangedFile]
    public let provenance: Provenance
    public let limitations: [String]
}

public struct ChangeSource: Codable, Sendable {
    public let repository: String
    public let baseSha: String
    public let headSha: String
    public let issueId: String
    public let issueURL: String
    public let branch: String
}

public struct Requirement: Codable, Sendable {
    public let id: String
    public let summary: String
    public let details: String
}

public enum CheckKind: String, Codable, Sendable { case differential, regression, structural }
public enum EvidenceClass: String, Codable, Sendable { case observed, historical, synthetic }
public enum CheckOutcome: String, Codable, Sendable { case pass, fail, notRun, error }
public enum ClaimKind: String, Codable, Sendable { case fix, invariant, structural }
public enum FileRole: String, Codable, Sendable { case source, generatedSnapshot, documentation, test, other }

public struct EvidenceCheck: Codable, Identifiable, Sendable {
    public let id: String
    public let title: String
    public let requirementId: String
    public let kind: CheckKind
    public let evidence: EvidenceClass
    public let baseOutcome: CheckOutcome
    public let headOutcome: CheckOutcome
    public let baseSourceSha: String
    public let headSourceSha: String
    public let baseHarnessSha256: String?
    public let headHarnessSha256: String?
    public let baseLog: String?
    public let headLog: String?
    public let baseLogSha256: String?
    public let headLogSha256: String?
    public let limitations: [String]
}

public struct ReviewClaim: Codable, Identifiable, Sendable {
    public let id: String
    public let title: String
    public let requirementId: String
    public let kind: ClaimKind
    public let checkIds: [String]
    public let paths: [String]
}

public struct ChangedFile: Codable, Identifiable, Sendable {
    public var id: String { path }
    public let path: String
    public let role: FileRole
    public let additions: Int
    public let deletions: Int
    public let group: String
}

public struct Provenance: Codable, Sendable {
    public let toolchain: String
    public let origin: String
    public let note: String
}

public enum ReviewVerdict: String, Codable, Sendable {
    case ready = "READY FOR HUMAN"
    case needsEvidence = "NEEDS EVIDENCE"
    case inspectionOnly = "INSPECTION ONLY"
}

public struct ClaimAssessment: Codable, Identifiable, Sendable {
    public let id: String
    public let title: String
    public let verdict: ReviewVerdict
    public let reasons: [String]
}

public struct LogIntegrity: Codable, Equatable, Sendable {
    public let baseVerified: Bool
    public let headVerified: Bool
    public let reasons: [String]
    public var verified: Bool { baseVerified && headVerified }
}

public struct LoadedPacket: Identifiable, Sendable {
    public var id: String { packet.packetId }
    public let packet: ReviewPacket
    public let url: URL
    public let sha256: String
    public let integrity: [String: LogIntegrity]
    public let assessments: [ClaimAssessment]

    public var verdict: ReviewVerdict {
        guard !assessments.isEmpty else { return .needsEvidence }
        let behavioral = assessments.filter { $0.verdict != .inspectionOnly }
        if behavioral.isEmpty { return .inspectionOnly }
        return behavioral.allSatisfy({ $0.verdict == .ready }) ? .ready : .needsEvidence
    }
    public var verifiedLogPairs: Int { integrity.values.filter(\.verified).count }
    public var generatedFiles: Int { packet.files.filter { $0.role == .generatedSnapshot }.count }
}
