#if os(iOS) && canImport(ARKit)
import ARKit
import AVFoundation
import ChibiLensARKit
import ChibiLensCore
import Foundation
import Observation
import UIKit

/// Explicit, local phone guide. No network, identity issuer, model execution,
/// ScreenshotContext crawl, or glasses-to-phone registration is hidden here.
@MainActor @Observable
public final class LensGuideModel {
    public private(set) var memories: [GuideSession.Memory] = []
    public private(set) var phase: GuideSession.Phase = .teaching
    public private(set) var captureState: PhoneSpatialCapture.State = .stopped
    public private(set) var status = "Choose what to remember, then start your phone camera."
    public private(set) var hasRequest = false
    public private(set) var requestID: String?
    public private(set) var reviewedFrameSHA256: String?
    public private(set) var waitingForFrame = false
    public private(set) var reviewedImage: UIImage?
    public private(set) var markerLabel: String?
    public private(set) var permissionPending = false
    public private(set) var selectedTarget: String?
    public var name = ""
    public var place = ""
    @ObservationIgnored public let capture = PhoneSpatialCapture()
    @ObservationIgnored private var notebook = GuideSession()
    @ObservationIgnored private var permissionTicket = UUID()
    @ObservationIgnored private var requestExpiry: Task<Void, Never>?
    @ObservationIgnored private var acceptedObservation: PhoneSpatialObservation?
    @ObservationIgnored private var captureAfterAR: Double?
    @ObservationIgnored private var presented = false
    @ObservationIgnored private var pendingSurface: PhoneSpatialCapture.SurfaceMarker?
    @ObservationIgnored private var rememberedSurfaces: [String: PhoneSpatialCapture.SurfaceMarker] = [:]

    public init() {
        capture.onObservation = { [weak self] value in self?.receive(value) }
        capture.onStateChanged = { [weak self] state, reason in
            guard let self else { return }
            self.captureState = state
            if state == .stopped {
                self.rememberedSurfaces.removeAll()
                self.cancelRequest()
                if reason != "stopped" { self.status = "Camera stopped. Start again when ready." }
            } else if state == .tracking { self.status = "Camera ready. Ask for a view of your item." }
            else { self.status = "Move your phone gently to find a surface." }
        }
    }
    private var nowMs: Int64 { Int64(Date().timeIntervalSince1970 * 1000) }

