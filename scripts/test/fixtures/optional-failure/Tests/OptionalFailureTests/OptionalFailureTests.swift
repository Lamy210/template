import XCTest
@testable import OptionalFailureFixture

final class OptionalFailureTests: XCTestCase {
    func testIntentionalOptionalFailure() {
        XCTAssertEqual(OptionalFailureFixture.value, 2, "intentional optional subsystem runtime failure")
    }
}
