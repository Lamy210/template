import Foundation

private struct ManifestReportIdentity {
    let expectedDigest: String
    let actualDigest: String
    let approvalStatus: VisualCaseStatus
    let approvalReason: String?
}

enum ManifestCaseExecutor {
    static func run(
        _ testCase: VisualCase,
        executionProfile: ManifestExecutionProfile,
        rollingBaseline: ValidatedBaselineBundle?,
        configuration: ManifestRunConfiguration
    ) throws -> VisualCaseRunReport {
        let currentURL = try ManifestPathResolver.confinedRepositoryURL(
            repoRoot: configuration.repoRoot,
            relativePath: testCase.current,
            allowedRelativeRoot: "artifacts/visual/current"
        )
        try ManifestPathResolver.requireRegularFile(
            currentURL,
            missingError: .missingCurrentCapture(caseID: testCase.id, path: testCase.current)
        )

        switch testCase.baseline {
        case .git:
            return try runGitCase(
                testCase,
                currentURL: currentURL,
                executionProfile: executionProfile,
                configuration: configuration
            )
        case .rollingMain:
            return try runRollingCase(
                testCase,
                currentURL: currentURL,
                executionProfile: executionProfile,
                rollingBaseline: rollingBaseline,
                configuration: configuration
            )
        }
    }

    private static func runGitCase(
        _ testCase: VisualCase,
        currentURL: URL,
        executionProfile: ManifestExecutionProfile,
        configuration: ManifestRunConfiguration
    ) throws -> VisualCaseRunReport {
        guard let expectedPath = testCase.expected else {
            throw ManifestRunnerError.missingGitBaseline(caseID: testCase.id, path: "")
        }
        let expectedURL = try ManifestPathResolver.confinedRepositoryURL(
            repoRoot: configuration.repoRoot,
            relativePath: expectedPath,
            allowedRelativeRoot: "Tests/VisualBaselines"
        )
        try ManifestPathResolver.requireRegularFile(
            expectedURL,
            missingError: .missingGitBaseline(caseID: testCase.id, path: expectedPath)
        )
        return try compareAndWrite(
            testCase: testCase,
            expectedURL: expectedURL,
            currentURL: currentURL,
            baselineReference: "git:\(expectedPath)",
            executionProfile: executionProfile,
            configuration: configuration
        )
    }

    private static func runRollingCase(
        _ testCase: VisualCase,
        currentURL: URL,
        executionProfile: ManifestExecutionProfile,
        rollingBaseline: ValidatedBaselineBundle?,
        configuration: ManifestRunConfiguration
    ) throws -> VisualCaseRunReport {
        guard let rollingBaseline else {
            return try bootstrapOrThrow(
                testCase,
                currentURL: currentURL,
                executionProfile: executionProfile,
                configuration: configuration
            )
        }

        guard let expectedURL = rollingBaseline.imageURL(caseID: testCase.id) else {
            return try writeBootstrapReport(
                testCase: testCase,
                currentURL: currentURL,
                executionProfile: executionProfile,
                configuration: configuration
            )
        }

        return try compareAndWrite(
            testCase: testCase,
            expectedURL: expectedURL,
            currentURL: currentURL,
            baselineReference: "run:\(rollingBaseline.manifest.sourceRunID)",
            executionProfile: executionProfile,
            configuration: configuration
        )
    }

    private static func bootstrapOrThrow(
        _ testCase: VisualCase,
        currentURL: URL,
        executionProfile: ManifestExecutionProfile,
        configuration: ManifestRunConfiguration
    ) throws -> VisualCaseRunReport {
        guard configuration.bootstrapRolling else {
            throw ManifestRunnerError.missingRollingBaseline(caseID: testCase.id)
        }
        return try writeBootstrapReport(
            testCase: testCase,
            currentURL: currentURL,
            executionProfile: executionProfile,
            configuration: configuration
        )
    }