    /// Permission is requested only by the visible Start action. An outstanding
    /// permission result cannot restart capture after pause, revoke or dismissal.
    public func setPresented(_ value: Bool) {
        presented = value
        if !value { stop() }
    }
    public func start(consent: Bool, bystandersClear: Bool) {
        guard presented, UIApplication.shared.applicationState == .active else { return }
        guard consent, bystandersClear else { status = "Confirm camera consent and your surroundings first."; return }
        guard !permissionPending else { return }
        guard let usage = Bundle.main.object(forInfoDictionaryKey: "NSCameraUsageDescription") as? String,
              !usage.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            status = "The containing app needs its camera usage description."; return
        }
        let ticket = UUID(); permissionTicket = ticket; permissionPending = true
        Task { [weak self] in await self?.finishStart(ticket: ticket) }
    }
    private func finishStart(ticket: UUID) async {
        guard ticket == permissionTicket, presented else { return }
        var allowed = AVCaptureDevice.authorizationStatus(for: .video) == .authorized
        if AVCaptureDevice.authorizationStatus(for: .video) == .notDetermined {
            allowed = await AVCaptureDevice.requestAccess(for: .video)
        }
        guard ticket == permissionTicket, presented else { return }
        permissionPending = false
        guard UIApplication.shared.applicationState == .active else { return }
        guard allowed else { status = "Camera access is unavailable. Your saved history is still readable."; return }
        notebook.setConsent(true)
        do { try capture.start(sessionID: UUID().uuidString, consent: .granted, bystanderClearance: true) }
        catch { notebook.setConsent(false); status = "Phone AR capture could not start: \(error)." }
        synchronize()
    }

    public func stop() {
        permissionTicket = UUID(); permissionPending = false
        notebook.setConsent(false)
        capture.stop()
        cancelRequest()
        status = "Camera stopped. Your confirmations remain local to this view."
    }
    public func setPhase(_ next: GuideSession.Phase) {
        do { try notebook.begin(next); selectedTarget = nil; cancelRequest(); synchronize() }
        catch { status = "Start capture before changing the active task." }
    }
    public func select(_ memory: GuideSession.Memory) {
        cancelRequest()
        selectedTarget = memory.id; name = memory.name; place = memory.place
        status = "Last confirmed at \(memory.place). Take a new look before confirming."
        if let point = rememberedSurfaces[memory.id], (try? capture.showRememberedMarker(point)) != nil {
            markerLabel = "Remembered surface estimate · not the item's current location"
        }
    }
    public func teachAnother() {
        cancelRequest(); selectedTarget = nil; name = ""; place = ""
        do { try notebook.begin(.teaching); synchronize() }
        catch { status = "Start capture to teach another item." }
    }
    public func ask(_ kind: GuideSession.ViewKind) {
        guard let latest = capture.latest, let watermark = capture.currentFrameTimestamp else {
            status = "Wait for normal phone tracking, then ask again."; return
        }
        let target = selectedTarget ?? UUID().uuidString
        do {
            try capture.validateCurrent(latest)
            cancelRequest()
            let request = try notebook.ask(kind: kind, targetID: target, sessionID: latest.frame.sessionID,
                captureGeneration: latest.frame.generation, worldID: latest.worldID,
                watermark: watermark, previousHash: latest.frame.frameSHA256, nowMs: nowMs)
            hasRequest = true
            requestID = request.id
            status = kind == .label ? "Show the label clearly, then capture." : kind == .side ? "Show a different side, then capture." : "Show the item and its surroundings, then capture."
            requestExpiry = Task { [weak self] in
                do { try await Task.sleep(for: .seconds(30)) } catch { return }
                guard let self, self.notebook.request?.id == request.id else { return }
                self.cancelRequest(); self.status = "That request expired. Ask for a fresh view."
            }
        } catch { status = "The task or camera changed. Ask again." }
    }
    public func captureNextFrame() {
        guard let request = notebook.request, (try? notebook.current(request.id, nowMs: nowMs)) != nil,
              let watermark = capture.currentFrameTimestamp else { cancelRequest(); status = "Ask for a fresh view first."; return }
        captureAfterAR = watermark
        waitingForFrame = true
        status = "Capturing a new frame…"
    }
    private func receive(_ observation: PhoneSpatialObservation) {
        guard waitingForFrame, let request = notebook.request, let after = captureAfterAR,
              observation.capturedAtARSeconds > after else { return }
        do {
            try capture.validateCurrent(observation)
            try notebook.observe(requestID: request.id, sessionID: observation.frame.sessionID,
                generation: observation.frame.generation, worldID: observation.worldID,
                frameSHA256: observation.frame.frameSHA256, arSeconds: observation.capturedAtARSeconds,
                receivedAtMs: observation.frame.receivedAtMs, nowMs: nowMs)
            acceptedObservation = observation
            reviewedFrameSHA256 = observation.frame.frameSHA256
            reviewedImage = UIImage(data: observation.jpeg)
            waitingForFrame = false
            status = "Review this captured image. You decide what it shows."
        } catch GuideSession.Failure.freshFrameRequired {
            // An unchanged JPEG is not a new distinguishing view. Keep waiting
            // within the same bounded request, rather than inventing success.
            status = "Move to a useful new view; this image has not changed."
        } catch { cancelRequest(); status = "The task or camera changed. Take another view." }
    }
    private func validateAccepted() throws -> String {
        guard let frame = acceptedObservation, let request = notebook.request,
              notebook.accepted?.frameSHA256 == frame.frame.frameSHA256 else { throw GuideSession.Failure.freshFrameRequired }
        try capture.validateCurrent(frame)
        guard let current = capture.currentFrameTimestamp, current >= frame.capturedAtARSeconds,
              current - frame.capturedAtARSeconds <= 30 else { throw GuideSession.Failure.staleRequest }
        _ = try notebook.current(request.id, nowMs: nowMs)
        return request.id
    }
    public func confirm(userChecked: Bool) {
        do {
            let requestID = try validateAccepted()
            var remembered: PhoneSpatialCapture.SurfaceMarker?
            if phase == .packing { try notebook.confirmPacked(requestID: requestID, userConfirmed: userChecked, nowMs: nowMs) }
            else {
                let memory = try notebook.confirmMemory(requestID: requestID, name: name, place: place, userConfirmed: userChecked, nowMs: nowMs)
                remembered = pendingSurface
                rememberedSurfaces[memory.id] = remembered
            }
            cancelRequest(); synchronize()
            if let point = remembered, (try? capture.showRememberedMarker(point)) != nil {
                markerLabel = "Remembered surface estimate · not the item's current location"
            }
            status = "Confirmed by you. This is history, not a live location."
        } catch { status = "Check the item and a fresh image before confirming." }
    }
    public func markSurface(at point: CGPoint, in view: ARSCNView) {
        pendingSurface = nil
        markerLabel = nil
        capture.clearMarkers()
        do {
            _ = try validateAccepted()
            guard let frame = acceptedObservation else { return }
            pendingSurface = try capture.placeMarker(at: point, in: view, for: frame)
            markerLabel = "Phone surface estimate · expires with this AR session"
        } catch { markerLabel = nil; status = "No usable surface here. Try a nearby visible surface." }
    }
    public func pause() {
        notebook.pause(); stop(); synchronize()
        status = "Paused here. Start the camera and resume when ready."
    }
    public func resume() {
        do { try notebook.resume(); synchronize(); status = "Resumed from your confirmations. Ask for the next item." }
        catch { status = "Start the camera before resuming." }
    }
    public func forget(_ id: String? = nil) {
        if let id { rememberedSurfaces.removeValue(forKey: id) } else { rememberedSurfaces.removeAll() }
        notebook.forget(id: id); cancelRequest(); selectedTarget = nil; name = ""; place = ""
        synchronize(); status = "Forgotten. Pending views and surface markers were cleared."
    }
    private func cancelRequest() {
        requestExpiry?.cancel(); requestExpiry = nil
        notebook.cancelObservation()
        acceptedObservation = nil; reviewedImage = nil; captureAfterAR = nil
        pendingSurface = nil
        requestID = nil; reviewedFrameSHA256 = nil
        hasRequest = false; waitingForFrame = false; markerLabel = nil
        capture.clearMarkers()
    }
    private func synchronize() { memories = notebook.memories; phase = notebook.phase }
}
#endif
