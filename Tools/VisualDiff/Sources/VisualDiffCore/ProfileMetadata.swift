import Foundation

public enum ProfileMetadataError: Error, Equatable {
    case unsupportedSchemaVersion(Int)
    case emptyProfile
    case emptyControlledField(String)
    case invalidControlledVersion(String)
    case fingerprintMismatch(expected: String, actual: String)
}

public struct ControlledProfile: Codable, Sendable, Equatable {
    public let runnerFamily: String
    public let architecture: String
    public let xcodePolicy: String
    public let locale: String
    public let language: String
    public let timezone: String
    public let appearance: String
    public let displayScale: String
    public let captureGeometry: String
    public let fixtureVersion: String
    public let captureContractVersion: Int
    public let comparatorSchemaVersion: Int

    public init(
        runnerFamily: String,
        architecture: String,
        xcodePolicy: String,
        locale: String,
        language: String,
        timezone: String,
        appearance: String,
        displayScale: String,
        captureGeometry: String,
        fixtureVersion: String,
        captureContractVersion: Int,
        comparatorSchemaVersion: Int
    ) {
        self.runnerFamily = runnerFamily
        self.architecture = architecture
        self.xcodePolicy = xcodePolicy
        self.locale = locale
        self.language = language
        self.timezone = timezone
        self.appearance = appearance
        self.displayScale = displayScale
        self.captureGeometry = captureGeometry
        self.fixtureVersion = fixtureVersion
        self.captureContractVersion = captureContractVersion
        self.comparatorSchemaVersion = comparatorSchemaVersion
    }

    public var fingerprint: String {
        CanonicalJSON.sha256(self)
    }

    fileprivate func validate() throws {
        let fields = [
            "runnerFamily": runnerFamily,
            "architecture": architecture,
            "xcodePolicy": xcodePolicy,
            "locale": locale,
            "language": language,
            "timezone": timezone,
            "appearance": appearance,
            "displayScale": displayScale,
            "captureGeometry": captureGeometry,
            "fixtureVersion": fixtureVersion,
        ]
        for (name, value) in fields {
            guard !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                throw ProfileMetadataError.emptyControlledField(name)
            }
        }
        guard captureContractVersion > 0 else {
            throw ProfileMetadataError.invalidControlledVersion("captureContractVersion")
        }
        guard comparatorSchemaVersion > 0 else {
            throw ProfileMetadataError.invalidControlledVersion("comparatorSchemaVersion")
        }
    }
}

public struct ObservedRuntime: Codable, Sendable, Equatable {
    public let macOSBuild: String
    public let runnerImageVersion: String
    public let xcodeBuild: String

    public init(
        macOSBuild: String,
        runnerImageVersion: String,
        xcodeBuild: String
    ) {
        self.macOSBuild = macOSBuild
        self.runnerImageVersion = runnerImageVersion
        self.xcodeBuild = xcodeBuild
    }
}

public struct ProfileMetadata: Codable, Sendable, Equatable {
    public let schemaVersion: Int
    public let profile: String
    public let controlled: ControlledProfile
    public let observed: ObservedRuntime
    public let profileFingerprint: String
    public let currentSHA: String

    public init(
        profile: String,
        controlled: ControlledProfile,
        observed: ObservedRuntime,
        currentSHA: String
    ) throws {
        try controlled.validate()
        guard !profile.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw ProfileMetadataError.emptyProfile
        }
        schemaVersion = 2
        self.profile = profile
        self.controlled = controlled
        self.observed = observed
        profileFingerprint = controlled.fingerprint
        self.currentSHA = currentSHA
    }

    public static func decode(_ data: Data) throws -> ProfileMetadata {
        let metadata = try JSONDecoder().decode(ProfileMetadata.self, from: data)
        try metadata.validate()
        return metadata
    }

    public static func load(from url: URL) throws -> ProfileMetadata {
        try decode(Data(contentsOf: url))
    }

    private func validate() throws {
        guard schemaVersion == 2 else {
            throw ProfileMetadataError.unsupportedSchemaVersion(schemaVersion)
        }
        guard !profile.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw ProfileMetadataError.emptyProfile
        }
        try controlled.validate()
        let calculated = controlled.fingerprint
        guard profileFingerprint == calculated else {
            throw ProfileMetadataError.fingerprintMismatch(
                expected: calculated,
                actual: profileFingerprint
            )
        }
    }
}
