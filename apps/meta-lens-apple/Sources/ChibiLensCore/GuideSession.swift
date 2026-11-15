import Foundation

/// A user-owned notebook and a requested-view state machine. These values are
/// client proposals/history; none is an authenticated Chibi observation receipt.
public struct GuideSession: Sendable {
    public enum Failure: Error, Equatable {
        case consentRequired, invalidInput, taskChanged, staleRequest, freshFrameRequired, memoryLimit
    }
    public enum ViewKind: String, Codable, CaseIterable, Sendable { case overview, label, side }
    public enum Phase: String, Codable, Sendable { case teaching, packing, paused }

    public struct Memory: Identifiable, Codable, Equatable, Sendable {
        public let id: String
        public var name: String
        public var place: String
        public var confirmedAtMs: Int64
        public var frameSHA256: String
        /// User confirmation of a task action, not evidence of current presence.
        public var packedAtMs: Int64?
        public var physicalIdentityVerified: Bool { false }
        public var currentPresenceVerified: Bool { false }
    }
    public struct Request: Equatable, Sendable {
        public let id: String
        public let taskID: String
        public let taskRevision: Int
        public let memoryEpoch: Int
        public let targetID: String
        public let sessionID: String
        public let captureGeneration: Int
        public let worldID: String
        public let frameWatermark: Double
        public let previousFrameSHA256: String?
        public let issuedAtMs: Int64
        public let expiresAtMs: Int64
        public let kind: ViewKind
    }
    public struct AcceptedFrame: Equatable, Sendable {
        public let requestID: String
        public let frameSHA256: String
        public let arSeconds: Double
        public let receivedAtMs: Int64
        public var requestedDetailVerified: Bool { false }
    }
    public private(set) var taskID = UUID().uuidString
    public private(set) var revision = 0
    public private(set) var memoryEpoch = 0
    public private(set) var consent = false
    public private(set) var phase: Phase = .teaching
    public private(set) var memories: [Memory] = []
    public private(set) var request: Request?
    public private(set) var accepted: AcceptedFrame?
    private var resumePhase: Phase = .teaching
    public init() {}

    public mutating func setConsent(_ enabled: Bool) {
        consent = enabled
        invalidate()
    }

    public mutating func begin(_ next: Phase) throws {
        guard consent else { throw Failure.consentRequired }
        guard next != .paused, next != .packing || !memories.isEmpty else { throw Failure.invalidInput }
        phase = next
        taskID = UUID().uuidString
        if next == .packing {
            for index in memories.indices { memories[index].packedAtMs = nil }
        }
        invalidate()
    }

    /// The capture owner supplies a watermark from its current ARFrame, not the
    /// last asynchronously delivered JPEG. Queued old frames cannot satisfy it.
    @discardableResult
    public mutating func ask(kind: ViewKind, targetID: String, sessionID: String,
                             captureGeneration: Int, worldID: String,
                             watermark: Double, previousHash: String?, nowMs: Int64) throws -> Request {
        guard consent else { throw Failure.consentRequired }
        guard phase != .paused, Self.validText(targetID, max: 160),
              Self.validText(sessionID, max: 160), Self.validText(worldID, max: 160),
              captureGeneration > 0, watermark.isFinite, watermark >= 0,
              nowMs > 0, nowMs < Int64.max - 30_000,
              previousHash == nil || Self.validHash(previousHash!),
              phase != .packing || memories.contains(where: { $0.id == targetID }) else { throw Failure.invalidInput }
        invalidate()
        let value = Request(id: UUID().uuidString, taskID: taskID, taskRevision: revision,
            memoryEpoch: memoryEpoch, targetID: targetID, sessionID: sessionID,
            captureGeneration: captureGeneration, worldID: worldID, frameWatermark: watermark,
            previousFrameSHA256: previousHash, issuedAtMs: nowMs, expiresAtMs: nowMs + 30_000, kind: kind)
        request = value
        return value
    }

