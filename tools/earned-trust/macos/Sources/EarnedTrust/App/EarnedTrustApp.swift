import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }
}

@main
struct EarnedTrustApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        WindowGroup("Earned Trust", id: "review") {
            ContentView()
                .frame(minWidth: 1040, minHeight: 680)
        }
        .defaultSize(width: 1320, height: 850)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Import Review Packet…") { NotificationCenter.default.post(name: .importReviewPacket, object: nil) }
                    .keyboardShortcut("o", modifiers: .command)
            }
            CommandMenu("Review") {
                Button("Record Local Decision…") { NotificationCenter.default.post(name: .recordReviewDecision, object: nil) }
                    .keyboardShortcut("r", modifiers: [.command, .shift])
                Button("Reload Evidence") { NotificationCenter.default.post(name: .reloadReviewEvidence, object: nil) }
                    .keyboardShortcut("r", modifiers: .command)
            }
        }
        Settings { SettingsView() }
    }
}

extension Notification.Name {
    static let importReviewPacket = Notification.Name("EarnedTrust.importPacket")
    static let recordReviewDecision = Notification.Name("EarnedTrust.recordDecision")
    static let reloadReviewEvidence = Notification.Name("EarnedTrust.reloadEvidence")
}
