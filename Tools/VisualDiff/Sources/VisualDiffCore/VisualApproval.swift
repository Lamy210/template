import Foundation

public enum VisualApprovalError: Error, Equatable {
    case unsupportedSchemaVersion(Int)
    case emptyCaseID
    case invalidDigest(String)
    case emptyProfileFingerprint
    case emptyReason
}

public struct VisualApprovalContext: Sendable, Equatable {
    public let caseID: String
    public let fromDigest: String
    public let toDigest: String
    public let profileFingerprint: String

    public init(
        caseID: String,
        fromDigest: String,
        toDigest: String,
        profileFingerprint: String
    ) {
        self.caseID = caseID
        self.fromDigest = fromDigest
        self.toDigest = toDigest
        self.profileFingerprint = profileFingerprint
    }
}

public struct VisualApproval: Codable, Sendable, Equatable {
    public let schemaVersion: Int
    public let caseID: String
    public let fromDigest: String
    public let toDigest: String
    public let profileFingerprint: String
    public let reason: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion
        case caseID = "caseId"
        case fromDigest
        case toDigest
        case profileFingerprint
        case reason
    }

    public init(
        schemaVersion: Int,
        caseID: String,
        fromDigest: String,
        toDigest: String,
        profileFingerprint: String,
        reason: String
    ) {
        self.schemaVersion = schemaVersion
        self.caseID = caseID
        self.fromDigest = fromDigest
        self.toDigest = toDigest
        self.profileFingerprint = profileFingerprint
        self.reason = reason
    }

    public static func decode(_ data: Data) throws -> VisualApproval {
        let approval = try JSONDecoder().decode(VisualApproval.self, from: data)
        try approval.validate()
        return approval
    }

    public static func load(from url: URL) throws -> VisualApproval {
        try decode(Data(contentsOf: url))
    }

    public func matches(_ context: VisualApprovalContext) -> Bool {
        caseID == context.caseID
            && fromDigest == context.fromDigest
            && toDigest == context.toDigest
            && profileFingerprint == context.profileFingerprint
    }

    private func validate() throws {
        guard schemaVersion == 1 else {
            throw VisualApprovalError.unsupportedSchemaVersion(schemaVersion)
        }
        guard !caseID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw VisualApprovalError.emptyCaseID
        }
        guard Self.isValidDigest(fromDigest) else {
            throw VisualApprovalError.invalidDigest(fromDigest)
        }
        guard Self.isValidDigest(toDigest) else {
            throw VisualApprovalError.invalidDigest(toDigest)
        }
        guard !profileFingerprint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw VisualApprovalError.emptyProfileFingerprint
        }
        guard !reason.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw VisualApprovalError.emptyReason
        }
    }

    private static func isValidDigest(_ value: String) -> Bool {
        let prefix = "sha256:"
        guard value.hasPrefix(prefix) else { return false }
        let hex = value.dropFirst(prefix.count)
        guard hex.count == 64 else { return false }
        return hex.allSatisfy { character in
            character.isNumber || ("a"..."f").contains(character)
        }
    }
}
