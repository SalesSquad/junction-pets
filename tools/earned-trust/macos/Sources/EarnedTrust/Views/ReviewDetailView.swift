import SwiftUI
import TrustCore

struct ReviewDetailView: View {
    let packet: LoadedPacket
    let decision: ReviewDecision?
    let recordDecision: () -> Void
    @State private var selectedTab = "Evidence"

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                header
                requirement
                HStack(spacing: 12) {
                    metric("Claims", value: "\(packet.packet.claims.count)", icon: "text.alignleft")
                    metric("Verified log pairs", value: "\(packet.verifiedLogPairs)", icon: "checkmark.seal")
                    metric("Changed files", value: "\(packet.packet.files.count)", icon: "doc.on.doc")
                }
                Picker("Review section", selection: $selectedTab) {
                    Text("Evidence").tag("Evidence")
                    Text("Change map").tag("Change map")
                    Text("Limits & decision").tag("Limits & decision")
                }.pickerStyle(.segmented).frame(maxWidth: 500)
                switch selectedTab {
                case "Change map": FileChangesView(packet: packet)
                case "Limits & decision": limitations
                default:
                    VStack(alignment: .leading, spacing: 16) {
                        SectionHeading(title: "What the evidence earns", subtitle: "Each claim is checked against its requirement and exact source versions.")
                        ForEach(packet.assessments) { claim in
                            Surface {
                                VStack(alignment: .leading, spacing: 12) {
                                    HStack(alignment: .top) {
                                        Text(claim.title).font(.headline)
                                        Spacer(minLength: 12)
                                        VerdictBadge(verdict: claim.verdict)
                                    }
                                    if claim.reasons.isEmpty {
                                        Label("Declared source and harness IDs match; attached log bytes verified. Inspect outcomes before deciding.", systemImage: "checkmark.circle")
                                            .font(.callout).foregroundStyle(.secondary)
                                    }
                                    ForEach(Array(claim.reasons.enumerated()), id: \.offset) { _, reason in
                                        Label(reason, systemImage: "arrow.turn.down.right")
                                            .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                                    }
                                }
                            }
                        }
                        SectionHeading(title: "Before → after", subtitle: "A fix needs a discriminating check. A regression check shows what stays true.")
                        ForEach(packet.packet.checks) { check in
                            EvidenceCheckView(packet: packet, check: check, integrity: packet.integrity[check.id])
                        }
                    }
                }
            }.padding(30).frame(maxWidth: 1050, alignment: .leading).frame(maxWidth: .infinity)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("CHANGE / \(packet.packet.source.issueId)").font(.caption.weight(.semibold)).tracking(1.8).foregroundStyle(.secondary)
                Spacer()
                VerdictBadge(verdict: packet.verdict)
            }
            Text(packet.packet.title).font(.system(size: 30, weight: .semibold, design: .rounded))
                .fixedSize(horizontal: false, vertical: true)
            Text(packet.verdict.sentence).font(.title3).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var requirement: some View {
        Surface {
            HStack(alignment: .top, spacing: 15) {
                Image(systemName: "scope").font(.title2).foregroundStyle(.tint).padding(.top, 2)
                VStack(alignment: .leading, spacing: 8) {
                    Text(packet.packet.requirement.id).font(.caption.monospaced().weight(.medium)).foregroundStyle(.secondary)
                    Text(packet.packet.requirement.summary).font(.headline).fixedSize(horizontal: false, vertical: true)
                    Text(packet.packet.requirement.details).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func metric(_ label: String, value: String, icon: String) -> some View {
        Surface {
            VStack(alignment: .leading, spacing: 10) {
                Label(label, systemImage: icon).font(.caption).foregroundStyle(.secondary)
                Text(value).font(.system(.title, design: .rounded).weight(.medium)).monospacedDigit()
            }
        }
    }

    private var limitations: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeading(title: "What this review cannot decide", subtitle: "Keep the boundary between a test result and an engineering judgment visible.")
            Surface {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(Array(packet.packet.limitations.enumerated()), id: \.offset) { _, text in
                        Label(text, systemImage: "minus.circle").font(.callout).fixedSize(horizontal: false, vertical: true)
                    }
                    Label("Log hashes confirm local byte integrity. They do not authenticate the runner or prove that a log is truthful.", systemImage: "person.crop.circle.badge.questionmark")
                        .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
            }
            Surface {
                VStack(alignment: .leading, spacing: 14) {
                    Label("A named person owns the next step", systemImage: "person.crop.circle").font(.headline)
                    if let decision {
                        Text("\(decision.declaredReviewer) · \(decision.decision.rawValue)").font(.callout.weight(.medium))
                        Text(decision.rationale).font(.callout).foregroundStyle(.secondary)
                    } else {
                        Text("No human decision has been recorded for this packet.").foregroundStyle(.secondary)
                    }
                    Button("Record a local review…", action: recordDecision).buttonStyle(.borderedProminent)
                    Text("A declaration is exported to a file. It does not authenticate an identity, approve code or merge anything.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
    }
}
