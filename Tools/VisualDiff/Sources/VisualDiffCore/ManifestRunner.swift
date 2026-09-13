import Foundation

public enum ManifestRunnerError: Error, Equatable {
    case profileMismatch(expected: String, actual: String)
    case rollingProfileMismatch(expected: String, actual: String)
    case missingRollingProfile
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

public enum ManifestRunner {
    public static func run(
        manifest: VisualManifest,
        configuration: ManifestRunConfiguration
    ) throws -> ManifestRunSummary {
        try validateProfiles(manifest: manifest, configuration: configuration)
        try FileManager.default.createDirectory(
            at: configuration.outputRoot,
            withIntermediateDirectories: true
        )

        var reports: [VisualCaseRunReport] = []
        for testCase in manifest.cases {
            try reports.append(runCase(
                testCase,
                profile: manifest.profile,
                configuration: configuration
            ))
        }
        return ManifestRunSummary(cases: reports)
    }

    private static func validateProfiles(
        manifest: VisualManifest,
        configuration: ManifestRunConfiguration
    ) throws {
        let currentProfile = try ProfileMetadata.load(from: configuration.currentProfileURL)
        guard currentProfile.profile == manifest.profile else {
            throw ManifestRunnerError.profileMismatch(
                expected: manifest.profile,
                actual: currentProfile.profile
            )
        }

        let hasRollingCases = manifest.cases.contains { $0.baseline == .rollingMain }
        guard hasRollingCases, configuration.rollingRoot != nil else {
            return
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
    }

    private static func runCase(
        _ testCase: VisualCase,
        profile: String,
        configuration: ManifestRunConfiguration
    ) throws -> VisualCaseRunReport {
        let currentURL = try confinedRepositoryURL(
            repoRoot: configuration.repoRoot,
            relativePath: testCase.current,
            allowedRelativeRoot: "artifacts/visual/current"
        )
        try requireRegularFile(
            currentURL,
            missingError: .missingCurrentCapture(caseID: testCase.id, path: testCase.current)
        )

        switch testCase.baseline {
        case .git:
            return try runGitCase(
                testCase,
                currentURL: currentURL,
                profile: profile,
                configuration: configuration
            )
        case .rollingMain:
            return try runRollingCase(
                testCase,
                currentURL: currentURL,
                profile: profile,
                configuration: configuration
            )
        }
    }

    private static func runGitCase(
        _ testCase: VisualCase,
        currentURL: URL,
        profile: String,
        configuration: ManifestRunConfiguration
    ) throws -> VisualCaseRunReport {
        guard let expectedPath = testCase.expected else {
            throw ManifestRunnerError.missingGitBaseline(caseID: testCase.id, path: "")
        }
        let expectedURL = try confinedRepositoryURL(
            repoRoot: configuration.repoRoot,
            relativePath: expectedPath,
            allowedRelativeRoot: "Tests/VisualBaselines"
        )
        try requireRegularFile(
            expectedURL,
            missingError: .missingGitBaseline(caseID: testCase.id, path: expectedPath)
        )
        return try compareAndWrite(
            testCase: testCase,
            expectedURL: expectedURL,
            currentURL: currentURL,
            baselineReference: "git:\(expectedPath)",
            profile: profile,
            configuration: configuration
        )
    }

    private static func runRollingCase(
        _ testCase: VisualCase,
        currentURL: URL,
        profile: String,
        configuration: ManifestRunConfiguration
    ) throws -> VisualCaseRunReport {
        guard let rollingRoot = configuration.rollingRoot else {
            return try bootstrapOrThrow(
                testCase,
                currentURL: currentURL,
                profile: profile,
                configuration: configuration
            )
        }

        let expectedURL = try confinedChildURL(
            root: rollingRoot,
            childName: "\(testCase.id).png"
        )
        guard isRegularFile(expectedURL) else {
            return try bootstrapOrThrow(
                testCase,
                currentURL: currentURL,
                profile: profile,
                configuration: configuration
            )
        }

        let baselineReference = configuration.baselineRunID.map { "run:\($0)" } ?? "rolling-main"
        return try compareAndWrite(
            testCase: testCase,
            expectedURL: expectedURL,
            currentURL: currentURL,
            baselineReference: baselineReference,
            profile: profile,
            configuration: configuration
        )
    }

    private static func bootstrapOrThrow(
        _ testCase: VisualCase,
        currentURL: URL,
        profile: String,
        configuration: ManifestRunConfiguration
    ) throws -> VisualCaseRunReport {
        guard configuration.bootstrapRolling else {
            throw ManifestRunnerError.missingRollingBaseline(caseID: testCase.id)
        }
        return try writeBootstrapReport(
            testCase: testCase,
            currentURL: currentURL,
            profile: profile,
            configuration: configuration
        )
    }

    private static func compareAndWrite(
        testCase: VisualCase,
        expectedURL: URL,
        currentURL: URL,
        baselineReference: String,
        profile: String,
        configuration: ManifestRunConfiguration
    ) throws -> VisualCaseRunReport {
        let expected = try PixelImage.loadPNG(from: expectedURL)
        let actual = try PixelImage.loadPNG(from: currentURL)
        let result = VisualComparator.compare(
            expected: expected,
            actual: actual,
            policy: ComparisonPolicy(
                maxChangedPixelRatio: testCase.maxChangedPixelRatio,
                maxChannelDelta: testCase.maxChannelDelta
            )
        )
        let expectedDigest = try ImageDigest.sha256(fileAt: expectedURL)
        let actualDigest = try ImageDigest.sha256(fileAt: currentURL)
        let approvalResult = try evaluateApproval(
            testCase: testCase,
            comparisonPassed: result.report.passed,
            expectedDigest: expectedDigest,
            actualDigest: actualDigest,
            profileFingerprint: profile,
            configuration: configuration
        )
        let report = VisualCaseRunReport(
            caseID: testCase.id,
            baseline: testCase.baseline,
            baselineReference: baselineReference,
            currentSHA: configuration.currentSHA,
            profile: profile,
            status: approvalResult.status,
            maxChangedPixelRatio: testCase.maxChangedPixelRatio,
            maxChannelDeltaThreshold: Int(testCase.maxChannelDelta),
            expectedDigest: expectedDigest,
            actualDigest: actualDigest,
            approvalPath: testCase.approval,
            approvalReason: approvalResult.reason,
            dimensionMismatch: result.report.dimensionMismatch,
            expectedWidth: result.report.expectedWidth,
            expectedHeight: result.report.expectedHeight,
            actualWidth: result.report.actualWidth,
            actualHeight: result.report.actualHeight,
            changedPixelCount: result.report.changedPixelCount,
            changedPixelRatio: result.report.changedPixelRatio,
            maxChannelDelta: result.report.maxChannelDelta
        )

        let caseRoot = try prepareCaseOutput(
            caseID: testCase.id,
            outputRoot: configuration.outputRoot
        )
        try expected.writePNG(to: caseRoot.appendingPathComponent("expected.png"))
        try actual.writePNG(to: caseRoot.appendingPathComponent("actual.png"))
        try result.diff.writePNG(to: caseRoot.appendingPathComponent("diff.png"))
        try write(report: report, to: caseRoot.appendingPathComponent("report.json"))
        return report
    }

    private static func evaluateApproval(
        testCase: VisualCase,
        comparisonPassed: Bool,
        expectedDigest: String,
        actualDigest: String,
        profileFingerprint: String,
        configuration: ManifestRunConfiguration
    ) throws -> (status: VisualCaseStatus, reason: String?) {
        guard !comparisonPassed else {
            return (.passed, nil)
        }
        guard let approvalPath = testCase.approval else {
            return (.failed, nil)
        }

        let approvalURL = try confinedRepositoryURL(
            repoRoot: configuration.repoRoot,
            relativePath: approvalPath,
            allowedRelativeRoot: "Tests/VisualRegression/Approvals"
        )
        try requireRegularFile(
            approvalURL,
            missingError: .missingApproval(caseID: testCase.id, path: approvalPath)
        )
        let approval = try VisualApproval.load(from: approvalURL)
        let context = VisualApprovalContext(
            caseID: testCase.id,
            fromDigest: expectedDigest,
            toDigest: actualDigest,
            profileFingerprint: profileFingerprint
        )
        guard approval.matches(context) else {
            return (.failed, nil)
        }
        return (.approvedChange, approval.reason)
    }

    private static func writeBootstrapReport(
        testCase: VisualCase,
        currentURL: URL,
        profile: String,
        configuration: ManifestRunConfiguration
    ) throws -> VisualCaseRunReport {
        let actual = try PixelImage.loadPNG(from: currentURL)
        let report = try VisualCaseRunReport(
            caseID: testCase.id,
            baseline: testCase.baseline,
            baselineReference: "bootstrap:none",
            currentSHA: configuration.currentSHA,
            profile: profile,
            status: .bootstrap,
            maxChangedPixelRatio: testCase.maxChangedPixelRatio,
            maxChannelDeltaThreshold: Int(testCase.maxChannelDelta),
            expectedDigest: nil,
            actualDigest: ImageDigest.sha256(fileAt: currentURL),
            approvalPath: testCase.approval,
            approvalReason: nil,
            dimensionMismatch: nil,
            expectedWidth: nil,
            expectedHeight: nil,
            actualWidth: actual.width,
            actualHeight: actual.height,
            changedPixelCount: nil,
            changedPixelRatio: nil,
            maxChannelDelta: nil
        )

        let caseRoot = try prepareCaseOutput(
            caseID: testCase.id,
            outputRoot: configuration.outputRoot
        )
        try actual.writePNG(to: caseRoot.appendingPathComponent("actual.png"))
        try write(report: report, to: caseRoot.appendingPathComponent("report.json"))
        return report
    }

    private static func prepareCaseOutput(caseID: String, outputRoot: URL) throws -> URL {
        let caseRoot = outputRoot.appendingPathComponent(caseID, isDirectory: true)
        if FileManager.default.fileExists(atPath: caseRoot.path) {
            try FileManager.default.removeItem(at: caseRoot)
        }
        try FileManager.default.createDirectory(at: caseRoot, withIntermediateDirectories: true)
        return caseRoot
    }

    private static func write(report: VisualCaseRunReport, to url: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        try encoder.encode(report).write(to: url, options: .atomic)
    }

    private static func requireRegularFile(
        _ url: URL,
        missingError: ManifestRunnerError
    ) throws {
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw missingError
        }
        guard isRegularFile(url) else {
            throw ManifestRunnerError.notRegularFile(url.path)
        }
    }

