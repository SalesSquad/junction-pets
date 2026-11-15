import Foundation
import XCTest
@testable import TrustCore

final class TrustCoreTests: XCTestCase {
    private var directory: URL!
    private let base = String(repeating: "a", count: 40)
    private let head = String(repeating: "b", count: 40)
    private let harness = String(repeating: "c", count: 64)

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent("earned-trust-tests-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try Data("synthetic unit-test base observation\n".utf8).write(to: directory.appendingPathComponent("base.log"))
        try Data("synthetic unit-test head observation\n".utf8).write(to: directory.appendingPathComponent("head.log"))
    }

    override func tearDownWithError() throws {
        if let directory { try FileManager.default.removeItem(at: directory) }
    }

    func testObservedFrozenFailPassIsReady() throws {
        let loaded = try load(packet())
        XCTAssertEqual(loaded.verdict, .ready)
        XCTAssertEqual(loaded.verifiedLogPairs, 1)
    }

    func testPassPassDoesNotProveFixButCanProveInvariant() throws {
        var value = try packet()
        var checks = value["checks"] as! [[String: Any]]
        checks[0]["baseOutcome"] = "pass"
        value["checks"] = checks
        XCTAssertEqual(try load(value).verdict, .needsEvidence)
        checks[0]["kind"] = "regression"
        var claims = value["claims"] as! [[String: Any]]
        claims[0]["kind"] = "invariant"
        value["checks"] = checks; value["claims"] = claims
        XCTAssertEqual(try load(value).verdict, .ready)
    }

    func testPassingRegressionCanSupportARealFix() throws {
        var value = try packet()
        var checks = value["checks"] as! [[String: Any]]
        var regression = checks[0]
        regression["id"] = "stable"; regression["kind"] = "regression"; regression["baseOutcome"] = "pass"
        checks.append(regression)
        var claims = value["claims"] as! [[String: Any]]
        claims[0]["checkIds"] = ["repro", "stable"]
        value["checks"] = checks; value["claims"] = claims
        XCTAssertEqual(try load(value).verdict, .ready)
    }

    func testStaleSourceDifferentHarnessAndSyntheticEvidenceRefuse() throws {
        for (field, replacement) in [("headSourceSha", String(repeating: "d", count: 40)),
                                     ("headHarnessSha256", String(repeating: "d", count: 64)),
                                     ("evidence", "synthetic"), ("baseOutcome", "error")] {
            var value = try packet()
            var checks = value["checks"] as! [[String: Any]]
            checks[0][field] = replacement; value["checks"] = checks
            XCTAssertEqual(try load(value).verdict, .needsEvidence, field)
        }
    }

    func testContradictoryAttachedCheckBlocksReadiness() throws {
        var value = try packet()
        var checks = value["checks"] as! [[String: Any]]
        var contradiction = checks[0]
        contradiction["id"] = "contradiction"; contradiction["headOutcome"] = "fail"
        checks.append(contradiction)
        var claims = value["claims"] as! [[String: Any]]
        claims[0]["checkIds"] = ["repro", "contradiction"]
        value["checks"] = checks; value["claims"] = claims
        XCTAssertEqual(try load(value).verdict, .needsEvidence)
    }

    func testChangedLogInvalidatesVerdictPreviewAndDecision() throws {
        let loaded = try load(packet())
        try Data("changed after load".utf8).write(to: directory.appendingPathComponent("head.log"))
        XCTAssertEqual(try PacketLoader.load(url: loaded.url).verdict, .needsEvidence)
        XCTAssertThrowsError(try PacketLoader.evidenceText(packet: loaded, check: loaded.packet.checks[0], head: true))
        XCTAssertThrowsError(try ReviewDecision.record(packet: loaded, reviewer: "Synthetic Reviewer", decision: .accept, rationale: "Unit-test fixture"))
    }

    func testDecisionBindsExactPacketAndHasNoAuthority() throws {
        let loaded = try load(packet())
        let record = try ReviewDecision.record(packet: loaded, reviewer: "Synthetic Reviewer", decision: .accept, rationale: "Unit-test fixture")
        XCTAssertEqual(record.packetSHA256, loaded.sha256)
        XCTAssertFalse(record.reviewerAuthenticated)
        XCTAssertFalse(record.codeChangeApproved)
        XCTAssertFalse(record.remoteWritePerformed)
        var value = try packet(); value["title"] = "Changed title"
        _ = try load(value)
        XCTAssertThrowsError(try ReviewDecision.record(packet: loaded, reviewer: "Synthetic Reviewer", decision: .accept, rationale: "Stale packet"))
    }

