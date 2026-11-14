import Foundation

/// App-local cancellation fence. Never a device identity or host-issued grant.
/// The owner serializes access (the DAT adapter uses the main actor).
public struct CaptureEpoch: Sendable {
    public private(set) var generation: UInt64 = 0
    public private(set) var isActive = false

    public init() {}

    @discardableResult public mutating func begin(consent: Bool, bystanderClearance: Bool) -> UInt64? {
        invalidate()
        guard consent && bystanderClearance else { return nil }
        isActive = true
        return generation
    }

    public mutating func invalidate() {
        generation &+= 1
        isActive = false
    }

    public func accepts(_ capturedGeneration: UInt64) -> Bool {
        isActive && capturedGeneration == generation
    }
}
