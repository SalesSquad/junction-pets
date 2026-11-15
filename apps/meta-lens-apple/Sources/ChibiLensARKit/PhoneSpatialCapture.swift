#if os(iOS) && canImport(ARKit)
import ARKit
import AVFoundation
import ChibiLensCore
import CoreImage
import Foundation
import ImageIO
import SceneKit
import simd
import UIKit
import UniformTypeIdentifiers

/// Explicitly started phone capture. The embedding app owns permission UI and
/// NSCameraUsageDescription; this type never requests permission or starts itself.
///
///     let capture = PhoneSpatialCapture()
///     capture.onObservation = { phoneFrame in /* local preview / host proposal */ }
///     try capture.start(sessionID: "phone-session", consent: .granted, bystanderClearance: true)
///     // After any async analysis: try capture.validateCurrent(phoneFrame)
///     capture.stop() // also call when consent, clearance or the view's lifetime ends
///
/// Permission must already be authorized by the OS. No depth/mesh feature is
/// enabled here: capability flags describe support, not captured depth or a map.
@MainActor
public final class PhoneSpatialCapture {
    public enum StartError: Error { case unsupported, captureNotAllowed, cameraPermissionRequired, missingUsageDescription }
    public enum State: String { case stopped, waitingForTracking, tracking }

    public private(set) var state: State = .stopped
    public private(set) var latest: PhoneSpatialObservation?
    public private(set) var stopReason: String?
    public var onObservation: ((PhoneSpatialObservation) -> Void)?
    public var onStateChanged: ((State, String?) -> Void)?
    private weak var preview: ARSCNView?

    /// A watermark from ARKit's current frame (including frames not yet encoded).
    /// It is never converted to a wall clock or to a glasses-camera timestamp.
    public var currentFrameTimestamp: Double? {
        guard epoch.isActive, lifetime?.delegate.isTracking == true,
              UIApplication.shared.applicationState == .active,
              AVCaptureDevice.authorizationStatus(for: .video) == .authorized else { return nil }
        return lifetime?.session.currentFrame?.timestamp
    }

    public struct SurfaceMarker: Sendable {
        public let id: String
        public let worldID: String
        public let measuredAtARSeconds: Double
        public let cameraToWorld: [Double]
        public let surfaceToWorld: [Double]
        public var registration: String { "phone-surface-estimate-unregistered" }
        public var physicalIdentityVerified: Bool { false }
    }

    private var epoch = CaptureEpoch()
    private var lifetime: PhoneCaptureLifetime?
    private var activeSessionID = ""
    private var worldID = ""
    private var clearance = false

    public init() {}

