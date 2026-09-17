import Foundation

public enum ManifestRunnerError: Error, Equatable {
    case profileMismatch(expected: String, actual: String)
    case rollingProfileMismatch(expected: String, actual: String)
    case rollingProfileFingerprintMismatch(expected: String, actual: String)
    case missingRollingProfile
    case missingRollingBundleManifest
    case missingCurrentCapture(caseID: String, path: String)
    case missingGitBaseline(caseID: String, path: String)
    case missingRollingBaseline(caseID: String)
    case missingApproval(caseID: String, path: String)
    case unsafeResolvedPath(String)
    case notRegularFile(String)
}

public enum VisualCaseStatus: String, Codable, Sendable, Equatable {
    case passed
    case failed
    case approvedChange = "approved-change"
    case bootstrap
}

public struct VisualCaseRunReport: Codable, Sendable, Equatable {
    public let caseID: String
    public let baseline: BaselineSource
    public let baselineReference: String
    public let currentSHA: String
    public let profile: String
    public let profileFingerprint: String
    public let status: VisualCaseStatus
    public let maxChangedPixelRatio: Double
    public let maxChannelDeltaThreshold: Int
    public let expectedDigest: String?
    public let actualDigest: String?
    public let approvalPath: String?
    public let approvalReason: String?
    public let dimensionMismatch: Bool?
    public let expectedWidth: Int?
    public let expectedHeight: Int?
    public let actualWidth: Int?
    public let actualHeight: Int?
    public let changedPixelCount: Int?
    public let changedPixelRatio: Double?
    public let maxChannelDelta: Int?
}

public struct ManifestRunSummary: Sendable, Equatable {
    public let cases: [VisualCaseRunReport]

    public var hasFailures: Bool {
        cases.contains { $0.status == .failed }
    }
}

public struct ManifestRunConfiguration: Sendable, Equatable {
    public let repoRoot: URL
    public let currentProfileURL: URL
    public let rollingRoot: URL?
    public let rollingProfileURL: URL?
    public let outputRoot: URL
    public let currentSHA: String
    public let baselineRunID: String?
    public let bootstrapRolling: Bool

    public init(
        repoRoot: URL,
        currentProfileURL: URL,
        rollingRoot: URL?,
        rollingProfileURL: URL?,
        outputRoot: URL,
        currentSHA: String,
        baselineRunID: String?,
        bootstrapRolling: Bool
    ) {
        self.repoRoot = repoRoot
        self.currentProfileURL = currentProfileURL
        self.rollingRoot = rollingRoot
        self.rollingProfileURL = rollingProfileURL
        self.outputRoot = outputRoot
        self.currentSHA = currentSHA
        self.baselineRunID = baselineRunID
        self.bootstrapRolling = bootstrapRolling
    }
}

struct ManifestExecutionProfile: Sendable, Equatable {
    let label: String
    let fingerprint: String
}

struct ManifestValidatedContext: Sendable, Equatable {
    let executionProfile: ManifestExecutionProfile
    let rollingBaseline: ValidatedBaselineBundle?
}

public enum ManifestRunner {
    public static func run(
        manifest: VisualManifest,
        configuration: ManifestRunConfiguration
    ) throws -> ManifestRunSummary {
        let context = try validateContext(
            manifest: manifest,
            configuration: configuration
        )
        try FileManager.default.createDirectory(
            at: configuration.outputRoot,
            withIntermediateDirectories: true
        )

        var reports: [VisualCaseRunReport] = []
        for testCase in manifest.cases {
            try reports.append(ManifestCaseExecutor.run(
                testCase,
                executionProfile: context.executionProfile,
                rollingBaseline: context.rollingBaseline,
                configuration: configuration
            ))
        }
        return ManifestRunSummary(cases: reports)
    }

    private static func validateContext(
        manifest: VisualManifest,
        configuration: ManifestRunConfiguration
    ) throws -> ManifestValidatedContext {
        let currentProfile = try ProfileMetadata.load(from: configuration.currentProfileURL)
        guard currentProfile.profile == manifest.profile else {
            throw ManifestRunnerError.profileMismatch(
                expected: manifest.profile,
                actual: currentProfile.profile
            )
        }

        let executionProfile = ManifestExecutionProfile(
            label: currentProfile.profile,
            fingerprint: currentProfile.profileFingerprint
        )
        let rollingBaseline = try validateRollingBaseline(
            manifest: manifest,
            executionProfile: executionProfile,
            configuration: configuration
        )
        return ManifestValidatedContext(
            executionProfile: executionProfile,
            rollingBaseline: rollingBaseline
        )
    }

    private static func validateRollingBaseline(
        manifest: VisualManifest,
        executionProfile: ManifestExecutionProfile,
        configuration: ManifestRunConfiguration
    ) throws -> ValidatedBaselineBundle? {
        let rollingCases = manifest.cases.filter { $0.baseline == .rollingMain }
        guard let firstRollingCase = rollingCases.first else {
            return nil
        }
        guard let rollingRoot = configuration.rollingRoot else {
            if configuration.bootstrapRolling {
                return nil
            }
            throw ManifestRunnerError.missingRollingBaseline(caseID: firstRollingCase.id)
        }
        guard let rollingProfileURL = configuration.rollingProfileURL else {
            throw ManifestRunnerError.missingRollingProfile
        }

        let rollingProfile = try ProfileMetadata.load(from: rollingProfileURL)
        guard rollingProfile.profile == manifest.profile else {
            throw ManifestRunnerError.rollingProfileMismatch(
                expected: manifest.profile,
                actual: rollingProfile.profile
            )
        }
        guard rollingProfile.profileFingerprint == executionProfile.fingerprint else {
            throw ManifestRunnerError.rollingProfileFingerprintMismatch(
                expected: executionProfile.fingerprint,
                actual: rollingProfile.profileFingerprint
            )
        }

        let bundleManifestURL = rollingRoot.appendingPathComponent(
            "bundle-manifest.json",
            isDirectory: false
        )
        guard ManifestPathResolver.isRegularFile(bundleManifestURL) else {
            throw ManifestRunnerError.missingRollingBundleManifest
        }
        let bundleManifest = try BaselineBundleManifest.decode(Data(contentsOf: bundleManifestURL))
        return try BaselineBundleValidator.validate(
            root: rollingRoot,
            manifest: bundleManifest,
            expectedProfileFingerprint: executionProfile.fingerprint,
            strict: true
        )
    }
}
