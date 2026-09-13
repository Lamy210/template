import Foundation

public enum ProfileMetadataError: Error, Equatable {
    case unsupportedSchemaVersion(Int)
    case emptyProfile
}

public struct ProfileMetadata: Codable, Sendable, Equatable {
    public let schemaVersion: Int
    public let profile: String
    public let runnerOS: String
    public let runnerArch: String
    public let xcodePath: String
    public let xcodeVersion: String
    public let locale: String
    public let language: String
    public let timezone: String
    public let currentSHA: String

    public init(
        schemaVersion: Int,
        profile: String,
        runnerOS: String,
        runnerArch: String,
        xcodePath: String,
        xcodeVersion: String,
        locale: String,
        language: String,
        timezone: String,
        currentSHA: String
    ) {
        self.schemaVersion = schemaVersion
        self.profile = profile
        self.runnerOS = runnerOS
        self.runnerArch = runnerArch
        self.xcodePath = xcodePath
        self.xcodeVersion = xcodeVersion
        self.locale = locale
        self.language = language
        self.timezone = timezone
        self.currentSHA = currentSHA
    }

    public static func load(from url: URL) throws -> ProfileMetadata {
        let metadata = try JSONDecoder().decode(ProfileMetadata.self, from: Data(contentsOf: url))
        guard metadata.schemaVersion == 1 else {
            throw ProfileMetadataError.unsupportedSchemaVersion(metadata.schemaVersion)
        }
        guard !metadata.profile.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw ProfileMetadataError.emptyProfile
        }
        return metadata
    }
}