    /// Call only after PhoneSpatialCapture.validateCurrent validates actual JPEG
    /// bytes and live consent. This portable function adds causal task binding.
    public mutating func observe(requestID: String, sessionID: String, generation: Int,
                                 worldID: String, frameSHA256: String, arSeconds: Double,
                                 receivedAtMs: Int64, nowMs: Int64) throws {
        let r = try current(requestID, nowMs: nowMs)
        guard r.sessionID == sessionID, r.captureGeneration == generation, r.worldID == worldID,
              Self.validHash(frameSHA256), frameSHA256 != r.previousFrameSHA256,
              arSeconds.isFinite, arSeconds > r.frameWatermark,
              receivedAtMs >= r.issuedAtMs, receivedAtMs <= nowMs,
              nowMs - receivedAtMs <= 30_000 else { throw Failure.freshFrameRequired }
        // First accepted frame stays stable while the user reviews it. Later
        // frames cannot silently change the pixels to which confirmation refers.
        guard accepted == nil else { throw Failure.staleRequest }
        accepted = AcceptedFrame(requestID: r.id, frameSHA256: frameSHA256,
                                 arSeconds: arSeconds, receivedAtMs: receivedAtMs)
    }

    @discardableResult
    public mutating func confirmMemory(requestID: String, name: String, place: String,
                                       userConfirmed: Bool, nowMs: Int64) throws -> Memory {
        let r = try current(requestID, nowMs: nowMs)
        guard userConfirmed, let frame = accepted, frame.requestID == r.id,
              Self.validText(name, max: 80), Self.validText(place, max: 120) else { throw Failure.freshFrameRequired }
        let entry = Memory(id: r.targetID, name: name.trimmingCharacters(in: .whitespacesAndNewlines),
            place: place.trimmingCharacters(in: .whitespacesAndNewlines), confirmedAtMs: nowMs,
            frameSHA256: frame.frameSHA256, packedAtMs: nil)
        if let index = memories.firstIndex(where: { $0.id == r.targetID }) { memories[index] = entry }
        else {
            guard memories.count < 10 else { throw Failure.memoryLimit }
            memories.append(entry)
        }
        invalidate()
        return entry
    }

    public mutating func confirmPacked(requestID: String, userConfirmed: Bool, nowMs: Int64) throws {
        let r = try current(requestID, nowMs: nowMs)
        guard phase == .packing, userConfirmed, accepted?.requestID == r.id,
              let index = memories.firstIndex(where: { $0.id == r.targetID }) else { throw Failure.freshFrameRequired }
        memories[index].packedAtMs = nowMs
        invalidate()
    }

    public mutating func pause() {
        if phase != .paused { resumePhase = phase }
        phase = .paused
        invalidate()
    }
    public mutating func resume() throws {
        guard consent else { throw Failure.consentRequired }
        guard phase == .paused else { throw Failure.taskChanged }
        phase = resumePhase
        invalidate()
    }
    public mutating func forget(id: String? = nil) {
        if let id { memories.removeAll { $0.id == id } } else { memories.removeAll() }
        memoryEpoch += 1
        invalidate()
        if memories.isEmpty { phase = .teaching; resumePhase = .teaching }
    }
    public mutating func cancelObservation() { invalidate() }

    public func current(_ id: String, nowMs: Int64) throws -> Request {
        guard consent else { throw Failure.consentRequired }
        guard phase != .paused, let r = request, r.id == id, r.taskID == taskID,
              r.taskRevision == revision, r.memoryEpoch == memoryEpoch,
              nowMs >= r.issuedAtMs, nowMs < r.expiresAtMs else { throw Failure.staleRequest }
        return r
    }
    private mutating func invalidate() { revision += 1; request = nil; accepted = nil }
    private static func validText(_ value: String, max: Int) -> Bool {
        !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && value.utf8.count <= max &&
        !value.unicodeScalars.contains { CharacterSet.controlCharacters.contains($0) }
    }
    private static func validHash(_ value: String) -> Bool {
        value.utf8.count == 64 && value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }
}
