import XCTest
@testable import ChibiLensCore

final class CaptureEpochTests: XCTestCase {
    func testConsentAndBystanderClearanceAreBothRequired() {
        var epoch = CaptureEpoch()
        XCTAssertNil(epoch.begin(consent: false, bystanderClearance: true))
        XCTAssertNil(epoch.begin(consent: true, bystanderClearance: false))
        XCTAssertFalse(epoch.isActive)
    }

    func testRevocationRejectsInFlightWorkAndRestartRejectsOldResults() throws {
        var epoch = CaptureEpoch()
        let old = try XCTUnwrap(epoch.begin(consent: true, bystanderClearance: true))
        XCTAssertTrue(epoch.accepts(old))
        epoch.invalidate()
        XCTAssertFalse(epoch.accepts(old))
        let fresh = try XCTUnwrap(epoch.begin(consent: true, bystanderClearance: true))
        XCTAssertNotEqual(old, fresh)
        XCTAssertFalse(epoch.accepts(old))
        XCTAssertTrue(epoch.accepts(fresh))
    }
}
