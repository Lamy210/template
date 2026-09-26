import AdoptionCore
import Foundation
import XCTest

final class CounterTests: XCTestCase {
    func testIncrementAddsOne() {
        XCTAssertEqual(Counter().increment(41), 42)
    }

    func testParityIsDeterministic() {
        XCTAssertTrue(Counter().isEven(42))
        XCTAssertFalse(Counter().isEven(41))
    }

    func testWritesDeterministicVisualFixtureWhenCaptureDirectoryExists() throws {
        var repositoryRoot = URL(fileURLWithPath: #filePath)
        for _ in 0 ..< 6 {
            repositoryRoot.deleteLastPathComponent()
        }

        let outputDirectory = repositoryRoot
            .appendingPathComponent("artifacts/visual/current", isDirectory: true)
        var isDirectory: ObjCBool = false
        guard
            FileManager.default.fileExists(
                atPath: outputDirectory.path,
                isDirectory: &isDirectory
            ),
            isDirectory.boolValue
        else {
            return
        }

        let encodedPNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        let payload = try XCTUnwrap(Data(base64Encoded: encodedPNG))
        try payload.write(
            to: outputDirectory.appendingPathComponent("adoption-counter.png"),
            options: .atomic
        )
    }
}
