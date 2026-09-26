import AdoptionCore
import XCTest

final class CounterTests: XCTestCase {
    func testIncrementAddsOne() {
        XCTAssertEqual(Counter().increment(41), 42)
    }

    func testParityIsDeterministic() {
        XCTAssertTrue(Counter().isEven(42))
        XCTAssertFalse(Counter().isEven(41))
    }
}
