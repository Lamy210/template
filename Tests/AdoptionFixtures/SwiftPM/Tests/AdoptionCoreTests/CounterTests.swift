@testable import AdoptionCore
import Testing

@Test func `increment adds one`() {
    #expect(Counter().increment(41) == 42)
}

@Test func `parity is deterministic`() {
    #expect(Counter().isEven(42))
    #expect(!Counter().isEven(41))
}
