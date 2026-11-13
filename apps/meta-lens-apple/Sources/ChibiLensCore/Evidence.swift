import Foundation

/// Client-provided metadata is ALWAYS untrusted until the authenticated Chibi host admits it.
public enum LensSourceKind: String, Codable, Sendable {
    case metaCamera = "meta-camera"
    case phoneCamera = "phone-camera"
    case fixture
    case imported = "import"
}

public enum CaptureConsent: String, Codable, Sendable {
    case unknown
    case granted
    case denied
    case revoked
}

public struct CaptureGate: Sendable {
    public let consent: CaptureConsent
    public let platformPermissionGranted: Bool
    public let bystanderClearance: Bool
    public let sessionGeneration: Int

    public init(
        consent: CaptureConsent,
        platformPermissionGranted: Bool,
        bystanderClearance: Bool,
        sessionGeneration: Int
    ) {
        self.consent = consent
        self.platformPermissionGranted = platformPermissionGranted
        self.bystanderClearance = bystanderClearance
        self.sessionGeneration = sessionGeneration
    }

    public var canPreview: Bool {
        consent == .granted && platformPermissionGranted && bystanderClearance
            && sessionGeneration > 0
    }
}

public struct LensCandidate: Codable, Hashable, Sendable {
    public let id: String
    public let label: String
    public let confidence: Double

    public init(id: String, label: String, confidence: Double) {
        self.id = id
        self.label = label
        self.confidence = confidence
    }
}

public struct LensFrameDraft: Sendable {
    public let observationID: String
    public let sessionID: String
    public let generation: Int
    public let receivedAtMs: Int64
    public let source: LensSourceKind
    public let frameSHA256: String
    public let width: Int
    public let height: Int
    public let candidates: [LensCandidate]

    public init(
        observationID: String, sessionID: String, generation: Int,
        receivedAtMs: Int64, source: LensSourceKind, frameSHA256: String,
        width: Int, height: Int, candidates: [LensCandidate]
    ) {
        self.observationID = observationID
        self.sessionID = sessionID
        self.generation = generation
        self.receivedAtMs = receivedAtMs
        self.source = source
        self.frameSHA256 = frameSHA256
        self.width = width
        self.height = height
        self.candidates = candidates
    }

    /// A successfully checked draft is not a host admission receipt or device proof.
    public var provenance: String { "client-unverified" }
}

public enum LensAdmissionError: Error, Equatable {
    case captureNotAllowed
    case staleSession
    case invalidDraft
}

public enum LensDraftValidator {
    public static func check(
        _ draft: LensFrameDraft, gate: CaptureGate, activeSessionID: String
    ) throws {
        guard gate.canPreview else { throw LensAdmissionError.captureNotAllowed }
        guard draft.generation == gate.sessionGeneration,
              draft.sessionID == activeSessionID else {
            throw LensAdmissionError.staleSession
        }
        guard !draft.observationID.isEmpty,
              !draft.sessionID.isEmpty,
              !activeSessionID.isEmpty,
              draft.sessionID.utf16.count <= 160,
              draft.receivedAtMs >= 0,
              (1...16384).contains(draft.width),
              (1...16384).contains(draft.height),
              draft.frameSHA256.count == 64,
              draft.frameSHA256.utf8.allSatisfy({ ($0 >= 48 && $0 <= 57) || ($0 >= 97 && $0 <= 102) }),
              draft.candidates.count <= 32 else {
            throw LensAdmissionError.invalidDraft
        }
        var ids = Set<String>()
        for candidate in draft.candidates {
            guard !candidate.id.isEmpty,
                  !candidate.label.isEmpty,
                  candidate.confidence.isFinite,
                  (0...1).contains(candidate.confidence),
                  ids.insert(candidate.id).inserted else {
                throw LensAdmissionError.invalidDraft
            }
        }
    }
}

public struct LensSighting: Codable, Hashable, Sendable {
    public let id: String
    public let targetID: String
    public let zone: String
    public let observedAtMs: Int64
    public let observationRef: String

    public init(
        id: String, targetID: String, zone: String,
        observedAtMs: Int64, observationRef: String
    ) {
        self.id = id
        self.targetID = targetID
        self.zone = zone
        self.observedAtMs = observedAtMs
        self.observationRef = observationRef
    }
}

public struct LensTimeline: Sendable {
    private var events: [LensSighting]

    public init(events: [LensSighting]) { self.events = events }

    public func history(for targetID: String) -> [LensSighting] {
        events.filter { $0.targetID == targetID }.sorted {
            $0.observedAtMs == $1.observedAtMs
                ? $0.id < $1.id : $0.observedAtMs > $1.observedAtMs
        }
    }

