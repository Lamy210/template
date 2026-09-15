public struct ComparisonReport: Sendable, Equatable, Codable {
    public let passed: Bool
    public let dimensionMismatch: Bool
    public let expectedWidth: Int
    public let expectedHeight: Int
    public let actualWidth: Int
    public let actualHeight: Int
    public let changedPixelCount: Int
    public let changedPixelRatio: Double
    public let maxChannelDelta: Int

    public init(
        passed: Bool,
        dimensionMismatch: Bool,
        expectedWidth: Int,
        expectedHeight: Int,
        actualWidth: Int,
        actualHeight: Int,
        changedPixelCount: Int,
        changedPixelRatio: Double,
        maxChannelDelta: Int
    ) {
        self.passed = passed
        self.dimensionMismatch = dimensionMismatch
        self.expectedWidth = expectedWidth
        self.expectedHeight = expectedHeight
        self.actualWidth = actualWidth
        self.actualHeight = actualHeight
        self.changedPixelCount = changedPixelCount
        self.changedPixelRatio = changedPixelRatio
        self.maxChannelDelta = maxChannelDelta
    }
}

public struct ComparisonResult: Sendable, Equatable {
    public let report: ComparisonReport
    public let diff: PixelImage

    public init(report: ComparisonReport, diff: PixelImage) {
        self.report = report
        self.diff = diff
    }
}
