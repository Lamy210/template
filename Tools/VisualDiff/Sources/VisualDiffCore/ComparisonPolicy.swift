public struct ComparisonPolicy: Sendable, Equatable {
    public let maxChangedPixelRatio: Double
    public let maxChannelDelta: UInt8

    public init(maxChangedPixelRatio: Double, maxChannelDelta: UInt8) {
        self.maxChangedPixelRatio = maxChangedPixelRatio
        self.maxChannelDelta = maxChannelDelta
    }
}
