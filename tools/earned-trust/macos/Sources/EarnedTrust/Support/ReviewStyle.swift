import SwiftUI
import TrustCore

extension ReviewVerdict {
    var color: Color {
        switch self { case .ready: return .green; case .needsEvidence: return .orange; case .inspectionOnly: return .blue }
    }
    var icon: String {
        switch self { case .ready: return "checkmark.shield"; case .needsEvidence: return "exclamationmark.shield"; case .inspectionOnly: return "doc.text.magnifyingglass" }
    }
    var sentence: String {
        switch self {
        case .ready: return "The recorded evidence supports review. A person still owns the decision."
        case .needsEvidence: return "The available checks do not yet establish every claim."
        case .inspectionOnly: return "The change is mapped. Its behavior still needs evidence."
        }
    }
}

extension CheckOutcome {
    var label: String {
        switch self { case .pass: return "Pass"; case .fail: return "Fail"; case .notRun: return "Not run"; case .error: return "Error" }
    }
    var color: Color {
        switch self { case .pass: return .green; case .fail: return .orange; case .notRun: return .secondary; case .error: return .red }
    }
}

struct SectionHeading: View {
    let title: String
    let subtitle: String
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.title3.weight(.semibold))
            Text(subtitle).font(.callout).foregroundStyle(.secondary)
        }
    }
}

struct Surface<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        content.padding(20).frame(maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(.quaternary, lineWidth: 1))
    }
}

struct VerdictBadge: View {
    let verdict: ReviewVerdict
    var body: some View {
        Label(verdict.rawValue, systemImage: verdict.icon)
            .font(.caption.weight(.bold)).tracking(0.6)
            .foregroundStyle(verdict.color)
            .padding(.horizontal, 11).padding(.vertical, 7)
            .background(verdict.color.opacity(0.1), in: Capsule())
    }
}
