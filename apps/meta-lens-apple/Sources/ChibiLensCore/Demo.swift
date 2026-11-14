import Foundation

public enum LensDemoPhase: Int, CaseIterable, Sendable {
    case history
    case lookalikes
    case revoked

    public var title: String {
        switch self {
        case .history: "Where was my USB-C charger?"
        case .lookalikes: "Is this the right charger?"
        case .revoked: "Capture access was revoked"
        }
    }

    public var answer: String {
        switch self {
        case .history:
            "Last observed on the hallway shelf. This is not a live location."
        case .lookalikes:
            "Two chargers look alike. A unique label is needed before confirmation."
        case .revoked:
            "Camera access is off. Existing notes remain available; continue manually."
        }
    }

    public var sourceLabel: String { "SYNTHETIC REPLAY — NO GLASSES CONNECTED" }

    public var canCapture: Bool { self != .revoked }

    public var candidateAssessment: LensAssessment {
        switch self {
        case .history: LensAssessment.assess([])
        case .lookalikes:
            LensAssessment.assess([
                .init(id: "charger-a", label: "65W USB-C charger", confidence: 0.87),
                .init(id: "charger-b", label: "65W USB-C charger", confidence: 0.84),
            ])
        case .revoked: LensAssessment.assess([])
        }
    }

    public func next() -> LensDemoPhase {
        LensDemoPhase(rawValue: (rawValue + 1) % LensDemoPhase.allCases.count) ?? .history
    }
}

public enum LensDemoFixture {
    public static let targetID = "charger-a"

    public static var history: [LensSighting] {
        LensTimeline(events: [
            LensSighting(id: "sight-older", targetID: targetID,
                         zone: "Desk", observedAtMs: 1_700_000_000_000,
                         observationRef: "fixture-desk"),
            LensSighting(id: "sight-newer", targetID: targetID,
                         zone: "Hallway shelf", observedAtMs: 1_700_000_060_000,
                         observationRef: "fixture-shelf"),
        ]).history(for: targetID)
    }

    public static func sampleDraft(generation: Int = 4) -> LensFrameDraft {
        LensFrameDraft(
            observationID: "fixture-lookalike-frame", sessionID: "fixture-session",
            generation: generation, receivedAtMs: 1_700_000_061_000,
            source: .fixture, frameSHA256: String(repeating: "a", count: 64),
            width: 720, height: 1280,
            candidates: [
                .init(id: "charger-a", label: "65W USB-C charger", confidence: 0.87),
                .init(id: "charger-b", label: "65W USB-C charger", confidence: 0.84),
            ]
        )
    }
}
