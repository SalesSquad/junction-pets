import Foundation

public enum LedgerEvaluator {
    public static func evaluate(_ packet: ReviewPacket, integrity: [String: LogIntegrity]) -> [ClaimAssessment] {
        let checks = Dictionary(uniqueKeysWithValues: packet.checks.map { ($0.id, $0) })
        return packet.claims.map { claim in
            if claim.kind == .structural {
                return ClaimAssessment(id: claim.id, title: claim.title, verdict: .inspectionOnly,
                                       reasons: ["A structural classification narrows review scope; it does not establish runtime behavior."])
            }
            var reasons: [String] = []
            var hasProof = false
            if claim.requirementId != packet.requirement.id { reasons.append("Claim names a different requirement.") }
            for id in claim.checkIds {
                guard let check = checks[id] else { reasons.append("Referenced check is absent: \(id)."); continue }
                if check.requirementId != packet.requirement.id { reasons.append("\(check.title): wrong requirement.") }
                if check.baseSourceSha != packet.source.baseSha || check.headSourceSha != packet.source.headSha {
                    reasons.append("\(check.title): source versions do not match this change.")
                }
                if check.evidence != .observed { reasons.append("\(check.title): \(check.evidence.rawValue) evidence is not direct behavioral proof.") }
                if check.kind == .structural {
                    reasons.append("\(check.title): source inspection alone cannot establish this behavioral claim.")
                    continue
                }
                if check.baseHarnessSha256 == nil || check.baseHarnessSha256 != check.headHarnessSha256 {
                    reasons.append("\(check.title): the identical frozen test harness is not established.")
                }
                if integrity[id]?.verified != true {
                    reasons.append(contentsOf: integrity[id]?.reasons ?? ["\(check.title): local log bytes have not been verified."])
                }
                if check.baseOutcome == .error || check.headOutcome == .error {
                    reasons.append("\(check.title): an execution error is not a behavioral test failure.")
                } else if check.baseOutcome == .notRun || check.headOutcome == .notRun {
                    reasons.append("\(check.title): both versions have not been executed.")
                } else if check.headOutcome == .fail {
                    reasons.append("\(check.title): the changed version fails the check.")
                } else if claim.kind == .fix && check.kind == .differential {
                    if check.baseOutcome == .fail && check.headOutcome == .pass { hasProof = true }
                    else { reasons.append("\(check.title): pass → pass does not demonstrate a fix.") }
                } else if claim.kind == .invariant && check.kind == .regression {
                    if check.baseOutcome == .pass && check.headOutcome == .pass { hasProof = true }
                    else { reasons.append("\(check.title): preserved behavior requires pass → pass.") }
                } else if claim.kind == .fix && check.kind == .regression {
                    if check.baseOutcome != .pass || check.headOutcome != .pass {
                        reasons.append("\(check.title): the supporting regression does not preserve behavior.")
                    }
                } else {
                    reasons.append("\(check.title): this check kind does not establish the claimed behavior.")
                }
            }
            if !hasProof { reasons.append(claim.kind == .fix ? "A frozen fail → pass check is still needed." : "A frozen pass → pass regression is still needed.") }
            let unique = Array(Set(reasons)).sorted()
            return ClaimAssessment(id: claim.id, title: claim.title,
                                   verdict: unique.isEmpty && hasProof ? .ready : .needsEvidence, reasons: unique)
        }
    }
}
