@testable import OptionalFailureFixture
import XCTest

final class OptionalFailureTests: XCTestCase {
    func testIntentionalOptionalFailure() {
        XCTAssertEqual(OptionalFailureFixture.value, 2, "intentional optional subsystem runtime failure")
    }
}