    /// Last observed is historical evidence, never a present-location assertion.
    public func lastObserved(for targetID: String) -> LensSighting? {
        history(for: targetID).first
    }
}

public enum LensCandidateVerdict: String, Codable, Sendable {
    case possibleMatch = "possible-match"
    case ambiguous
    case notObserved = "not-observed"
}

public struct LensAssessment: Sendable {
    public let verdict: LensCandidateVerdict
    public let suggestedID: String?
    public let explanation: String

    /// Candidate ranking, even with high confidence, is NOT a physical identity proof.
    public var identityVerified: Bool { false }
    public var actionAuthorized: Bool { false }

    public static func assess(_ candidates: [LensCandidate]) -> LensAssessment {
        let sorted = candidates.sorted { $0.confidence > $1.confidence }
        guard let first = sorted.first else {
            return LensAssessment(verdict: .notObserved, suggestedID: nil,
                                  explanation: "Not observed in this frame; history is unchanged.")
        }
        guard first.confidence >= 0.80,
              sorted.dropFirst().first.map({ first.confidence - $0.confidence >= 0.15 }) ?? true else {
            return LensAssessment(verdict: .ambiguous, suggestedID: nil,
                                  explanation: "Lookalikes are too similar. Check a unique label.")
        }
        return LensAssessment(verdict: .possibleMatch, suggestedID: first.id,
                              explanation: "Possible match only. Ask the host to verify unique evidence.")
    }
}

/// Source-port contract for the existing JS `validateRequest`. No trusted actor/tenant is
/// created here: the private Chibi host derives identity and validates all receipts.
public struct LensScanRequest: Encodable, Sendable {
    public enum Mode: String, Encodable, Sendable { case inspect, find, verify }

    public let schemaVersion = 1
    public let requestId: String
    public let sessionId: String
    public let mode: Mode
    public let query: String
    public let observationRef: String?
    public let observationSha256: String?
    public let targetId: String?

    public enum ValidationError: Error, Equatable { case invalidInput }

    private init(
        requestId: String, sessionId: String, mode: Mode, query: String,
        observationRef: String? = nil, observationSha256: String? = nil,
        targetId: String? = nil
    ) {
        self.requestId = requestId
        self.sessionId = sessionId
        self.mode = mode
        self.query = query
        self.observationRef = observationRef
        self.observationSha256 = observationSha256
        self.targetId = targetId
    }

    public static func find(requestID: String, sessionID: String, query: String) -> Self {
        .init(requestId: requestID, sessionId: sessionID, mode: .find, query: query)
    }

    /// `digest` MUST be the authenticated host's canonical observation digest,
    /// not a locally hashed JPEG or a model-generated string.
    public static func inspect(
        requestID: String, sessionID: String, query: String,
        hostObservationRef: String, hostObservationDigest: String
    ) -> Self {
        .init(requestId: requestID, sessionId: sessionID, mode: .inspect,
              query: query, observationRef: hostObservationRef,
              observationSha256: hostObservationDigest)
    }

    public static func verify(
        requestID: String, sessionID: String, query: String, targetID: String,
        hostObservationRef: String, hostObservationDigest: String
    ) -> Self {
        .init(requestId: requestID, sessionId: sessionID, mode: .verify,
              query: query, observationRef: hostObservationRef,
              observationSha256: hostObservationDigest, targetId: targetID)
    }

    /// Local preflight parity with JS `validateRequest`, not a grant or a host receipt.
    /// An authenticated host MUST enforce the contract again after transport.
    @discardableResult
    public func validated() throws -> Self {
        func validText(_ value: String, max: Int = 160) -> Bool {
            !value.isEmpty && value.utf16.count <= max
                && value == value.trimmingCharacters(in: .whitespacesAndNewlines)
                && !value.unicodeScalars.contains(where: { $0.value <= 31 })
        }
        func validDigest(_ value: String) -> Bool {
            value.utf8.count == 64 && value.utf8.allSatisfy {
                ($0 >= 48 && $0 <= 57) || ($0 >= 97 && $0 <= 102)
            }
        }
        guard validText(requestId), validText(sessionId),
              validText(query, max: 400) else {
            throw ValidationError.invalidInput
        }
        switch mode {
        case .find:
            guard observationRef == nil, observationSha256 == nil,
                  targetId == nil else { throw ValidationError.invalidInput }
        case .inspect:
            guard let ref = observationRef, validText(ref),
                  let hash = observationSha256, validDigest(hash),
                  targetId == nil else { throw ValidationError.invalidInput }
        case .verify:
            guard let ref = observationRef, validText(ref),
                  let hash = observationSha256, validDigest(hash),
                  let target = targetId, validText(target) else {
                throw ValidationError.invalidInput
            }
        }
        return self
    }
}
