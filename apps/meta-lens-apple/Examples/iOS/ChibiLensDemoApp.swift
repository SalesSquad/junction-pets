// Add ChibiLensUI as a local Swift Package dependency to an iOS App target.
// The production DAT adapter remains intentionally unconnected.
import SwiftUI
import ChibiLensUI

@main
struct ChibiLensDemoApp: App {
    var body: some Scene {
        WindowGroup {
            LensReplayView()
        }
    }
}
