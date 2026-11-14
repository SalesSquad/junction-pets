import Foundation
import XCTest
@testable import ChibiLensCore

final class EvidenceTests: XCTestCase {
    private let allowed = CaptureGate(
        consent: .granted, platformPermissionGranted: true,
        bystanderClearance: true, sessionGeneration: 4
    )

    func testValidReplayDraftRemainsClientUnverified() throws {
        let draft = LensDemoFixture.sampleDraft()
        try LensDraftValidator.check(draft, gate: allowed, activeSessionID: "fixture-session")
        XCTAssertEqual(draft.provenance, "client-unverified")
    }

    func testAllPermissionDimensionsRequired() {
        for gate in [
            CaptureGate(consent: .unknown, platformPermissionGranted: true,
                        bystanderClearance: true, sessionGeneration: 4),
            CaptureGate(consent: .revoked, platformPermissionGranted: true,
                        bystanderClearance: true, sessionGeneration: 4),
            CaptureGate(consent: .granted, platformPermissionGranted: false,
                        bystanderClearance: true, sessionGeneration: 4),
            CaptureGate(consent: .granted, platformPermissionGranted: true,
                        bystanderClearance: false, sessionGeneration: 4),
            CaptureGate(consent: .granted, platformPermissionGranted: true,
                        bystanderClearance: true, sessionGeneration: 0),
        ] {
            XCTAssertFalse(gate.canPreview)
            XCTAssertThrowsError(try LensDraftValidator.check(
                LensDemoFixture.sampleDraft(), gate: gate,
                activeSessionID: "fixture-session"
            )) { XCTAssertEqual($0 as? LensAdmissionError, .captureNotAllowed) }
        }
    }

    func testStaleGenerationAndSessionFail() {
        XCTAssertThrowsError(try LensDraftValidator.check(
            LensDemoFixture.sampleDraft(generation: 3), gate: allowed,
            activeSessionID: "fixture-session"
        )) { XCTAssertEqual($0 as? LensAdmissionError, .staleSession) }
        XCTAssertThrowsError(try LensDraftValidator.check(
            LensDemoFixture.sampleDraft(), gate: allowed, activeSessionID: "other"
        )) { XCTAssertEqual($0 as? LensAdmissionError, .staleSession) }
    }

    func testEmptySessionIdentifiersAreRejected() {
        let source = LensDemoFixture.sampleDraft()
        let empty = LensFrameDraft(
            observationID: source.observationID, sessionID: "",
            generation: source.generation, receivedAtMs: source.receivedAtMs,
            source: source.source, frameSHA256: source.frameSHA256,
            width: source.width, height: source.height, candidates: source.candidates
        )
        XCTAssertThrowsError(try LensDraftValidator.check(
            empty, gate: allowed, activeSessionID: ""
        )) { XCTAssertEqual($0 as? LensAdmissionError, .invalidDraft) }
    }

    func testInvalidFrameDigestCannotBeAdmitted() {
        let original = LensDemoFixture.sampleDraft()
        let bad = LensFrameDraft(
            observationID: original.observationID, sessionID: original.sessionID,
            generation: original.generation, receivedAtMs: original.receivedAtMs,
            source: original.source, frameSHA256: "not-a-sha256",
            width: original.width, height: original.height,
            candidates: original.candidates
        )
        XCTAssertThrowsError(try LensDraftValidator.check(
            bad, gate: allowed, activeSessionID: "fixture-session"
        )) { XCTAssertEqual($0 as? LensAdmissionError, .invalidDraft) }
    }

    func testAmbiguousLookalikesAreNeverVerified() {
        let outcome = LensAssessment.assess(LensDemoFixture.sampleDraft().candidates)
        XCTAssertEqual(outcome.verdict, .ambiguous)
        XCTAssertNil(outcome.suggestedID)
        XCTAssertFalse(outcome.identityVerified)
        XCTAssertFalse(outcome.actionAuthorized)
    }

    func testStrongCandidateStillNotIdentityProof() {
        let outcome = LensAssessment.assess([
            .init(id: "tagged-item", label: "Charger", confidence: 0.99),
        ])
        XCTAssertEqual(outcome.verdict, .possibleMatch)
        XCTAssertFalse(outcome.identityVerified)
        XCTAssertFalse(outcome.actionAuthorized)
    }

    func testHistoryIsNewestFirstButNotLivePresence() {
        let history = LensDemoFixture.history
        XCTAssertEqual(history.map(\.zone), ["Hallway shelf", "Desk"])
        XCTAssertEqual(history.map(\.id), ["sight-newer", "sight-older"])
    }

    func testRequestMatchesExistingJSContract() throws {
        let find = try LensScanRequest.find(
            requestID: "find-1", sessionID: "s-1", query: "charger"
        ).validated()
        let findObject = try XCTUnwrap(JSONSerialization.jsonObject(
            with: JSONEncoder().encode(find)) as? [String: Any])
        XCTAssertEqual(findObject["schemaVersion"] as? Int, 1)
        XCTAssertEqual(findObject["mode"] as? String, "find")
        XCTAssertNil(findObject["observationRef"])
        XCTAssertNil(findObject["targetId"])

        let inspect = try LensScanRequest.inspect(
            requestID: "inspect-1", sessionID: "s-1", query: "charger",
            hostObservationRef: "host-ref",
            hostObservationDigest: String(repeating: "a", count: 64)
        ).validated()
        let inspectObject = try XCTUnwrap(JSONSerialization.jsonObject(
            with: JSONEncoder().encode(inspect)) as? [String: Any])
        XCTAssertEqual(inspectObject["mode"] as? String, "inspect")
        XCTAssertNil(inspectObject["targetId"])

        let verify = try LensScanRequest.verify(
            requestID: "verify-1", sessionID: "s-1", query: "charger",
            targetID: "charger-a", hostObservationRef: "host-ref",
            hostObservationDigest: String(repeating: "f", count: 64)
        ).validated()
        let verifyObject = try XCTUnwrap(JSONSerialization.jsonObject(
            with: JSONEncoder().encode(verify)) as? [String: Any])
        XCTAssertEqual(verifyObject["mode"] as? String, "verify")
        XCTAssertEqual(verifyObject["targetId"] as? String, "charger-a")
        XCTAssertEqual(verifyObject["observationRef"] as? String, "host-ref")
    }

    func testSourcePortPreflightRejectsInvalidStringsAndDigest() {
        XCTAssertThrowsError(try LensScanRequest.find(
            requestID: " bad", sessionID: "s-1", query: "charger"
        ).validated())
        XCTAssertThrowsError(try LensScanRequest.find(
            requestID: "ok", sessionID: "s-1", query: String(repeating: "a", count: 401)
        ).validated())
        XCTAssertThrowsError(try LensScanRequest.inspect(
            requestID: "ok", sessionID: "s-1", query: "charger",
            hostObservationRef: "host-ref", hostObservationDigest: String(repeating: "A", count: 64)
        ).validated())
        XCTAssertThrowsError(try LensScanRequest.verify(
            requestID: "ok", sessionID: "s-1", query: "charger",
            targetID: "", hostObservationRef: "host-ref",
            hostObservationDigest: String(repeating: "a", count: 64)
        ).validated())
        XCTAssertThrowsError(try LensScanRequest.find(
            requestID: "ok", sessionID: "s-1", query: "charger\u{FEFF}"
        ).validated())
        XCTAssertNoThrow(try LensScanRequest.find(
            requestID: "ok", sessionID: "s-1", query: "charger\u{0085}"
        ).validated())
    }
}
