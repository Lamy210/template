public enum ComparisonPolicyError: Error, Equatable {
    case invalidChangedPixelRatio(Double)
}

public struct ComparisonPolicy: Sendable, Equatable {
    public let maxChangedPixelRatio: Double
    public let maxChannelDelta: UInt8

    public init(maxChangedPixelRatio: Double, maxChannelDelta: UInt8) throws {
        guard maxChangedPixelRatio.isFinite,
              (0 ... 1).contains(maxChangedPixelRatio)
        else {
            throw ComparisonPolicyError.invalidChangedPixelRatio(maxChangedPixelRatio)
        }

        self.maxChangedPixelRatio = maxChangedPixelRatio
        self.maxChannelDelta = maxChannelDelta
    }
}
