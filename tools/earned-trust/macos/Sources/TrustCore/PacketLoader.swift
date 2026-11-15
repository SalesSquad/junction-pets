import CryptoKit
import Foundation

public enum PacketError: LocalizedError {
    case invalid(String)
    public var errorDescription: String? { if case let .invalid(message) = self { return message }; return nil }
}

public enum PacketLoader {
    public static let maxPacketBytes = 5 * 1024 * 1024
    public static let maxLogBytes = 2 * 1024 * 1024
    public static let maxTotalLogBytes = 32 * 1024 * 1024

    public static func digest(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    public static func load(url: URL) throws -> LoadedPacket {
        let data = try boundedData(url, maximum: maxPacketBytes)
        let packet = try decode(data)
        var total = 0
        var integrity: [String: LogIntegrity] = [:]
        for check in packet.checks {
            var reasons: [String] = []
            let base = try verifyLog(path: check.baseLog, expected: check.baseLogSha256,
                                     directory: url.deletingLastPathComponent(), label: "\(check.title), base", total: &total, reasons: &reasons)
            let head = try verifyLog(path: check.headLog, expected: check.headLogSha256,
                                     directory: url.deletingLastPathComponent(), label: "\(check.title), head", total: &total, reasons: &reasons)
            integrity[check.id] = LogIntegrity(baseVerified: base, headVerified: head, reasons: reasons)
        }
        return LoadedPacket(packet: packet, url: url, sha256: digest(data), integrity: integrity,
                            assessments: LedgerEvaluator.evaluate(packet, integrity: integrity))
    }

    public static func decode(_ data: Data) throws -> ReviewPacket {
        guard data.count <= maxPacketBytes else { throw PacketError.invalid("The packet exceeds the 5 MiB limit.") }
        let json = try JSONSerialization.jsonObject(with: data)
        let root = try shape(json, fields: ["schemaVersion", "packetId", "title", "generatedAt", "source", "requirement", "checks", "claims", "files", "provenance", "limitations"], label: "packet")
        _ = try shape(root["source"], fields: ["repository", "baseSha", "headSha", "issueId", "issueURL", "branch"], label: "source")
        _ = try shape(root["requirement"], fields: ["id", "summary", "details"], label: "requirement")
        _ = try shape(root["provenance"], fields: ["toolchain", "origin", "note"], label: "provenance")
        guard let checks = root["checks"] as? [Any], checks.count <= 40,
              let claims = root["claims"] as? [Any], claims.count <= 40,
              let files = root["files"] as? [Any], files.count <= 2000 else {
            throw PacketError.invalid("Invalid collection types or packet limits exceeded.")
        }
        for check in checks {
            _ = try shape(check, fields: ["id", "title", "requirementId", "kind", "evidence", "baseOutcome", "headOutcome", "baseSourceSha", "headSourceSha", "baseHarnessSha256", "headHarnessSha256", "baseLog", "headLog", "baseLogSha256", "headLogSha256", "limitations"], label: "check")
        }
        for claim in claims { _ = try shape(claim, fields: ["id", "title", "requirementId", "kind", "checkIds", "paths"], label: "claim") }
        for file in files { _ = try shape(file, fields: ["path", "role", "additions", "deletions", "group"], label: "file") }
        let packet = try JSONDecoder().decode(ReviewPacket.self, from: data)
        guard packet.schemaVersion == 1 else { throw PacketError.invalid("Unsupported packet schema version.") }
        for string in [packet.packetId, packet.title, packet.generatedAt, packet.requirement.id, packet.requirement.summary,
                       packet.requirement.details, packet.provenance.toolchain, packet.provenance.origin, packet.provenance.note,
                       packet.source.issueId, packet.source.branch] { try nonempty(string) }
        guard ISO8601DateFormatter().date(from: packet.generatedAt) != nil || fractionalDate(packet.generatedAt) != nil else {
            throw PacketError.invalid("The packet timestamp is not ISO 8601.")
        }
        guard approvedGitHubURL(packet.source.repository) != nil, approvedGitHubURL(packet.source.issueURL) != nil else {
            throw PacketError.invalid("Source links must use https://github.com without credentials or ports.")
        }
        try hex(packet.source.baseSha, count: 40); try hex(packet.source.headSha, count: 40)
        guard packet.source.baseSha != packet.source.headSha else { throw PacketError.invalid("Base and changed version must differ.") }
        try unique(packet.checks.map(\.id)); try unique(packet.claims.map(\.id)); try unique(packet.files.map(\.path))
        let checkIDs = Set(packet.checks.map(\.id))
        for check in packet.checks {
            for string in [check.id, check.title, check.requirementId] { try nonempty(string) }
            try hex(check.baseSourceSha, count: 40); try hex(check.headSourceSha, count: 40)
            for hash in [check.baseHarnessSha256, check.headHarnessSha256, check.baseLogSha256, check.headLogSha256].compactMap({ $0 }) { try hex(hash, count: 64) }
            for path in [check.baseLog, check.headLog].compactMap({ $0 }) { try validateRelativePath(path) }
            try strings(check.limitations)
        }
        for claim in packet.claims {
            for string in [claim.id, claim.title, claim.requirementId] { try nonempty(string) }
            guard !claim.checkIds.isEmpty, claim.checkIds.count <= 40, claim.paths.count <= 2000,
                  claim.checkIds.allSatisfy({ checkIDs.contains($0) }) else {
                throw PacketError.invalid("A claim has an absent or invalid check reference.")
            }
            try unique(claim.checkIds)
            for path in claim.paths { try validateRelativePath(path) }
        }
        for file in packet.files {
            try validateRelativePath(file.path); try nonempty(file.group)
            guard file.additions >= 0, file.deletions >= 0, file.additions <= 100_000_000, file.deletions <= 100_000_000 else {
                throw PacketError.invalid("Invalid changed-line counts.")
            }
        }
        try strings(packet.limitations)
        return packet
    }

    public static func approvedGitHubURL(_ string: String) -> URL? {
        guard let url = URL(string: string), url.scheme == "https", url.host == "github.com",
              url.user == nil, url.password == nil, url.port == nil,
              !url.path.isEmpty, url.path != "/" else { return nil }
        return url
    }

    public static func validateRelativePath(_ path: String) throws {
        guard !path.isEmpty, path.utf8.count <= 2048, !path.hasPrefix("/"), !path.contains("\\"),
              !path.contains("\0"), !path.contains(":"),
              !path.split(separator: "/", omittingEmptySubsequences: false).contains(where: { $0.isEmpty || $0 == "." || $0 == ".." }) else {
            throw PacketError.invalid("An evidence path is absolute, ambiguous, or contains traversal.")
        }
    }

    public static func safeEvidenceURL(_ path: String, directory: URL) throws -> URL {
        try validateRelativePath(path)
        let base = directory.resolvingSymlinksInPath().standardizedFileURL
        var candidate = base
        for component in path.split(separator: "/") {
            candidate.appendPathComponent(String(component))
            if let values = try? candidate.resourceValues(forKeys: [.isSymbolicLinkKey]), values.isSymbolicLink == true {
                throw PacketError.invalid("Symbolic links are not permitted in evidence paths.")
            }
        }
        let canonical = candidate.resolvingSymlinksInPath().standardizedFileURL
        guard canonical.path.hasPrefix(base.path + "/") else { throw PacketError.invalid("Evidence escapes the packet directory.") }
        return canonical
    }

    public static func evidenceText(packet: LoadedPacket, check: EvidenceCheck, head: Bool) throws -> String {
        guard let path = head ? check.headLog : check.baseLog,
              let expected = head ? check.headLogSha256 : check.baseLogSha256 else {
            throw PacketError.invalid("This check has no attached evidence file.")
        }
        let url = try safeEvidenceURL(path, directory: packet.url.deletingLastPathComponent())
        let data = try boundedData(url, maximum: maxLogBytes)
        guard digest(data) == expected else { throw PacketError.invalid("Evidence changed or its digest does not match. Reload the packet.") }
        guard let text = String(data: data, encoding: .utf8) else { throw PacketError.invalid("Evidence is not UTF-8 text.") }
        return text
    }

    private static func verifyLog(path: String?, expected: String?, directory: URL, label: String,
                                  total: inout Int, reasons: inout [String]) throws -> Bool {
        guard let path, let expected else { reasons.append("\(label): a log path and digest are required."); return false }
        let url = try safeEvidenceURL(path, directory: directory)
        do {
            let data = try boundedData(url, maximum: maxLogBytes)
            total += data.count
            guard total <= maxTotalLogBytes else { throw PacketError.invalid("Referenced evidence exceeds the total 32 MiB limit.") }
            guard digest(data) == expected else { reasons.append("\(label): local log digest does not match."); return false }
            return true
        } catch let error as PacketError { throw error }
        catch { reasons.append("\(label): log file cannot be read."); return false }
    }

    private static func boundedData(_ url: URL, maximum: Int) throws -> Data {
        let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true else { throw PacketError.invalid("Only regular files are accepted.") }
        guard let size = values.fileSize, size <= maximum else { throw PacketError.invalid("An input file exceeds its size limit.") }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let data = try handle.read(upToCount: maximum + 1) ?? Data()
        guard data.count <= maximum else { throw PacketError.invalid("An input file exceeds its size limit.") }
        return data
    }
    private static func shape(_ value: Any?, fields: Set<String>, label: String) throws -> [String: Any] {
        guard let object = value as? [String: Any], Set(object.keys) == fields else { throw PacketError.invalid("Invalid \(label) fields.") }
        return object
    }
    private static func nonempty(_ string: String) throws {
        guard !string.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, string.utf8.count <= 20_000 else {
            throw PacketError.invalid("A required string is empty or too long.")
        }
    }
    private static func strings(_ values: [String]) throws {
        guard values.count <= 100 else { throw PacketError.invalid("Too many limitations.") }
        for value in values { try nonempty(value) }
    }
    private static func unique(_ values: [String]) throws {
        guard Set(values).count == values.count else { throw PacketError.invalid("Duplicate identifiers are not allowed.") }
    }
    private static func hex(_ value: String, count: Int) throws {
        guard value.count == count, value.unicodeScalars.allSatisfy({ (48...57).contains($0.value) || (97...102).contains($0.value) }) else {
            throw PacketError.invalid("A source SHA or digest is invalid.")
        }
    }
    private static func fractionalDate(_ value: String) -> Date? {
        let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: value)
    }
}
