import SwiftUI
import ChibiLensCore

/// A runnable first-party replay surface, not a live Meta DAT device interface.
public struct LensReplayView: View {
    @State private var phase: LensDemoPhase = .history

    public init() {}

    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    titleBlock
                    statusCard
                    timelineCard
                    explanationCard
                    controls
                }
                .frame(maxWidth: 660, alignment: .leading)
                .padding(24)
                .frame(maxWidth: .infinity)
            }
            .navigationTitle("Chibi Lens")
        }
    }

    private var titleBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Memory for the physical world", systemImage: "eye.circle")
                .font(.headline)
                .foregroundStyle(.secondary)
            Text(phase.title)
                .font(.system(size: 32, weight: .semibold, design: .rounded))
                .fixedSize(horizontal: false, vertical: true)
            Text("With evidence. Without guesses.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(phase.sourceLabel, systemImage: "checkmark.shield")
                .font(.caption.weight(.bold))
                .foregroundStyle(.orange)
            Text(phase.answer)
                .font(.title3)
                .fixedSize(horizontal: false, vertical: true)

            if phase == .lookalikes {
                Label("Ambiguous — never auto-verified", systemImage: "questionmark.diamond")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.orange)
            } else if phase == .revoked {
                Label("Capture stopped; use text fallback", systemImage: "hand.raised")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.red)
            } else {
                Label("Historical sighting, not a live position", systemImage: "clock")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 22))
        .accessibilityElement(children: .combine)
    }

    private var timelineCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Evidence timeline")
                .font(.headline)
            ForEach(LensDemoFixture.history, id: \.id) { sighting in
                HStack(alignment: .firstTextBaseline) {
                    Image(systemName: "mappin.circle")
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(sighting.zone)
                            .font(.body.weight(.semibold))
                        Text("Observed event · \(sighting.id)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    if sighting.id == "sight-newer" {
                        Text("Latest")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.secondary)
                    }
                }
                .accessibilityElement(children: .combine)
                if sighting.id != "sight-older" { Divider() }
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 22))
    }

    private var explanationCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Why the answer is cautious", systemImage: "info.circle")
                .font(.headline)
            Text("The app suggests candidates. Only the authenticated host can verify a unique identifier against a fresh, permitted observation. No model score grants access or proves identity.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }

    private var controls: some View {
        HStack(spacing: 12) {
            Button {
                phase = phase.next()
            } label: {
                Label("Next replay step", systemImage: "arrow.right")
            }
            .buttonStyle(.borderedProminent)

            Button("Reset") { phase = .history }
                .buttonStyle(.bordered)
        }
        .accessibilityHint("All scenes are synthetic and do not start camera capture")
    }
}
