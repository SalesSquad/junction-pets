import AppKit
import SwiftUI
import TrustCore
import UniformTypeIdentifiers

struct ContentView: View {
    @State private var store = ReviewStore()
    @State private var showImporter = false
    @State private var showDecision = false
    @State private var showInspector = true
    @State private var showExporter = false
    @State private var pendingExport = false
    @State private var exportDocument = ReviewExportDocument()
    @State private var exportName = "earned-trust-review.json"
    @State private var containingWindow = WeakWindowReference()

    var body: some View {
        @Bindable var store = store
        NavigationSplitView {
            SidebarView(store: store)
                .navigationSplitViewColumnWidth(min: 230, ideal: 250, max: 290)
        } detail: {
            Group {
                if let packet = store.selected {
                    ReviewDetailView(packet: packet, decision: store.selectedDecision, recordDecision: { showDecision = true })
                        .id(packet.sha256)
                } else {
                    ContentUnavailableView("Open a change", systemImage: "doc.text.magnifyingglass",
                                           description: Text("Choose a supplied change or import a review packet."))
                }
            }
            .inspector(isPresented: $showInspector) {
                if let packet = store.selected { ProvenanceView(packet: packet).inspectorColumnWidth(min: 250, ideal: 280, max: 340) }
            }
            .toolbar {
                ToolbarItemGroup {
                    Button { showImporter = true } label: { Label("Import", systemImage: "square.and.arrow.down") }
                        .help("Import a JSON packet and verify its local evidence")
                    Button { store.reload() } label: { Label("Reload", systemImage: "arrow.clockwise") }.disabled(store.selected == nil)
                    Button { showDecision = true } label: { Label("Record Review", systemImage: "person.crop.circle.badge.checkmark") }
                        .disabled(store.selected == nil)
                    Button { showInspector.toggle() } label: { Label("Provenance", systemImage: "sidebar.right") }
                }
            }
        }
        .navigationTitle("Earned Trust")
        .background(WindowReader { containingWindow.value = $0 }.frame(width: 0, height: 0))
        .task { store.loadBundled() }
        .fileImporter(isPresented: $showImporter, allowedContentTypes: [.json]) { result in
            switch result { case .success(let url): store.importPacket(url); case .failure(let error): store.error = error.localizedDescription }
        }
        .sheet(isPresented: $showDecision, onDismiss: {
            if pendingExport { pendingExport = false; showExporter = true }
        }) {
            if let packet = store.selected {
                DecisionSheet(packet: packet) { reviewer, decision, rationale in
                    let record = try store.record(reviewer: reviewer, decision: decision, rationale: rationale)
                    exportDocument = ReviewExportDocument(data: try record.data())
                    exportName = "earned-trust-\(packet.packet.source.issueId)-review.json"
                    pendingExport = true
                    showDecision = false
                }
            }
        }
        .fileExporter(isPresented: $showExporter, document: exportDocument, contentType: .json, defaultFilename: exportName) { result in
            if case .failure(let error) = result { store.error = error.localizedDescription }
        }
        .alert("Review packet", isPresented: Binding(get: { store.error != nil }, set: { if !$0 { store.error = nil } })) {
            Button("OK", role: .cancel) { store.error = nil }
        } message: { Text(store.error ?? "") }
        .onReceive(NotificationCenter.default.publisher(for: .importReviewPacket)) { _ in if isKeyWindow { showImporter = true } }
        .onReceive(NotificationCenter.default.publisher(for: .recordReviewDecision)) { _ in if isKeyWindow && store.selected != nil { showDecision = true } }
        .onReceive(NotificationCenter.default.publisher(for: .reloadReviewEvidence)) { _ in if isKeyWindow { store.reload() } }
    }

    private var isKeyWindow: Bool { containingWindow.value?.isKeyWindow == true }
}