    private static func isRegularFile(_ url: URL) -> Bool {
        guard let values = try? url.resourceValues(forKeys: [.isRegularFileKey]) else {
            return false
        }
        return values.isRegularFile == true
    }

    private static func confinedRepositoryURL(
        repoRoot: URL,
        relativePath: String,
        allowedRelativeRoot: String
    ) throws -> URL {
        let allowedRoot = repoRoot
            .appendingPathComponent(allowedRelativeRoot, isDirectory: true)
            .standardizedFileURL
            .resolvingSymlinksInPath()
        let candidate = repoRoot
            .appendingPathComponent(relativePath)
            .standardizedFileURL
            .resolvingSymlinksInPath()
        guard isDescendant(candidate, of: allowedRoot) else {
            throw ManifestRunnerError.unsafeResolvedPath(relativePath)
        }
        return candidate
    }

    private static func confinedChildURL(root: URL, childName: String) throws -> URL {
        let resolvedRoot = root.standardizedFileURL.resolvingSymlinksInPath()
        let candidate = root
            .appendingPathComponent(childName)
            .standardizedFileURL
            .resolvingSymlinksInPath()
        guard isDescendant(candidate, of: resolvedRoot) else {
            throw ManifestRunnerError.unsafeResolvedPath(childName)
        }
        return candidate
    }

    private static func isDescendant(_ candidate: URL, of root: URL) -> Bool {
        let rootPath = root.path.hasSuffix("/") ? root.path : root.path + "/"
        return candidate.path == root.path || candidate.path.hasPrefix(rootPath)
    }
}