    public func start(sessionID: String, consent: CaptureConsent, bystanderClearance: Bool) throws {
        stop()
        guard ARWorldTrackingConfiguration.isSupported else { throw StartError.unsupported }
        guard consent == .granted, bystanderClearance, !sessionID.isEmpty,
              sessionID.utf16.count <= 160, UIApplication.shared.applicationState == .active else {
            throw StartError.captureNotAllowed
        }
        guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
            throw StartError.cameraPermissionRequired
        }
        guard let description = Bundle.main.object(forInfoDictionaryKey: "NSCameraUsageDescription") as? String,
              !description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw StartError.missingUsageDescription
        }
        guard let generation = epoch.begin(consent: true, bystanderClearance: true),
              let generationInt = Int(exactly: generation) else { throw StartError.captureNotAllowed }
        activeSessionID = sessionID
        worldID = UUID().uuidString
        clearance = true
        latest = nil
        stopReason = nil
        state = .waitingForTracking
        let capabilities = PhoneSpatialObservation.Capabilities(
            sceneDepth: ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth),
            smoothedSceneDepth: ARWorldTrackingConfiguration.supportsFrameSemantics(.smoothedSceneDepth),
            mesh: ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh),
            classifiedMesh: ARWorldTrackingConfiguration.supportsSceneReconstruction(.meshWithClassification)
        )
        let receiver = PhoneFrameDelegate(sessionID: sessionID, generation: generationInt,
                                         worldID: worldID, capabilities: capabilities) { [weak self] event in
            Task { @MainActor [weak self] in self?.receive(event, generation: generation) }
        }
        let arSession = ARSession()
        arSession.delegate = receiver
        arSession.delegateQueue = receiver.queue
        let observer = NotificationCenter.default.addObserver(
            forName: UIApplication.willResignActiveNotification, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self, self.epoch.accepts(generation) else { return }
                self.stop(reason: "app-inactive")
            }
        }
        lifetime = PhoneCaptureLifetime(session: arSession, delegate: receiver, observer: observer)
        let configuration = ARWorldTrackingConfiguration()
        configuration.worldAlignment = .gravity
        configuration.planeDetection = [.horizontal, .vertical]
        arSession.run(configuration, options: [.resetTracking, .removeExistingAnchors])
        onStateChanged?(state, nil)
    }

    /// Fences results before stopping ARKit; a later start creates a new world ID.
    public func stop(reason: String = "stopped") {
        epoch.invalidate()
        lifetime?.delegate.invalidate()
        lifetime = nil
        latest = nil
        clearance = false
        activeSessionID = ""
        worldID = ""
        state = .stopped
        stopReason = reason
        clearMarkers()
        onStateChanged?(state, reason)
    }

    /// Render using this capture owner's existing session. The view must not run
    /// or reconfigure the session; there is still exactly one capture delegate.
    public func attachPreview(_ view: ARSCNView) {
        preview = view
        guard let session = lifetime?.session else { return }
        if view.session !== session { view.session = session }
        view.automaticallyUpdatesLighting = true
    }

    public func clearMarkers() {
        preview?.scene.rootNode.childNodes.filter { $0.name == "chibi-guide-surface" }.forEach { $0.removeFromParentNode() }
    }

    /// The point is in the visible ARSCNView viewport, so ARKit handles display
    /// orientation/crop. This measures a surface now, not the selected object's
    /// identity or the location of any pixel in an older JPEG.
    public func placeMarker(at point: CGPoint, in view: ARSCNView,
                            for observation: PhoneSpatialObservation) throws -> SurfaceMarker {
        try validateCurrent(observation)
        guard let session = lifetime?.session, view.session === session,
              point.x.isFinite, point.y.isFinite, view.bounds.contains(point),
              let frame = session.currentFrame, frame.timestamp >= observation.capturedAtARSeconds,
              frame.timestamp - observation.capturedAtARSeconds <= 30,
              let query = view.raycastQuery(from: point, allowing: .estimatedPlane, alignment: .any),
              let result = session.raycast(query).first else { throw PhoneSpatialObservation.ValidationError.staleWorld }
        let position = result.worldTransform.columns.3, camera = frame.camera.transform.columns.3
        let distance = simd_length(SIMD3(position.x-camera.x, position.y-camera.y, position.z-camera.z))
        guard distance.isFinite, distance >= 0.1, distance <= 5 else { throw PhoneSpatialObservation.ValidationError.invalidPose }
        try validateCurrent(observation)
        let marker = SurfaceMarker(id: UUID().uuidString, worldID: observation.worldID,
            measuredAtARSeconds: frame.timestamp,
            cameraToWorld: Self.matrixValues(frame.camera.transform),
            surfaceToWorld: Self.matrixValues(result.worldTransform))
        try showRememberedMarker(marker)
        return marker
    }

    /// Re-show a user's remembered point only in the original live phone world.
    /// A historical surface estimate is never re-localized by string identity.
    public func showRememberedMarker(_ marker: SurfaceMarker) throws {
        guard marker.worldID == worldID, epoch.isActive, lifetime?.delegate.isTracking == true,
              UIApplication.shared.applicationState == .active,
              AVCaptureDevice.authorizationStatus(for: .video) == .authorized,
              let view = preview, let session = lifetime?.session, view.session === session,
              let current = session.currentFrame, current.timestamp >= marker.measuredAtARSeconds,
              marker.surfaceToWorld.count == 16, marker.surfaceToWorld.allSatisfy(\.isFinite) else {
            throw PhoneSpatialObservation.ValidationError.staleWorld
        }
        clearMarkers()
        let node = SCNNode(geometry: SCNSphere(radius: 0.018))
        node.name = "chibi-guide-surface"
        node.geometry?.firstMaterial?.diffuse.contents = UIColor.systemMint
        node.geometry?.firstMaterial?.lightingModel = .constant
        let m = marker.surfaceToWorld.map(Float.init)
        node.simdTransform = simd_float4x4(columns: (
            SIMD4(m[0],m[1],m[2],m[3]), SIMD4(m[4],m[5],m[6],m[7]),
            SIMD4(m[8],m[9],m[10],m[11]), SIMD4(m[12],m[13],m[14],m[15])))
        view.scene.rootNode.addChildNode(node)
    }

    private static func matrixValues(_ matrix: simd_float4x4) -> [Double] {
        (0..<4).flatMap { column in (0..<4).map { row in Double(matrix[column][row]) } }
    }

    /// Consume asynchronous work through the live owner, not a saved CaptureGate.
    /// Tracking loss retires this world, even before its main-actor event arrives.
    public func validateCurrent(_ observation: PhoneSpatialObservation) throws {
        guard epoch.isActive, let delegate = lifetime?.delegate, delegate.isTracking,
              let generation = Int(exactly: epoch.generation),
              UIApplication.shared.applicationState == .active,
              AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
            throw PhoneSpatialObservation.ValidationError.staleWorld
        }
        try observation.validate(gate: CaptureGate(consent: .granted,
            platformPermissionGranted: true, bystanderClearance: clearance,
            sessionGeneration: generation), activeSessionID: activeSessionID, activeWorldID: worldID)
    }

    private func receive(_ event: PhoneFrameDelegate.Event, generation: UInt64) {
        guard epoch.accepts(generation), let delegate = lifetime?.delegate else { return }
        switch event {
        case .stopped(let reason): stop(reason: reason)
        case .frame(let observation, let revision):
            defer { delegate.finishFrame() }
            guard delegate.accepts(revision), UIApplication.shared.applicationState == .active,
                  AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
                latest = nil
                if AVCaptureDevice.authorizationStatus(for: .video) != .authorized {
                    stop(reason: "camera-permission-lost")
                }
                return
            }
            do {
                try validateCurrent(observation)
                guard epoch.accepts(generation), delegate.accepts(revision) else { return }
                latest = observation
                let changed = state != .tracking
                state = .tracking
                if changed { onStateChanged?(state, nil) }
                onObservation?(observation)
            } catch { stop(reason: "invalid-phone-observation") }
        }
    }
}