    private static func compareAndWrite(
        testCase: VisualCase,
        expectedURL: URL,
        currentURL: URL,
        baselineReference: String,
        executionProfile: ManifestExecutionProfile,
        configuration: ManifestRunConfiguration
    ) throws -> VisualCaseRunReport {
        let expected = try PixelImage.loadPNG(from: expectedURL)
        let actual = try PixelImage.loadPNG(from: currentURL)
        let result = try VisualComparator.compare(
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
            profileFingerprint: executionProfile.fingerprint,
            configuration: configuration
        )
        let identity = ManifestReportIdentity(
            expectedDigest: expectedDigest,
            actualDigest: actualDigest,
            approvalStatus: approvalResult.status,
            approvalReason: approvalResult.reason
        )
        let report = makeReport(
            testCase: testCase,
            baselineReference: baselineReference,
            executionProfile: executionProfile,
            identity: identity,
            comparison: result.report,
            currentSHA: configuration.currentSHA
        )

        let caseRoot = try ManifestReportIO.prepareCaseOutput(
            caseID: testCase.id,
            outputRoot: configuration.outputRoot
        )
        try expected.writePNG(to: caseRoot.appendingPathComponent("expected.png"))
        try actual.writePNG(to: caseRoot.appendingPathComponent("actual.png"))
        try result.diff.writePNG(to: caseRoot.appendingPathComponent("diff.png"))
        try ManifestReportIO.write(
            report: report,
            to: caseRoot.appendingPathComponent("report.json")
        )
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

        let approvalURL = try ManifestPathResolver.confinedRepositoryURL(
            repoRoot: configuration.repoRoot,
            relativePath: approvalPath,
            allowedRelativeRoot: "Tests/VisualRegression/Approvals"
        )
        try ManifestPathResolver.requireRegularFile(
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
        executionProfile: ManifestExecutionProfile,
        configuration: ManifestRunConfiguration
    ) throws -> VisualCaseRunReport {
        let actual = try PixelImage.loadPNG(from: currentURL)
        let report = try VisualCaseRunReport(
            caseID: testCase.id,
            baseline: testCase.baseline,
            baselineReference: "bootstrap:none",
            currentSHA: configuration.currentSHA,
            profile: executionProfile.label,
            profileFingerprint: executionProfile.fingerprint,
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

        let caseRoot = try ManifestReportIO.prepareCaseOutput(
            caseID: testCase.id,
            outputRoot: configuration.outputRoot
        )
        try actual.writePNG(to: caseRoot.appendingPathComponent("actual.png"))
        try ManifestReportIO.write(
            report: report,
            to: caseRoot.appendingPathComponent("report.json")
        )
        return report
    }

    private static func makeReport(
        testCase: VisualCase,
        baselineReference: String,
        executionProfile: ManifestExecutionProfile,
        identity: ManifestReportIdentity,
        comparison: ComparisonReport,
        currentSHA: String
    ) -> VisualCaseRunReport {
        VisualCaseRunReport(
            caseID: testCase.id,
            baseline: testCase.baseline,
            baselineReference: baselineReference,
            currentSHA: currentSHA,
            profile: executionProfile.label,
            profileFingerprint: executionProfile.fingerprint,
            status: identity.approvalStatus,
            maxChangedPixelRatio: testCase.maxChangedPixelRatio,
            maxChannelDeltaThreshold: Int(testCase.maxChannelDelta),
            expectedDigest: identity.expectedDigest,
            actualDigest: identity.actualDigest,
            approvalPath: testCase.approval,
            approvalReason: identity.approvalReason,
            dimensionMismatch: comparison.dimensionMismatch,
            expectedWidth: comparison.expectedWidth,
            expectedHeight: comparison.expectedHeight,
            actualWidth: comparison.actualWidth,
            actualHeight: comparison.actualHeight,
            changedPixelCount: comparison.changedPixelCount,
            changedPixelRatio: comparison.changedPixelRatio,
            maxChannelDelta: comparison.maxChannelDelta
        )
    }
}
