import Foundation
import TrustCore

struct Inspection: Encodable {
    let packetId: String
    let packetSHA256: String
    let verdict: ReviewVerdict
    let files: Int
    let generatedSnapshots: Int
    let verifiedLogPairs: Int
    let claims: [ClaimAssessment]
    let note: String
}

do {
    guard CommandLine.arguments.count == 2 else { throw PacketError.invalid("Usage: trust-inspect /absolute/path/to/packet.json") }
    let loaded = try PacketLoader.load(url: URL(fileURLWithPath: CommandLine.arguments[1]))
    let result = Inspection(packetId: loaded.id, packetSHA256: loaded.sha256, verdict: loaded.verdict,
                            files: loaded.packet.files.count, generatedSnapshots: loaded.generatedFiles,
                            verifiedLogPairs: loaded.verifiedLogPairs, claims: loaded.assessments,
                            note: "Local byte integrity is not authenticated runner provenance or code approval.")
    let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    print(String(decoding: try encoder.encode(result), as: UTF8.self))
} catch {
    FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
    exit(2)
}