/// ARC cleanup also stops capture if the embedding view releases its owner.
/// This helper has no actor-isolated state; ARSession uses its own delegate queue.
private final class PhoneCaptureLifetime {
    let session: ARSession
    let delegate: PhoneFrameDelegate
    let observer: NSObjectProtocol
    init(session: ARSession, delegate: PhoneFrameDelegate, observer: NSObjectProtocol) {
        self.session = session
        self.delegate = delegate
        self.observer = observer
    }
    deinit {
        delegate.invalidate()
        session.pause()
        session.delegate = nil
        NotificationCenter.default.removeObserver(observer)
    }
}

/// ARFrame/CVPixelBuffer never cross this serial delegate queue. Only immutable
/// Sendable values leave it. NSLock protects admission against main-actor stop
/// and completion; at most one encoded frame is awaiting publication.
private final class PhoneFrameDelegate: NSObject, ARSessionDelegate, @unchecked Sendable {
    enum Event: Sendable {
        case frame(PhoneSpatialObservation, UInt64)
        case stopped(String)
    }
    let queue = DispatchQueue(label: "chibi.phone-arkit.frames", qos: .userInitiated)
    private let lock = NSLock()
    private var active = true
    private var busy = false
    private var tracking = false
    private var revision: UInt64 = 0
    private var lastAdmission = -Double.infinity
    private let sessionID: String
    private let generation: Int
    private let worldID: String
    private let capabilities: PhoneSpatialObservation.Capabilities
    private let send: @Sendable (Event) -> Void
    private let context = CIContext(options: [.cacheIntermediates: false])

    init(sessionID: String, generation: Int, worldID: String,
         capabilities: PhoneSpatialObservation.Capabilities, send: @escaping @Sendable (Event) -> Void) {
        self.sessionID = sessionID
        self.generation = generation
        self.worldID = worldID
        self.capabilities = capabilities
        self.send = send
    }

