import AVFoundation
import ChibiLensCore
import CryptoKit
import MWDATCamera
import MWDATCore
import MWDATMockDevice
import SwiftUI
import Vision

/// Debug harness for the REAL Meta SDK using simulated glasses and owned video.
/// There is deliberately no real-glasses selector or phone-camera activation.
@MainActor
final class DATCaptureModel: ObservableObject {
    @Published private(set) var status = "Ready for a test video"
    @Published private(set) var preview: UIImage?
    @Published private(set) var recognizedText = ""
    @Published private(set) var frameCount = 0
    @Published private(set) var lastTimestamp: Double?
    @Published private(set) var frameDigest = ""
    @Published private(set) var running = false
    @Published private(set) var cleaning = false
    @Published private(set) var configured = false
    @Published private(set) var lastError: String?
    private var epoch = CaptureEpoch()
    private var mock: (any MockGlasses)?
    private var selector: SpecificDeviceSelector?
    private var session: DeviceSession?
    private var camera: Camera?
    private var listeners: [any AnyListenerToken] = []
    private var startup: Task<Void, Never>?
    private var watchdog: Task<Void, Never>?
    private var permissionWatch: Task<Void, Never>?
    private var analysis: Task<Void, Never>?
    private var lastFrameAt = Date.distantPast
    private var busy = false
    private var hasStreamed = false
    private var importedVideo: URL?
    private var mockEnabled = false
    var isMockKitEnabled: Bool { MockDeviceKit.shared.isEnabled }
    var hasImportedVideo: Bool { importedVideo != nil }

    private static let configurationError: String? = {
        do {
            try Wearables.configure()
            return nil
        } catch {
            return error.localizedDescription
        }
    }()

    init() {
        lastError = Self.configurationError
        configured = Self.configurationError == nil
        if !configured { status = "Meta SDK configuration failed" }
    }

    func start(video: URL, consent: Bool, bystanderClearance: Bool) {
        guard configured, !running, !cleaning else { return }
        guard let generation = epoch.begin(consent: consent, bystanderClearance: bystanderClearance) else {
            status = "Confirm permission and that the video is cleared for use"
            return
        }
        preview = nil
        recognizedText = ""
        frameDigest = ""
        lastTimestamp = nil
        lastError = nil
        frameCount = 0
        lastFrameAt = .distantPast
        hasStreamed = false
        running = true
        status = "Connecting simulated glasses"
        watchdog = Task { [weak self] in
            try? await Task.sleep(for: .seconds(20))
            guard !Task.isCancelled, let self, self.epoch.accepts(generation), self.frameCount == 0 else { return }
            self.stop(reason: "No SDK frames received — use the manual path")
        }
        startup = Task { [weak self] in
            guard let self, self.epoch.accepts(generation), !Task.isCancelled else { return }
            do {
                MockDeviceKit.shared.enable()
                self.mockEnabled = true
                let mock = try MockDeviceKit.shared.pairGlasses(model: .rayBanMeta)
                self.mock = mock
                mock.services.camera.setCameraFeed(fileURL: video)
                mock.powerOn()
                mock.unfold()
                mock.don()
                let wearables = Wearables.shared
                // Selecting an ID is not proof that the SDK has discovered the mock.
                // Subscribe before checking the snapshot to avoid missing discovery.
                let discovery = wearables.devicesStream()
                self.status = "Waiting for Meta test glasses"
                if !wearables.devices.contains(mock.deviceIdentifier) {
                    for await devices in discovery {
                        guard self.epoch.accepts(generation), !Task.isCancelled else { return }
                        if devices.contains(mock.deviceIdentifier) { break }
                    }
                }
                guard self.epoch.accepts(generation), !Task.isCancelled else { return }
                guard wearables.devices.contains(mock.deviceIdentifier) else {
                    throw DeviceSessionError.noEligibleDevice
                }
                let selector = SpecificDeviceSelector(device: mock.deviceIdentifier)
                self.selector = selector
                self.status = "Creating Meta test session"
                let session = try wearables.createSession(deviceSelector: selector)
                self.session = session
                self.listeners.append(session.statePublisher.listen { [weak self] state in
                    Task { @MainActor in
                        guard let self, self.epoch.accepts(generation) else { return }
                        switch state {
                        case .started: await self.startCamera(generation: generation)
                        case .paused: self.stop(reason: "Session paused — restart when ready")
                        case .stopping, .stopped: self.stop(reason: "Connection ended — manual path available")
                        default: break
                        }
                    }
                })
                self.listeners.append(session.errorPublisher.listen { [weak self] error in
                    Task { @MainActor in
                        guard let self, self.epoch.accepts(generation) else { return }
                        self.lastError = error.localizedDescription
                        self.stop(reason: "Meta session failed — manual path available")
                    }
                })
                self.status = "Starting Meta test session"
                try session.start()
            } catch {
                guard self.epoch.accepts(generation) else { return }
                self.lastError = "\(self.status): \(error.localizedDescription)"
                self.stop(reason: "Could not start Meta test session")
            }
        }
    }

