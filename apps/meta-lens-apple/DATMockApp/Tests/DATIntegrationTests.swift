import XCTest
@testable import ChibiDATMock

@MainActor
final class DATIntegrationTests: XCTestCase {
    private var activeModel: DATCaptureModel?

    override func tearDown() async throws {
        activeModel?.stop()
        if let model = activeModel { try await eventually({ !model.cleaning }) }
        activeModel = nil
        try await super.tearDown()
    }

    private func eventually(_ predicate: @escaping @MainActor () -> Bool, seconds: Double = 25) async throws {
        let deadline = Date().addingTimeInterval(seconds)
        while !predicate(), Date() < deadline { try await Task.sleep(for: .milliseconds(100)) }
        guard predicate() else {
            XCTFail("Condition not met within \(seconds)s")
            throw NSError(domain: "DATIntegrationTest", code: 1)
        }
    }

    func testRealSDKVideoFramesOCRRevocationAndDisconnect() async throws {
        let model = DATCaptureModel()
        activeModel = model
        XCTAssertTrue(model.configured, model.lastError ?? "configuration failed")
        let video = try XCTUnwrap(Bundle.main.url(forResource: "charger-label", withExtension: "mp4"))
        model.start(video: video, consent: false, bystanderClearance: true)
        XCTAssertFalse(model.running)
        XCTAssertNil(model.preview)
        // A revoke before the queued startup runs must never enable the SDK.
        try model.importAndStart(video, consent: true, bystanderClearance: true)
        XCTAssertTrue(model.hasImportedVideo)
        model.revoke()
        try await Task.sleep(for: .milliseconds(200))
        XCTAssertFalse(model.isMockKitEnabled)
        XCTAssertFalse(model.hasImportedVideo)
        XCTAssertFalse(model.running)
        model.start(video: video, consent: true, bystanderClearance: true)
        try await eventually({ model.frameCount > 0 && model.recognizedText.contains("CHARGER") })
        XCTAssertNotNil(model.lastTimestamp)
        XCTAssertEqual(model.frameDigest.count, 64)
        model.revoke()
        let stoppedCount = model.frameCount
        XCTAssertNil(model.preview)
        XCTAssertEqual(model.recognizedText, "")
        try await eventually({ !model.cleaning })
        try await Task.sleep(for: .milliseconds(800))
        XCTAssertEqual(model.frameCount, stoppedCount, "Late frames must be fenced")
        XCTAssertFalse(model.running)
        model.start(video: video, consent: true, bystanderClearance: true)
        try await eventually({ model.frameCount > 0 })
        model.simulateSDKPermissionRevocation()
        try await eventually({ !model.running })
        XCTAssertNil(model.preview)
        XCTAssertEqual(model.recognizedText, "")
        try await eventually({ !model.cleaning })
        model.start(video: video, consent: true, bystanderClearance: true)
        try await eventually({ model.frameCount > 0 })
        model.simulateDisconnect()
        try await eventually({ !model.running })
        XCTAssertNil(model.preview)
        XCTAssertEqual(model.recognizedText, "")
        try await eventually({ !model.cleaning })
    }
}