    func invalidate() { lock.withLock { active = false; revision &+= 1 } }
    func finishFrame() { lock.withLock { busy = false } }
    func accepts(_ value: UInt64) -> Bool { lock.withLock { active && tracking && revision == value } }
    var isTracking: Bool { lock.withLock { active && tracking } }

    private func setTracking(_ normal: Bool) {
        let lost = lock.withLock {
            guard active, tracking != normal else { return false }
            tracking = normal
            revision &+= 1
            // Initial .limited waits. Losing an established pose retires the
            // entire world; recovery requires an explicit new start/session.
            if !normal { active = false }
            return !normal
        }
        if lost { send(.stopped("tracking-lost")) }
    }

    func session(_ session: ARSession, cameraDidChangeTrackingState camera: ARCamera) {
        if case .normal = camera.trackingState { setTracking(true) } else { setTracking(false) }
    }

    func sessionWasInterrupted(_ session: ARSession) { invalidate(); send(.stopped("session-interrupted")) }
    func session(_ session: ARSession, didFailWithError error: Error) { invalidate(); send(.stopped("arkit-session-failed")) }

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        guard case .normal = frame.camera.trackingState else { setTracking(false); return }
        setTracking(true)
        guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
            invalidate(); send(.stopped("camera-permission-lost")); return
        }
        let admitted: UInt64? = lock.withLock {
            let now = ProcessInfo.processInfo.systemUptime
            guard active, tracking, !busy, now - lastAdmission >= 0.5 else { return nil }
            busy = true
            lastAdmission = now
            return revision
        }
        guard let admitted else { return }
        do {
            let observation = try autoreleasepool { try encode(frame) }
            guard accepts(admitted), AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
                finishFrame(); return
            }
            send(.frame(observation, admitted))
        } catch {
            finishFrame()
            invalidate()
            send(.stopped("phone-frame-encoding-failed"))
        }
    }

    private func encode(_ frame: ARFrame) throws -> PhoneSpatialObservation {
        let buffer = frame.capturedImage
        let width = CVPixelBufferGetWidth(buffer), height = CVPixelBufferGetHeight(buffer)
        guard (1...4096).contains(width), (1...4096).contains(height), width * height <= 8_388_608,
              frame.camera.imageResolution.width == Double(width),
              frame.camera.imageResolution.height == Double(height),
              let cg = context.createCGImage(CIImage(cvPixelBuffer: buffer), from: CGRect(x: 0, y: 0, width: width, height: height)) else {
            throw PhoneSpatialObservation.ValidationError.invalidFrameBinding
        }
        let data = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(data, UTType.jpeg.identifier as CFString, 1, nil) else {
            throw PhoneSpatialObservation.ValidationError.invalidFrameBinding
        }
        // No rotation/crop/resize: ARCamera.intrinsics remains in these exact pixels.
        CGImageDestinationAddImage(destination, cg, [kCGImageDestinationLossyCompressionQuality: 0.8,
                                                   kCGImagePropertyOrientation: 1] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw PhoneSpatialObservation.ValidationError.invalidFrameBinding }
        let jpeg = data as Data
        let draft = LensFrameDraft(observationID: UUID().uuidString, sessionID: sessionID,
            generation: generation, receivedAtMs: Int64(Date().timeIntervalSince1970 * 1000),
            source: .phoneCamera, frameSHA256: PhoneSpatialObservation.digest(jpeg),
            width: width, height: height, candidates: [])
        let transform = frame.camera.transform, k = frame.camera.intrinsics
        let matrix = (0..<4).flatMap { column in (0..<4).map { row in Double(transform[column][row]) } }
        let intrinsics = (0..<3).flatMap { column in (0..<3).map { row in Double(k[column][row]) } }
        let mapping: PhoneSpatialObservation.MappingStatus
        switch frame.worldMappingStatus {
        case .notAvailable: mapping = .notAvailable
        case .limited: mapping = .limited
        case .extending: mapping = .extending
        case .mapped: mapping = .mapped
        @unknown default: mapping = .notAvailable
        }
        return try PhoneSpatialObservation(frame: draft, jpeg: jpeg, worldID: worldID,
            worldGeneration: generation, capturedAtARSeconds: frame.timestamp,
            cameraToWorld: matrix, intrinsics: intrinsics, mappingStatus: mapping, capabilities: capabilities)
    }
}
#endif
