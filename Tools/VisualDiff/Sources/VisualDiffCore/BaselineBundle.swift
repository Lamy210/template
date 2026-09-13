import Foundation

public struct BaselineBundleCase: Codable, Sendable, Equatable {
    public let id: String
    public let digest: String

    public init(id: String, digest: String) {
        self.id = id
        self.digest = digest
    }
}

public struct BaselineBundleManifest: Codable, Sendable, Equatable {
    public let schemaVersion: Int
    public let sourceRepository: String
    public let workflow: String
    public let sourceRunID: String
    public let runAttempt: Int
    public let sourceSHA: String
    public let profileFingerprint: String
    public let previousBaselineReference: String?
    public let cases: [BaselineBundleCase]

    public init(
        schemaVersion: Int,
        sourceRepository: String,
        workflow: String,
        sourceRunID: String,
        runAttempt: Int,
        sourceSHA: String,
        profileFingerprint: String,
        previousBaselineReference: String?,
        cases: [BaselineBundleCase]
    ) {
        self.schemaVersion = schemaVersion
        self.sourceRepository = sourceRepository
        self.workflow = workflow
        self.sourceRunID = sourceRunID
        self.runAttempt = runAttempt
        self.sourceSHA = sourceSHA
        self.profileFingerprint = profileFingerprint
        self.previousBaselineReference = previousBaselineReference
        self.cases = cases
    }

    public static func decode(_ data: Data) throws -> BaselineBundleManifest {
        let manifest = try JSONDecoder().decode(BaselineBundleManifest.self, from: data)
        guard manifest.schemaVersion == 1 else {
            throw BaselineBundleError.unsupportedSchemaVersion(manifest.schemaVersion)
        }
        return manifest
    }
}

public struct ValidatedBaselineBundle: Sendable, Equatable {
    public let manifest: BaselineBundleManifest
    public let caseDigests: [String: String]

    public init(manifest: BaselineBundleManifest, caseDigests: [String: String]) {
        self.manifest = manifest
        self.caseDigests = caseDigests
    }
}

public enum BaselineBundleError: Error, Equatable {
    case unsupportedSchemaVersion(Int)
    case invalidManifestField(String)
    case profileMismatch(expected: String, actual: String)
    case duplicateCaseID(String)
    case invalidCaseID(String)
    case invalidDigest(caseID: String, digest: String)
    case missingImagesDirectory
    case missingImage(caseID: String)
    case notRegularImage(caseID: String)
    case digestMismatch(caseID: String, expected: String, actual: String)
    case unexpectedImage(String)
}

public enum BaselineBundleValidator {
    public static func validate(
        root: URL,
        manifest: BaselineBundleManifest,
        expectedProfileFingerprint: String,
        strict: Bool
    ) throws -> ValidatedBaselineBundle {
        try validateManifestMetadata(manifest)
        guard manifest.profileFingerprint == expectedProfileFingerprint else {
            throw BaselineBundleError.profileMismatch(
                expected: expectedProfileFingerprint,
                actual: manifest.profileFingerprint
            )
        }

        let caseDigests = try validateCases(manifest.cases)
        let imagesRoot = root.appendingPathComponent("images", isDirectory: true)
        guard try isDirectoryWithoutSymlink(imagesRoot) else {
            throw BaselineBundleError.missingImagesDirectory
        }

        for testCase in manifest.cases {
            let imageURL = imagesRoot.appendingPathComponent("\(testCase.id).png", isDirectory: false)
            guard FileManager.default.fileExists(atPath: imageURL.path) else {
                throw BaselineBundleError.missingImage(caseID: testCase.id)
            }
            guard try isRegularFileWithoutSymlink(imageURL) else {
                throw BaselineBundleError.notRegularImage(caseID: testCase.id)
            }
            let actualDigest = try ImageDigest.sha256(fileAt: imageURL)
            guard actualDigest == testCase.digest else {
                throw BaselineBundleError.digestMismatch(
                    caseID: testCase.id,
                    expected: testCase.digest,
                    actual: actualDigest
                )
            }
        }

        if strict {
            try rejectUnexpectedImages(in: imagesRoot, declaredCaseIDs: Set(caseDigests.keys))
        }

        return ValidatedBaselineBundle(manifest: manifest, caseDigests: caseDigests)
    }

    private static func validateManifestMetadata(_ manifest: BaselineBundleManifest) throws {
        guard manifest.schemaVersion == 1 else {
            throw BaselineBundleError.unsupportedSchemaVersion(manifest.schemaVersion)
        }
        guard !manifest.sourceRepository.isEmpty,
              manifest.sourceRepository.contains("/"),
              !manifest.workflow.isEmpty,
              !manifest.sourceRunID.isEmpty,
              manifest.runAttempt > 0,
              isGitSHA(manifest.sourceSHA),
              isSHA256(manifest.profileFingerprint)
        else {
            throw BaselineBundleError.invalidManifestField("provenance")
        }
        if let previous = manifest.previousBaselineReference, previous.isEmpty {
            throw BaselineBundleError.invalidManifestField("previousBaselineReference")
        }
    }

    private static func validateCases(_ cases: [BaselineBundleCase]) throws -> [String: String] {
        var digests: [String: String] = [:]
        for testCase in cases {
            guard isSafeCaseID(testCase.id) else {
                throw BaselineBundleError.invalidCaseID(testCase.id)
            }
            guard isSHA256(testCase.digest) else {
                throw BaselineBundleError.invalidDigest(caseID: testCase.id, digest: testCase.digest)
            }
            guard digests[testCase.id] == nil else {
                throw BaselineBundleError.duplicateCaseID(testCase.id)
            }
            digests[testCase.id] = testCase.digest
        }
        return digests
    }

    private static func rejectUnexpectedImages(
        in imagesRoot: URL,
        declaredCaseIDs: Set<String>
    ) throws {
        let children = try FileManager.default.contentsOfDirectory(
            at: imagesRoot,
            includingPropertiesForKeys: [.isDirectoryKey, .isRegularFileKey, .isSymbolicLinkKey],
            options: []
        )
        let expectedNames = Set(declaredCaseIDs.map { "\($0).png" })
        for child in children {
            guard expectedNames.contains(child.lastPathComponent) else {
                throw BaselineBundleError.unexpectedImage(child.lastPathComponent)
            }
        }
    }

    private static func isSafeCaseID(_ id: String) -> Bool {
        guard !id.isEmpty, id.count <= 128 else {
            return false
        }
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
        guard id.unicodeScalars.allSatisfy(allowed.contains) else {
            return false
        }
        return id != "." && id != ".." && !id.hasPrefix(".")
    }

    private static func isSHA256(_ value: String) -> Bool {
        guard value.hasPrefix("sha256:") else {
            return false
        }
        let hex = value.dropFirst("sha256:".count)
        guard hex.count == 64 else {
            return false
        }
        return hex.allSatisfy { character in
            character.isNumber || ("a" ... "f").contains(character)
        }
    }

    private static func isGitSHA(_ value: String) -> Bool {
        guard value.count == 40 else {
            return false
        }
        return value.allSatisfy { character in
            character.isNumber || ("a" ... "f").contains(character)
        }
    }

    private static func isDirectoryWithoutSymlink(_ url: URL) throws -> Bool {
        let values = try url.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        return values.isDirectory == true && values.isSymbolicLink != true
    }

    private static func isRegularFileWithoutSymlink(_ url: URL) throws -> Bool {
        let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
        return values.isRegularFile == true && values.isSymbolicLink != true
    }
}