    func testTraversalAbsoluteAndSymlinkEvidenceAreRejected() throws {
        for path in ["../outside.log", "/tmp/outside.log", "logs/../../outside", "logs//head.log", "logs\\head.log"] {
            XCTAssertThrowsError(try PacketLoader.safeEvidenceURL(path, directory: directory))
        }
        let link = directory.appendingPathComponent("linked.log")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: directory.appendingPathComponent("head.log"))
        XCTAssertThrowsError(try PacketLoader.safeEvidenceURL("linked.log", directory: directory))
    }

    func testMalformedContractAndDuplicateIDsAreRejected() throws {
        var value = try packet(); value["unexpectedAuthority"] = true
        XCTAssertThrowsError(try load(value))
        value = try packet()
        var checks = value["checks"] as! [[String: Any]]
        checks[0]["evidence"] = "trusted"; value["checks"] = checks
        XCTAssertThrowsError(try load(value))
        value = try packet(); checks = value["checks"] as! [[String: Any]]
        checks.append(checks[0]); value["checks"] = checks
        XCTAssertThrowsError(try load(value))
        value = try packet()
        var claims = value["claims"] as! [[String: Any]]
        claims[0]["checkIds"] = ["absent"]; value["claims"] = claims
        XCTAssertThrowsError(try load(value))
    }

    func testStructuralClaimCannotBecomeBehavioralAcceptance() throws {
        var value = try packet()
        var claims = value["claims"] as! [[String: Any]]
        claims[0]["kind"] = "structural"; value["claims"] = claims
        let loaded = try load(value)
        XCTAssertEqual(loaded.verdict, .inspectionOnly)
        XCTAssertThrowsError(try ReviewDecision.record(packet: loaded, reviewer: "Synthetic Reviewer", decision: .accept, rationale: "No behavior evidence"))
    }

    func testStructuralContextDoesNotDowngradeAnEvidencedBehavioralClaim() throws {
        var value = try packet()
        var claims = value["claims"] as! [[String: Any]]
        var structural = claims[0]
        structural["id"] = "change-map"; structural["kind"] = "structural"
        claims.append(structural); value["claims"] = claims
        let loaded = try load(value)
        XCTAssertEqual(loaded.verdict, .ready)
        XCTAssertEqual(loaded.assessments.last?.verdict, .inspectionOnly)
    }

    private func load(_ value: [String: Any]) throws -> LoadedPacket {
        let url = directory.appendingPathComponent("packet.json")
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]).write(to: url)
        return try PacketLoader.load(url: url)
    }

    private func packet() throws -> [String: Any] {
        let baseDigest = PacketLoader.digest(try Data(contentsOf: directory.appendingPathComponent("base.log")))
        let headDigest = PacketLoader.digest(try Data(contentsOf: directory.appendingPathComponent("head.log")))
        let check: [String: Any] = [
            "id": "repro", "title": "Synthetic unit-test observation", "requirementId": "TEST-1",
            "kind": "differential", "evidence": "observed", "baseOutcome": "fail", "headOutcome": "pass",
            "baseSourceSha": base, "headSourceSha": head, "baseHarnessSha256": harness, "headHarnessSha256": harness,
            "baseLog": "base.log", "headLog": "head.log", "baseLogSha256": baseDigest, "headLogSha256": headDigest,
            "limitations": ["Unit-test fixtures are invented and never shipped as real execution evidence."]
        ]
        return [
            "schemaVersion": 1, "packetId": "synthetic-test", "title": "Synthetic unit-test packet", "generatedAt": "2026-11-15T00:00:00Z",
            "source": ["repository": "https://github.com/example/public-test", "baseSha": base, "headSha": head,
                       "issueId": "1", "issueURL": "https://github.com/example/public-test/issues/1", "branch": "test"],
            "requirement": ["id": "TEST-1", "summary": "Synthetic requirement", "details": "Used only for local unit tests."],
            "checks": [check],
            "claims": [["id": "claim", "title": "Synthetic fix", "requirementId": "TEST-1", "kind": "fix", "checkIds": ["repro"], "paths": ["src/Test.cs"]]],
            "files": [["path": "src/Test.cs", "role": "source", "additions": 1, "deletions": 1, "group": "Unit test"]],
            "provenance": ["toolchain": "Unit test", "origin": "synthetic-unit-test", "note": "Invented internal fixture; no real run is claimed."],
            "limitations": ["Synthetic unit-test input."]
        ]
    }
}
