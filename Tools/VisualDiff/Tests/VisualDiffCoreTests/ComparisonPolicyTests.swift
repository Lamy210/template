@testable import VisualDiffCore
import XCTest

final class ComparisonPolicyTests: XCTestCase {
    func testRejectsChangedPixelRatioBelowZero() {
        XCTAssertThrowsError(
            try ComparisonPolicy(maxChangedPixelRatio: -0.001, maxChannelDelta: 0)
        )
    }

    func testRejectsChangedPixelRatioAboveOne() {
        XCTAssertThrowsError(
            try ComparisonPolicy(maxChangedPixelRatio: 1.001, maxChannelDelta: 0)
        )
    }

    func testRejectsNonFiniteChangedPixelRatio() {
        for value in [Double.nan, Double.infinity, -Double.infinity] {
            XCTAssertThrowsError(
                try ComparisonPolicy(maxChangedPixelRatio: value, maxChannelDelta: 0)
            )
        }
    }

    func testAcceptsChangedPixelRatioBoundaries() throws {
        let zero = try ComparisonPolicy(maxChangedPixelRatio: 0, maxChannelDelta: 0)
        let one = try ComparisonPolicy(maxChangedPixelRatio: 1, maxChannelDelta: 255)

        XCTAssertEqual(zero.maxChangedPixelRatio, 0)
        XCTAssertEqual(one.maxChangedPixelRatio, 1)
    }
}
