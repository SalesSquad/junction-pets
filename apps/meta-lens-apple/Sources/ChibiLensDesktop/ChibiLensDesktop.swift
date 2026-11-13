import SwiftUI
import ChibiLensUI
import OSLog

@main
struct ChibiLensDesktop: App {
    private let logger = Logger(subsystem: "cloud.taika.chibilens.replay", category: "lifecycle")

    init() {
        logger.info("Starting synthetic Chibi Lens replay; no connected camera")
    }

    var body: some Scene {
        WindowGroup {
            LensReplayView()
                .frame(minWidth: 600, minHeight: 580)
        }
    }
}
