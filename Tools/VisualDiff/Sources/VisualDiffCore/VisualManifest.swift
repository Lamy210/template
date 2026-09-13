import Foundation

public enum VisualManifestError: Error, Equatable {
    case unsupportedSchemaVersion(Int)
    case emptyProfile
    case emptyCases
    case emptyCaseID
    case invalidCaseID(String)
    case duplicateCaseID(String)
    case invalidRelativePath(String)
    case currentOutsideCaptureRoot(String)
    case missingGitExpectedPath(String)
    case gitExpectedOutsideBaselineRoot(String)
    case rollingCaseMustNotDeclareExpected(String)
    case approvalOutsideApprovalRoot(String)
    case invalidChangedPixelRatio(caseID: String, value: Double)
}

public enum BaselineSource: String, Codable, Sendable, Equatable {
    case git
    case rollingMain = "rolling-main"
}

public struct VisualCase: Codable, Sendable, Equatable {
    public let id: String
    public let baseline: BaselineSource
    public let current: String
    public let expected: String?
    public let maxChangedPixelRatio: Double
    public let maxChannelDelta: UInt8
    public let approval: String?

    public init(
        id: String,
        baseline: BaselineSource,
        current: String,
        expected: String?,
        maxChangedPixelRatio: Double,
        maxChannelDelta: UInt8,
        approval: String? = nil
    ) {
        self.id = id
        self.baseline = baseline
        self.current = current
        self.expected = expected
        self.maxChangedPixelRatio = maxChangedPixelRatio
        self.maxChannelDelta = maxChannelDelta
        self.approval = approval
    }
}

public struct VisualManifest: Codable, Sendable, Equatable {
    public let schemaVersion: Int
    public let profile: String
    public let cases: [VisualCase]

    public init(
        schemaVersion: Int,
        profile: String,
        cases: [VisualCase]
    ) throws {
        self.schemaVersion = schemaVersion
        self.profile = profile
        self.cases = cases
        try validate()
    }

    public static func decode(_ data: Data) throws -> VisualManifest {
        let decoded = try JSONDecoder().decode(VisualManifest.self, from: data)
        try decoded.validate()
        return decoded
    }

    public static func load(from url: URL) throws -> VisualManifest {
        try decode(Data(contentsOf: url))
    }

    private func validate() throws {
        guard schemaVersion == 1 else {
            throw VisualManifestError.unsupportedSchemaVersion(schemaVersion)
        }
        guard !profile.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw VisualManifestError.emptyProfile
        }
        guard !cases.isEmpty else {
            throw VisualManifestError.emptyCases
        }

        var seen = Set<String>()
        for testCase in cases {
            try validate(testCase)
            guard seen.insert(testCase.id).inserted else {
                throw VisualManifestError.duplicateCaseID(testCase.id)
            }
        }
    }

    private func validate(_ testCase: VisualCase) throws {
        guard !testCase.id.isEmpty else {
            throw VisualManifestError.emptyCaseID
        }
        guard isSafeCaseID(testCase.id) else {
            throw VisualManifestError.invalidCaseID(testCase.id)
        }
        guard (0...1).contains(testCase.maxChangedPixelRatio) else {
            throw VisualManifestError.invalidChangedPixelRatio(
                caseID: testCase.id,
                value: testCase.maxChangedPixelRatio
            )
        }

        try validateRelativePath(testCase.current)
        guard isUnder(testCase.current, prefix: "artifacts/visual/current") else {
            throw VisualManifestError.currentOutsideCaptureRoot(testCase.current)
        }

        if let approval = testCase.approval {
            try validateRelativePath(approval)
            guard isUnder(approval, prefix: "Tests/VisualRegression/Approvals") else {
                throw VisualManifestError.approvalOutsideApprovalRoot(approval)
            }
        }

        switch testCase.baseline {
        case .git:
            guard let expected = testCase.expected else {
                throw VisualManifestError.missingGitExpectedPath(testCase.id)
            }
            try validateRelativePath(expected)
            guard isUnder(expected, prefix: "Tests/VisualBaselines") else {
                throw VisualManifestError.gitExpectedOutsideBaselineRoot(expected)
            }
        case .rollingMain:
            guard testCase.expected == nil else {
                throw VisualManifestError.rollingCaseMustNotDeclareExpected(testCase.id)
            }
        }
    }

    private func validateRelativePath(_ path: String) throws {
        guard !path.isEmpty, !path.hasPrefix("/") else {
            throw VisualManifestError.invalidRelativePath(path)
        }
        let components = path.split(separator: "/", omittingEmptySubsequences: false)
        guard !components.contains(where: { $0.isEmpty || $0 == "." || $0 == ".." }) else {
            throw VisualManifestError.invalidRelativePath(path)
        }
    }

    private func isUnder(_ path: String, prefix: String) -> Bool {
        path == prefix || path.hasPrefix(prefix + "/")
    }

    private func isSafeCaseID(_ id: String) -> Bool {
        guard id != ".", id != ".." else { return false }
        return id.unicodeScalars.allSatisfy { scalar in
            CharacterSet.alphanumerics.contains(scalar)
                || scalar == "-"
                || scalar == "_"
                || scalar == "."
        }
    }
}
