#if os(iOS) && canImport(ARKit)
import ARKit
import ChibiLensCore
import SceneKit
import SwiftUI
import UIKit

/// Embed in an iOS app with NSCameraUsageDescription. Merely presenting this
/// screen never starts capture. Notebook state is scoped to this view's lifetime.
@MainActor
public struct PhoneLensGuideView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var model = LensGuideModel()
    @State private var cameraConsent = false
    @State private var bystandersClear = false
    public init() {}

    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    GuideHeader(status: model.status)
                    GuideCaptureControls(model: model, consent: $cameraConsent, clearance: $bystandersClear)
                    if model.captureState != .stopped {
                        PhoneGuidePreview(model: model)
                            .frame(height: 280)
                            .clipShape(RoundedRectangle(cornerRadius: 20))
                            .accessibilityLabel("Phone camera. After capturing, tap a surface to place a temporary marker.")
                        if let marker = model.markerLabel { Text(marker).font(.caption).foregroundStyle(.secondary) }
                    }
                    GuideObservationControls(model: model)
                    GuideNotebook(model: model)
                    GuideLifecycleControls(model: model)
                    Text("Phone-only preview. Surface estimates are not item identity or glasses coordinates. Images stay in memory; closing this view ends this notebook. No Chibi host is connected.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                .frame(maxWidth: 650, alignment: .leading).padding()
                .frame(maxWidth: .infinity)
            }
            .navigationTitle("Lens Guide")
            .onAppear { model.setPresented(true) }
            .onChange(of: cameraConsent) { _, granted in if !granted { model.stop() } }
            .onChange(of: bystandersClear) { _, clear in if !clear { model.stop() } }
            .onChange(of: scenePhase) { _, phase in if phase == .background { model.pause() } }
            .onDisappear { model.setPresented(false) }
        }
    }
}

@MainActor private struct GuideHeader: View {
    let status: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Teach once. Pick up where you left off.").font(.title2.bold())
            Text(status).accessibilityAddTraits(.updatesFrequently)
        }
    }
}

@MainActor private struct GuideCaptureControls: View {
    let model: LensGuideModel
    @Binding var consent: Bool
    @Binding var clearance: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Toggle("Use my phone camera for this task", isOn: $consent)
            Toggle("My surroundings are clear to capture", isOn: $clearance)
            HStack {
                Button(model.permissionPending ? "Waiting for permission…" : "Start camera") {
                    model.start(consent: consent, bystandersClear: clearance)
                }
                .buttonStyle(.borderedProminent)
                .disabled(!consent || !clearance || model.permissionPending || model.captureState != .stopped)
                Button("Stop camera") { model.stop() }.buttonStyle(.bordered)
            }
        }
    }
}

@MainActor private struct GuideObservationControls: View {
    @Bindable var model: LensGuideModel
    @State private var userChecked = false
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.phase == .packing ? "Check the next item" : "Teach an item").font(.headline)
            if model.phase == .packing {
                Text(model.selectedTarget == nil ? "Choose an item from your workbench below." : model.name)
            }
            if model.phase != .packing {
                TextField("Item name", text: $model.name).textFieldStyle(.roundedBorder)
                TextField("Where you put it", text: $model.place).textFieldStyle(.roundedBorder)
            }
            ViewThatFits(in: .horizontal) {
                HStack { GuideRequestButtons(model: model) }
                VStack(alignment: .leading) { GuideRequestButtons(model: model) }
            }
            .disabled(model.captureState != .tracking || model.phase == .paused)
            if model.hasRequest, model.reviewedImage == nil {
                Button(model.waitingForFrame ? "Waiting for a new frame…" : "Capture this view") { model.captureNextFrame() }
                    .buttonStyle(.borderedProminent).disabled(model.waitingForFrame)
            }
            if let image = model.reviewedImage {
                Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 220)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .accessibilityLabel("The captured image awaiting your review")
                Text("Captured image · detail not automatically verified").font(.caption).foregroundStyle(.secondary)
                Toggle(model.phase == .packing ? "I checked this item and packed it" : "I checked this item, name and place", isOn: $userChecked)
                Button(model.phase == .packing ? "Confirm packed" : "Remember this association") { model.confirm(userChecked: userChecked) }
                    .buttonStyle(.borderedProminent).disabled(!userChecked)
                Button("Try a different view") { model.ask(.side) }
            }
        }
        .onChange(of: model.requestID) { _, _ in userChecked = false }
        .onChange(of: model.reviewedFrameSHA256) { _, _ in userChecked = false }
        .onChange(of: model.selectedTarget) { _, _ in userChecked = false }
    }
}

@MainActor private struct GuideRequestButtons: View {
    let model: LensGuideModel
    var body: some View {
        Button("Overview") { model.ask(.overview) }.buttonStyle(.bordered)
        Button("Read the label") { model.ask(.label) }.buttonStyle(.bordered)
        Button("Another side") { model.ask(.side) }.buttonStyle(.bordered)
    }
}

@MainActor private struct GuideNotebook: View {
    let model: LensGuideModel
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Your workbench · \(model.memories.count)/10").font(.headline)
            ForEach(model.memories) { memory in
                HStack(alignment: .top) {
                    Button { model.select(memory) } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(memory.name).font(.headline)
                            Text("Last confirmed: \(memory.place)").font(.subheadline)
                            Text(Date(timeIntervalSince1970: Double(memory.confirmedAtMs) / 1000), format: .dateTime.hour().minute())
                                .font(.caption)
                            if memory.packedAtMs != nil { Label("Packed — confirmed by you", systemImage: "checkmark.circle").font(.caption) }
                        }
                    }.buttonStyle(.plain)
                    Spacer()
                    Button("Forget", role: .destructive) { model.forget(memory.id) }.font(.caption)
                }
                Divider()
            }
            HStack {
                Button("Teach another") { model.teachAnother() }.disabled(model.memories.count >= 10)
                Button("Pack these items") { model.setPhase(.packing) }.disabled(model.memories.isEmpty)
            }
        }
    }
}

@MainActor private struct GuideLifecycleControls: View {
    let model: LensGuideModel
    var body: some View {
        HStack {
            if model.phase == .paused { Button("Resume task") { model.resume() } }
            else { Button("Pause task") { model.pause() } }
            Spacer()
            Button("Forget all", role: .destructive) { model.forget() }
        }.buttonStyle(.bordered)
    }
}

@MainActor private struct PhoneGuidePreview: UIViewRepresentable {
    let model: LensGuideModel
    func makeCoordinator() -> Coordinator { Coordinator(model: model) }
    func makeUIView(context: Context) -> ARSCNView {
        let view = ARSCNView(frame: .zero)
        view.scene = SCNScene()
        view.addGestureRecognizer(UITapGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.tap(_:))))
        model.capture.attachPreview(view)
        return view
    }
    func updateUIView(_ view: ARSCNView, context: Context) { model.capture.attachPreview(view) }
    @MainActor final class Coordinator: NSObject {
        let model: LensGuideModel
        init(model: LensGuideModel) { self.model = model }
        @objc func tap(_ gesture: UITapGestureRecognizer) {
            guard let view = gesture.view as? ARSCNView else { return }
            model.markSurface(at: gesture.location(in: view), in: view)
        }
    }
}
#endif
