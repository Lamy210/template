import Foundation
@testable import VisualDiffCore
import XCTest

final class PixelImageTests: XCTestCase {
    func testRejectsInvalidRGBAByteCount() {
        XCTAssertThrowsError(
            try PixelImage(width: 2, height: 2, rgba: [0, 0, 0, 255])
        )
    }

    func testRejectsNonPositiveDimensions() {
        XCTAssertThrowsError(try PixelImage(width: 0, height: 1, rgba: []))
        XCTAssertThrowsError(try PixelImage(width: 1, height: 0, rgba: []))
    }

    func testPNGRoundTripPreservesNormalizedPixels() throws {
        let image = try PixelImage(
            width: 1,
            height: 2,
            rgba: [
                255, 0, 0, 255,
                0, 0, 255, 255
            ]
        )
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let path = directory.appendingPathComponent("roundtrip.png")
        try image.writePNG(to: path)
        let loaded = try PixelImage.loadPNG(from: path)

        XCTAssertEqual(loaded.width, image.width)
        XCTAssertEqual(loaded.height, image.height)
        XCTAssertEqual(loaded.rgba, image.rgba)
    }
}
