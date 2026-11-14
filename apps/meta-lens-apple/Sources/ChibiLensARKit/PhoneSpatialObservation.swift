import ChibiLensCore
import CryptoKit
import Foundation
import ImageIO
import UniformTypeIdentifiers

/// A phone-camera estimate in one ARKit session, never a Meta-camera pose or host receipt.
public struct PhoneSpatialObservation: Sendable {
    public enum MappingStatus: String, Sendable {
        case notAvailable, limited, extending, mapped
    }

    public struct Capabilities: Sendable, Equatable {
        public let sceneDepth: Bool
        public let smoothedSceneDepth: Bool
        public let mesh: Bool
        public let classifiedMesh: Bool

        public init(sceneDepth: Bool, smoothedSceneDepth: Bool, mesh: Bool, classifiedMesh: Bool) {
            self.sceneDepth = sceneDepth
            self.smoothedSceneDepth = smoothedSceneDepth
            self.mesh = mesh
            self.classifiedMesh = classifiedMesh
        }
    }

    public enum ValidationError: Error, Equatable {
        case invalidFrameBinding, invalidPose, invalidIntrinsics, staleWorld
    }

    public let frame: LensFrameDraft
    public let jpeg: Data
    public let worldID: String
    public let worldGeneration: Int
    /// ARFrame.timestamp. The epoch is deliberately not converted to UTC or Meta PTS.
    public let capturedAtARSeconds: Double
    /// Column-major 4x4, metres, right-handed ARKit camera-to-session-world transform.
    public let cameraToWorld: [Double]
    /// Column-major 3x3 for the unrotated captured-image pixels in `frame`.
    public let intrinsics: [Double]
    public let mappingStatus: MappingStatus
    public let capabilities: Capabilities

    public var provenance: String { "client-unverified" }
    public var registration: String { "unregistered" }
    public var poseSource: String { "phone-arkit" }
    public var captureClockDomain: String { "arkit-session:\(worldID)" }
    public var receiptClockDomain: String { "client-wall-clock-unverified" }
    public var imageCoordinates: String { "arkit-native-captured-image-unrotated" }
    public var encodedEXIFOrientation: Int { 1 }
    public var trackingState: String { "normal" }
    public var identityVerified: Bool { false }
    public var actionAuthorized: Bool { false }

    /// The producer must copy image and geometry from the same ARFrame. Validation
    /// checks internal consistency only; it cannot attest a camera or physical scene.
    public init(
        frame: LensFrameDraft, jpeg: Data, worldID: String, worldGeneration: Int,
        capturedAtARSeconds: Double, cameraToWorld: [Double], intrinsics: [Double],
        mappingStatus: MappingStatus, capabilities: Capabilities
    ) throws {
        guard frame.source == .phoneCamera, worldGeneration > 0,
              frame.generation == worldGeneration, !worldID.isEmpty, worldID.utf8.count <= 160,
              capturedAtARSeconds.isFinite, capturedAtARSeconds >= 0,
              !jpeg.isEmpty, jpeg.count <= 4_000_000,
              (1...4096).contains(frame.width), (1...4096).contains(frame.height),
              frame.width * frame.height <= 8_388_608,
              frame.frameSHA256 == Self.digest(jpeg),
              Self.validJPEG(jpeg, width: frame.width, height: frame.height) else {
            throw ValidationError.invalidFrameBinding
        }
        guard Self.isRigidTransform(cameraToWorld) else { throw ValidationError.invalidPose }
        guard Self.validIntrinsics(intrinsics, width: frame.width, height: frame.height) else {
            throw ValidationError.invalidIntrinsics
        }
        self.frame = frame
        self.jpeg = jpeg
        self.worldID = worldID
        self.worldGeneration = worldGeneration
        self.capturedAtARSeconds = capturedAtARSeconds
        self.cameraToWorld = cameraToWorld
        self.intrinsics = intrinsics
        self.mappingStatus = mappingStatus
        self.capabilities = capabilities
    }

    /// Checks against supplied current state only. Runtime consumers must call
    /// PhoneSpatialCapture.validateCurrent instead of retaining an old gate.
    public func validate(gate: CaptureGate, activeSessionID: String, activeWorldID: String) throws {
        try LensDraftValidator.check(frame, gate: gate, activeSessionID: activeSessionID)
        guard worldID == activeWorldID, worldGeneration == gate.sessionGeneration else {
            throw ValidationError.staleWorld
        }
    }

    public static func digest(_ bytes: Data) -> String {
        SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
    }

    private static func validJPEG(_ data: Data, width: Int, height: Int) -> Bool {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              CGImageSourceGetCount(source) == 1,
              CGImageSourceGetType(source) as String? == UTType.jpeg.identifier,
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              (properties[kCGImagePropertyPixelWidth] as? NSNumber)?.intValue == width,
              (properties[kCGImagePropertyPixelHeight] as? NSNumber)?.intValue == height,
              ((properties[kCGImagePropertyOrientation] as? NSNumber)?.intValue ?? 1) == 1,
              CGImageSourceGetStatus(source) == .statusComplete,
              let image = CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCache: false] as CFDictionary)
        else { return false }
        return image.width == width && image.height == height
    }

    private static func validIntrinsics(_ k: [Double], width: Int, height: Int) -> Bool {
        guard k.count == 9, k.allSatisfy(\.isFinite), k[0] > 0, k[4] > 0,
              abs(k[1]) < 1e-6, abs(k[2]) < 1e-6, abs(k[3]) < 1e-6,
              abs(k[5]) < 1e-6, abs(k[8] - 1) < 1e-6 else { return false }
        return (0...Double(width)).contains(k[6]) && (0...Double(height)).contains(k[7])
    }

    private static func isRigidTransform(_ m: [Double]) -> Bool {
        guard m.count == 16, m.allSatisfy(\.isFinite), abs(m[3]) < 1e-5,
              abs(m[7]) < 1e-5, abs(m[11]) < 1e-5, abs(m[15] - 1) < 1e-5 else { return false }
        let a = Array(m[0...2]), b = Array(m[4...6]), c = Array(m[8...10])
        func dot(_ x: [Double], _ y: [Double]) -> Double { zip(x, y).reduce(0) { $0 + $1.0 * $1.1 } }
        guard [a, b, c].allSatisfy({ abs(dot($0, $0) - 1) < 0.002 }),
              abs(dot(a, b)) < 0.002, abs(dot(a, c)) < 0.002, abs(dot(b, c)) < 0.002 else { return false }
        let determinant = a[0] * (b[1] * c[2] - b[2] * c[1])
            - b[0] * (a[1] * c[2] - a[2] * c[1])
            + c[0] * (a[1] * b[2] - a[2] * b[1])
        return abs(determinant - 1) < 0.002
    }
}
