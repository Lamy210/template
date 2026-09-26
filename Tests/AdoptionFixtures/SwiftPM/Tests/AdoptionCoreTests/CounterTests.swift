import Testing
@testable import AdoptionCore

@Test func incrementAddsOne() {
    #expect(Counter().increment(41) == 42)
}

@Test func parityIsDeterministic() {
    #expect(Counter().isEven(42))
    #expect(!Counter().isEven(41))
}
