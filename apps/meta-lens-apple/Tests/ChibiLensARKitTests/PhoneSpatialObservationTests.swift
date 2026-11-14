import ChibiLensARKit
import ChibiLensCore
import Foundation
import ImageIO
import UniformTypeIdentifiers
import XCTest

final class PhoneSpatialObservationTests: XCTestCase {
    private let bytes = syntheticJPEG() // Generated pixels, not camera evidence.
    private let pose: [Double] = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 2, 3, 4, 1]
    private let intrinsics: [Double] = [100, 0, 0, 0, 100, 0, 50, 40, 1]
    private let capabilities = PhoneSpatialObservation.Capabilities(
        sceneDepth: false, smoothedSceneDepth: false, mesh: false, classifiedMesh: false)

    private func observation(source: LensSourceKind = .phoneCamera, digest: String? = nil,
                             pose: [Double]? = nil, intrinsics: [Double]? = nil,
                             timestamp: Double = 17, generation: Int = 3,
                             jpeg: Data? = nil) throws -> PhoneSpatialObservation {
        let bytes = jpeg ?? self.bytes
        let frame = LensFrameDraft(observationID: "frame-1", sessionID: "phone-1", generation: generation,
            receivedAtMs: 1234, source: source, frameSHA256: digest ?? PhoneSpatialObservation.digest(bytes),
            width: 100, height: 80, candidates: [])
        return try PhoneSpatialObservation(frame: frame, jpeg: bytes, worldID: "world-1", worldGeneration: 3,
            capturedAtARSeconds: timestamp, cameraToWorld: pose ?? self.pose,
            intrinsics: intrinsics ?? self.intrinsics, mappingStatus: .extending, capabilities: capabilities)
    }

    func testPhoneObservationRetainsUntrustedSameImageGeometryAndClock() throws {
        let value = try observation()
        try value.validate(gate: CaptureGate(consent: .granted, platformPermissionGranted: true,
            bystanderClearance: true, sessionGeneration: 3), activeSessionID: "phone-1", activeWorldID: "world-1")
        XCTAssertEqual(value.cameraToWorld, pose)
        XCTAssertEqual(value.frame.source, .phoneCamera)
        XCTAssertEqual(value.captureClockDomain, "arkit-session:world-1")
        XCTAssertEqual(value.encodedEXIFOrientation, 1)
        XCTAssertEqual(value.provenance, "client-unverified")
        XCTAssertEqual(value.registration, "unregistered")
        XCTAssertFalse(value.identityVerified)
        XCTAssertFalse(value.actionAuthorized)
        XCTAssertFalse(value.capabilities.sceneDepth)
    }

    func testRejectsGlassesSourceAndDifferentImageDigest() {
        XCTAssertThrowsError(try observation(source: .metaCamera))
        XCTAssertThrowsError(try observation(digest: String(repeating: "a", count: 64)))
    }

    func testRejectsUndecodableResizedAndRotatedJPEG() {
        XCTAssertThrowsError(try observation(jpeg: Data([0xff, 0xd8, 0xff, 0xd9])))
        XCTAssertThrowsError(try observation(jpeg: syntheticJPEG(width: 80, height: 100)))
        XCTAssertThrowsError(try observation(jpeg: syntheticJPEG(orientation: 6)))
    }

    func testRejectsNonRigidReflectedAndNonFiniteTransforms() {
        var scaled = pose; scaled[0] = 2
        var reflected = pose; reflected[0] = -1
        var infinite = pose; infinite[12] = .infinity
        for value in [scaled, reflected, infinite, []] { XCTAssertThrowsError(try observation(pose: value)) }
    }

    func testRejectsInvalidIntrinsicsAndCaptureTime() {
        var wrongFocalLength = intrinsics; wrongFocalLength[0] = 0
        var wrongPrincipalPoint = intrinsics; wrongPrincipalPoint[6] = 101
        XCTAssertThrowsError(try observation(intrinsics: wrongFocalLength))
        XCTAssertThrowsError(try observation(intrinsics: wrongPrincipalPoint))
        XCTAssertThrowsError(try observation(timestamp: .nan))
        XCTAssertThrowsError(try observation(timestamp: -1))
    }

    func testRejectsWorldAndCaptureGenerationMismatch() throws {
        XCTAssertThrowsError(try observation(generation: 2))
        let value = try observation()
        XCTAssertThrowsError(try value.validate(gate: CaptureGate(consent: .granted,
            platformPermissionGranted: true, bystanderClearance: true, sessionGeneration: 3),
            activeSessionID: "phone-1", activeWorldID: "new-world"))
        XCTAssertThrowsError(try value.validate(gate: CaptureGate(consent: .granted,
            platformPermissionGranted: true, bystanderClearance: true, sessionGeneration: 4),
            activeSessionID: "phone-1", activeWorldID: "world-1"))
    }

    func testRechecksRevocationPermissionAndClearanceAtConsumption() throws {
        let value = try observation()
        let gates = [
            CaptureGate(consent: .revoked, platformPermissionGranted: true, bystanderClearance: true, sessionGeneration: 3),
            CaptureGate(consent: .granted, platformPermissionGranted: false, bystanderClearance: true, sessionGeneration: 3),
            CaptureGate(consent: .granted, platformPermissionGranted: true, bystanderClearance: false, sessionGeneration: 3),
        ]
        for gate in gates {
            XCTAssertThrowsError(try value.validate(gate: gate, activeSessionID: "phone-1", activeWorldID: "world-1"))
        }
    }
}

private func syntheticJPEG(width: Int = 100, height: Int = 80, orientation: Int = 1) -> Data {
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8,
        bytesPerRow: width * 4, space: colorSpace, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    context.setFillColor(CGColor(red: 0.1, green: 0.4, blue: 0.8, alpha: 1))
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    let data = NSMutableData()
    let destination = CGImageDestinationCreateWithData(data, UTType.jpeg.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(destination, context.makeImage()!, [kCGImagePropertyOrientation: orientation] as CFDictionary)
    precondition(CGImageDestinationFinalize(destination))
    return data as Data
}