    private func startCamera(generation: UInt64) async {
        guard epoch.accepts(generation), camera == nil, let session else { return }
        // Reserve the slot before the permission await: repeated state events cannot add cameras.
        guard !busy else { return }
        busy = true
        defer { if epoch.accepts(generation) { busy = false } }
        do {
            let permission = try await Wearables.shared.checkPermissionStatus(.camera)
            guard epoch.accepts(generation) else { return }
            guard permission == .granted else {
                stop(reason: "Camera permission denied — manual path available")
                return
            }
            guard let camera = try session.addCamera(config: StreamConfiguration(
                videoCodec: .raw, resolution: .low, frameRate: 24
            )) else { throw CaptureFailure.noCamera }
            self.camera = camera
            listeners.append(camera.stream.videoFramePublisher.listen { [weak self] frame in
                let timestamp = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(frame.sampleBuffer))
                guard timestamp.isFinite, let image = frame.makeUIImage(),
                      let data = image.jpegData(compressionQuality: 0.7) else { return }
                Task { @MainActor in
                    self?.receive(data, timestamp: timestamp, generation: generation)
                }
            })
            listeners.append(camera.stream.statePublisher.listen { [weak self] state in
                Task { @MainActor in
                    guard let self, self.epoch.accepts(generation) else { return }
                    if state == .streaming { self.hasStreamed = true }
                    if self.hasStreamed && (state == .stopped || state == .paused) {
                        self.stop(reason: "Camera stream ended — manual path available")
                    }
                }
            })
            listeners.append(camera.stream.errorPublisher.listen { [weak self] error in
                Task { @MainActor in
                    guard let self, self.epoch.accepts(generation) else { return }
                    self.lastError = error.localizedDescription
                    self.stop(reason: "Camera unavailable — manual path available")
                }
            })
            camera.stream.start()
            status = "Streaming test video through Meta SDK"
            permissionWatch = Task { [weak self] in
                while !Task.isCancelled {
                    try? await Task.sleep(for: .milliseconds(300))
                    guard !Task.isCancelled, let self, self.epoch.accepts(generation) else { return }
                    guard await self.permissionStillGranted(generation) else { return }
                }
            }
        } catch {
            guard epoch.accepts(generation) else { return }
            lastError = error.localizedDescription
            stop(reason: "Could not start camera preview")
        }
    }

    private func permissionStillGranted(_ generation: UInt64) async -> Bool {
        do {
            let permission = try await Wearables.shared.checkPermissionStatus(.camera)
            guard epoch.accepts(generation), !Task.isCancelled else { return false }
            guard permission == .granted else {
                stop(reason: "Camera permission revoked — manual path available")
                return false
            }
            return true
        } catch {
            guard epoch.accepts(generation) else { return false }
            lastError = error.localizedDescription
            stop(reason: "Cannot confirm camera permission — manual path available")
            return false
        }
    }

    private func receive(_ data: Data, timestamp: Double, generation: UInt64) {
        guard epoch.accepts(generation), !busy,
              Date().timeIntervalSince(lastFrameAt) >= 0.5, data.count <= 2_000_000 else { return }
        busy = true
        lastFrameAt = Date()
        analysis = Task { [weak self] in
            guard let self else { return }
            defer { if self.epoch.accepts(generation) { self.busy = false } }
            guard await self.permissionStillGranted(generation), self.epoch.accepts(generation),
                  let image = UIImage(data: data), let cg = image.cgImage else { return }
            let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
            let draft = LensFrameDraft(
                observationID: UUID().uuidString, sessionID: "mock-\(generation)",
                generation: Int(generation), receivedAtMs: Int64(Date().timeIntervalSince1970 * 1000),
                source: .fixture, frameSHA256: digest, width: cg.width, height: cg.height, candidates: []
            )
            do {
                try LensDraftValidator.check(draft, gate: CaptureGate(consent: .granted,
                    platformPermissionGranted: true, bystanderClearance: true,
                    sessionGeneration: Int(generation)), activeSessionID: "mock-\(generation)")
                self.preview = image
                self.lastTimestamp = timestamp
                self.frameDigest = digest
                self.frameCount += 1
                // Vision reads the actual SDK-delivered pixels. No canned recognition result.
                let worker = Task.detached(priority: .utility) { try Self.readText(data) }
                let text = try await withTaskCancellationHandler {
                    try await worker.value
                } onCancel: { worker.cancel() }
                guard !Task.isCancelled, await self.permissionStillGranted(generation),
                      self.epoch.accepts(generation) else { return }
                self.recognizedText = text.isEmpty ? "No readable label in this frame" : text
                self.status = "Read from test video · identity unverified"
            } catch {
                guard self.epoch.accepts(generation), !Task.isCancelled else { return }
                self.lastError = error.localizedDescription
                self.stop(reason: "Frame analysis failed — manual path available")
            }
        }
    }

    nonisolated private static func readText(_ data: Data) throws -> String {
        try Task.checkCancellation()
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["en-US"]
        try VNImageRequestHandler(data: data).perform([request])
        try Task.checkCancellation()
        return (request.results ?? []).prefix(12).compactMap { $0.topCandidates(1).first?.string }
            .joined(separator: "\n")
    }

    func revoke() { stop(reason: "Permission revoked — continue manually") }
    func simulateSDKPermissionRevocation() {
        MockDeviceKit.shared.permissions.set(.camera, .denied)
    }
    func simulateDisconnect() { mock?.fold() }

    func stop(reason: String = "Stopped — continue manually") {
        epoch.invalidate() // Fence all callbacks/results BEFORE stopping the SDK.
        running = false
        busy = false
        preview = nil
        recognizedText = ""
        frameDigest = ""
        lastTimestamp = nil
        startup?.cancel(); startup = nil
        watchdog?.cancel(); watchdog = nil
        permissionWatch?.cancel(); permissionWatch = nil
        analysis?.cancel(); analysis = nil
        camera?.stop(); camera = nil
        session?.stop(); session = nil
        selector = nil
        mock = nil
        status = reason
        guard !cleaning else { return }
        guard mockEnabled else { removeImportedVideo(); return }
        mockEnabled = false
        cleaning = true
        let oldListeners = listeners
        listeners = []
        Task { [weak self] in
            for token in oldListeners { await token.cancel() }
            await MockDeviceKit.shared.disable()
            guard let self else { return }
            self.removeImportedVideo()
            self.cleaning = false
        }
    }

    private func removeImportedVideo() {
        if let importedVideo {
            try? FileManager.default.removeItem(at: importedVideo)
            self.importedVideo = nil
        }
    }

    func importAndStart(_ url: URL, consent: Bool, bystanderClearance: Bool) throws {
        guard configured, !running, !cleaning, consent, bystanderClearance else { throw CaptureFailure.notReady }
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }
        let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max
        guard size > 0, size <= 20_000_000 else { throw CaptureFailure.videoTooLarge }
        let owned = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".mp4")
        try FileManager.default.copyItem(at: url, to: owned)
        importedVideo = owned
        start(video: owned, consent: consent, bystanderClearance: bystanderClearance)
    }

    private enum CaptureFailure: Error { case noCamera, notReady, videoTooLarge }
}
