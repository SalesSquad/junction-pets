import Foundation
import ChibiLensCore

struct ReplayReceipt: Codable {
    let receiptKind: String
    let source: String
    let gateAccepted: Bool
    let latestZone: String
    let candidateVerdict: String
    let identityVerified: Bool
    let actionAuthorized: Bool
}

@main
enum LensReplayMain {
    static func main() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        if CommandLine.arguments.dropFirst().first == "--contracts" {
            let digest = String(repeating: "f", count: 64)
            let requests = try [
                LensScanRequest.find(requestID: "find-1", sessionID: "fixture-session",
                                     query: "charger").validated(),
                LensScanRequest.inspect(requestID: "inspect-1", sessionID: "fixture-session",
                                        query: "charger", hostObservationRef: "host-fixture",
                                        hostObservationDigest: digest).validated(),
                LensScanRequest.verify(requestID: "verify-1", sessionID: "fixture-session",
                                       query: "charger", targetID: "charger-a",
                                       hostObservationRef: "host-fixture",
                                       hostObservationDigest: digest).validated(),
            ]
            FileHandle.standardOutput.write(try encoder.encode(requests) + Data([0x0a]))
            return
        }
        let gate = CaptureGate(
            consent: .granted, platformPermissionGranted: true,
            bystanderClearance: true, sessionGeneration: 4
        )
        let draft = LensDemoFixture.sampleDraft()
        try LensDraftValidator.check(draft, gate: gate, activeSessionID: "fixture-session")
        let outcome = LensAssessment.assess(draft.candidates)
        let receipt = ReplayReceipt(
            receiptKind: "SYNTHETIC", source: draft.provenance,
            gateAccepted: gate.canPreview,
            latestZone: LensDemoFixture.history.first?.zone ?? "unknown",
            candidateVerdict: outcome.verdict.rawValue,
            identityVerified: outcome.identityVerified,
            actionAuthorized: outcome.actionAuthorized
        )
        let data = try encoder.encode(receipt)
        FileHandle.standardOutput.write(data + Data([0x0a]))
    }
}
