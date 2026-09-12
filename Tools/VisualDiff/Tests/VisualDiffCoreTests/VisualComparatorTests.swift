import XCTest
@testable import VisualDiffCore

final class VisualComparatorTests: XCTestCase {
    func testIdenticalImagesPassStrictComparison() throws {
        let expected = try TestImageFactory.solid(width: 2, height: 2, rgba: [255, 0, 0, 255])

        let result = VisualComparator.compare(
            expected: expected,
            actual: expected,
            policy: ComparisonPolicy(maxChangedPixelRatio: 0, maxChannelDelta: 0)
        )

        XCTAssertTrue(result.report.passed)
        XCTAssertFalse(result.report.dimensionMismatch)
        XCTAssertEqual(result.report.changedPixelCount, 0)
        XCTAssertEqual(result.report.changedPixelRatio, 0, accuracy: 0.000_001)
        XCTAssertEqual(result.report.maxChannelDelta, 0)
    }

    func testSinglePixelChangeFailsStrictComparison() throws {
        let expected = try TestImageFactory.solid(width: 2, height: 2, rgba: [0, 0, 0, 255])
        var bytes = expected.rgba
        bytes[0] = 1
        let actual = try PixelImage(width: 2, height: 2, rgba: bytes)

        let result = VisualComparator.compare(
            expected: expected,
            actual: actual,
            policy: ComparisonPolicy(maxChangedPixelRatio: 0, maxChannelDelta: 0)
        )

        XCTAssertFalse(result.report.passed)
        XCTAssertEqual(result.report.changedPixelCount, 1)
        XCTAssertEqual(result.report.changedPixelRatio, 0.25, accuracy: 0.000_001)
        XCTAssertEqual(result.report.maxChannelDelta, 1)
    }

    func testChangedPixelRatioAtThresholdPasses() throws {
        let expected = try TestImageFactory.solid(width: 2, height: 2, rgba: [0, 0, 0, 255])
        var bytes = expected.rgba
        bytes[0] = 255
        let actual = try PixelImage(width: 2, height: 2, rgba: bytes)

        let result = VisualComparator.compare(
            expected: expected,
            actual: actual,
            policy: ComparisonPolicy(maxChangedPixelRatio: 0.25, maxChannelDelta: 255)
        )

        XCTAssertTrue(result.report.passed)
    }

    func testChannelDeltaAtThresholdPasses() throws {
        let expected = try TestImageFactory.solid(width: 1, height: 1, rgba: [10, 20, 30, 255])
        let actual = try TestImageFactory.solid(width: 1, height: 1, rgba: [12, 20, 30, 255])

        let result = VisualComparator.compare(
            expected: expected,
            actual: actual,
            policy: ComparisonPolicy(maxChangedPixelRatio: 1, maxChannelDelta: 2)
        )

        XCTAssertTrue(result.report.passed)
        XCTAssertEqual(result.report.maxChannelDelta, 2)
    }

    func testDimensionMismatchReturnsFailedDiagnosticResult() throws {
        let expected = try TestImageFactory.solid(width: 2, height: 2, rgba: [0, 0, 0, 255])
        let actual = try TestImageFactory.solid(width: 3, height: 2, rgba: [0, 0, 0, 255])

        let result = VisualComparator.compare(
            expected: expected,
            actual: actual,
            policy: ComparisonPolicy(maxChangedPixelRatio: 1, maxChannelDelta: 255)
        )

        XCTAssertFalse(result.report.passed)
        XCTAssertTrue(result.report.dimensionMismatch)
        XCTAssertEqual(result.report.expectedWidth, 2)
        XCTAssertEqual(result.report.expectedHeight, 2)
        XCTAssertEqual(result.report.actualWidth, 3)
        XCTAssertEqual(result.report.actualHeight, 2)
        XCTAssertGreaterThan(result.diff.width, expected.width)
    }
}
