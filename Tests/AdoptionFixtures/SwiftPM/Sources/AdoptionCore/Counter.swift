public struct Counter: Sendable {
    public init() {}

    public func increment(_ value: Int) -> Int {
        value + 1
    }

    public func isEven(_ value: Int) -> Bool {
        value.isMultiple(of: 2)
    }
}
