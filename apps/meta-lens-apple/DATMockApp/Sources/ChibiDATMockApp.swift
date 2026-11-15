import SwiftUI
import UniformTypeIdentifiers

@main
struct ChibiDATMockApp: App {
    @StateObject private var model = DATCaptureModel()
    @Environment(\.scenePhase) private var scenePhase
    @State private var consent = false
    @State private var clearedVideo = false
    @State private var importing = false
    @State private var importError: String?

    var body: some Scene {
        WindowGroup {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        Text("See a label. Resume your task.").font(.largeTitle.bold())
                        Text("Simulated glasses · real Meta SDK · on-device text recognition")
                            .font(.subheadline).foregroundStyle(.secondary)
                        if let image = model.preview {
                            Image(uiImage: image).resizable().scaledToFit()
                                .accessibilityLabel("Preview from the test video")
                        } else {
                            ContentUnavailableView("Camera is off", systemImage: "eyeglasses",
                                description: Text("Use our generated video or import your own cleared HEVC MP4."))
                        }
                        Text(model.status).accessibilityIdentifier("captureStatus")
                        if !model.recognizedText.isEmpty {
                            Text(model.recognizedText).font(.title2).textSelection(.enabled)
                                .accessibilityIdentifier("recognizedText")
                        }
                        Text("Processed frames: \(model.frameCount)").monospacedDigit()
                        Toggle("I allow this test video to be processed", isOn: $consent)
                        Toggle("I have permission to use the people and content shown", isOn: $clearedVideo)
                        HStack {
                            Button("Play demo") {
                                if let video = Bundle.main.url(forResource: "charger-label", withExtension: "mp4") {
                                    model.start(video: video, consent: consent, bystanderClearance: clearedVideo)
                                }
                            }.buttonStyle(.borderedProminent)
                            Button("Import video") { importing = true }.buttonStyle(.bordered)
                        }.disabled(!model.configured || !consent || !clearedVideo || model.running || model.cleaning)
                        if model.running {
                            Button("Revoke app consent & clear", role: .destructive) { model.revoke() }
                            Button("Simulate Meta permission denial") { model.simulateSDKPermissionRevocation() }
                            Button("Simulate disconnect") { model.simulateDisconnect() }
                        }
                        if let error = model.lastError ?? importError {
                            Text(error).font(.caption).foregroundStyle(.red)
                        }
                        Text("Manual fallback: read the label yourself. A matching label is not proof that this is your charger. No frame is uploaded or saved; no host action is authorized.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }.padding()
                }.navigationTitle("Chibi Resume")
            }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.mpeg4Movie]) { result in
                do {
                    try model.importAndStart(result.get(), consent: consent, bystanderClearance: clearedVideo)
                    importError = nil
                } catch { importError = "Could not open video: \(error.localizedDescription)" }
            }
            .onChange(of: consent) { _, allowed in if !allowed { model.revoke() } }
            .onChange(of: clearedVideo) { _, allowed in if !allowed { model.revoke() } }
            .onChange(of: scenePhase) { _, phase in
                if phase != .active { model.stop(reason: "App left the foreground — restart when ready") }
            }
        }
    }
}
