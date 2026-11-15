import Foundation

/// Focused portable state-machine checks. Compile with GuideSession.swift.
/// These synthetic values are not ARKit, camera, rendering or identity evidence.
@main @MainActor enum GuideBoundaryChecks {
    static let now: Int64 = 1_800_000_000_000
    static let a = String(repeating: "a", count: 64)
    static let b = String(repeating: "b", count: 64)
    static var count = 0
    static func check(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else { fatalError(message) }; count += 1
    }
    static func fails(_ expected: GuideSession.Failure, _ action: () throws -> Void) {
        do { try action(); fatalError("Expected \(expected)") }
        catch let error as GuideSession.Failure { check(error == expected, "Unexpected \(error)") }
        catch { fatalError("Unexpected error: \(error)") }
    }
    static func arm(_ session: inout GuideSession, at time: Int64 = now) throws -> GuideSession.Request {
        try session.ask(kind: .label, targetID: "item-1", sessionID: "session-1", captureGeneration: 1,
                        worldID: "world-1", watermark: 100, previousHash: a, nowMs: time)
    }
    static func observe(_ session: inout GuideSession, _ request: GuideSession.Request) throws {
        try session.observe(requestID: request.id, sessionID: "session-1", generation: 1,
            worldID: "world-1", frameSHA256: b, arSeconds: 101, receivedAtMs: request.issuedAtMs + 1,
            nowMs: request.issuedAtMs + 2)
    }
    static func main() throws {
        var session = GuideSession()
        fails(.consentRequired) { _ = try arm(&session) }
        session.setConsent(true)
        let request = try arm(&session)
        fails(.freshFrameRequired) {
            try session.observe(requestID: request.id, sessionID: "session-1", generation: 1,
                worldID: "world-1", frameSHA256: b, arSeconds: 100, receivedAtMs: now+1, nowMs: now+2)
        }
        fails(.freshFrameRequired) {
            try session.observe(requestID: request.id, sessionID: "other-session", generation: 1,
                worldID: "world-1", frameSHA256: b, arSeconds: 101, receivedAtMs: now+1, nowMs: now+2)
        }
        fails(.freshFrameRequired) {
            try session.observe(requestID: request.id, sessionID: "session-1", generation: 1,
                worldID: "world-1", frameSHA256: a, arSeconds: 101, receivedAtMs: now+1, nowMs: now+2)
        }
        try observe(&session, request)
        check(session.accepted?.requestedDetailVerified == false, "New pixels are not verified detail")
        fails(.freshFrameRequired) { _ = try session.confirmMemory(requestID: request.id, name: "Charger", place: "Desk", userConfirmed: false, nowMs: now+3) }
        let memory = try session.confirmMemory(requestID: request.id, name: "Charger", place: "Desk", userConfirmed: true, nowMs: now+3)
        check(!memory.physicalIdentityVerified && !memory.currentPresenceVerified, "History must remain unverified")
        check(session.request == nil && session.accepted == nil, "Confirmation retires frame")
        try session.begin(.packing)
        let packing = try arm(&session)
        try observe(&session, packing)
        try session.confirmPacked(requestID: packing.id, userConfirmed: true, nowMs: now+3)
        check(session.memories[0].packedAtMs == now+3, "User packing history missing")
        session.pause(); try session.resume()
        check(session.memories[0].packedAtMs == now+3, "Pause/resume must preserve task progress")
        try session.begin(.packing)
        check(session.memories[0].packedAtMs == nil, "A new task must not inherit completed steps")
        let forgotten = try arm(&session)
        try observe(&session, forgotten)
        session.forget(id: "item-1")
        fails(.staleRequest) { _ = try session.confirmMemory(requestID: forgotten.id, name: "Charger", place: "Desk", userConfirmed: true, nowMs: now+3) }
        check(session.memories.isEmpty && session.accepted == nil, "Forget must clear pending work")
        let expired = try arm(&session)
        try observe(&session, expired)
        fails(.staleRequest) { _ = try session.confirmMemory(requestID: expired.id, name: "Charger", place: "Desk", userConfirmed: true, nowMs: now+30_000) }
        session.setConsent(false)
        fails(.consentRequired) { _ = try session.confirmMemory(requestID: expired.id, name: "Charger", place: "Desk", userConfirmed: true, nowMs: now+3) }
        session.setConsent(true)
        let changed = try arm(&session)
        try session.begin(.teaching)
        fails(.staleRequest) { try observe(&session, changed) }
        print("{\"result\":\"PASS\",\"checks\":\(count),\"evidenceMode\":\"synthetic-state-machine\",\"cameraStarted\":false}")
    }
}
