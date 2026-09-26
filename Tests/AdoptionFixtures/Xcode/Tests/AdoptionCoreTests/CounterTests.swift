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
        guard
            let workspace = ProcessInfo.processInfo.environment["GITHUB_WORKSPACE"]
        else {
            return
        }

        let outputDirectory = URL(fileURLWithPath: workspace, isDirectory: true)
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

        let payload = try XCTUnwrap(Data(base64Encoded: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="))
        try payload.write(
            to: outputDirectory.appendingPathComponent("adoption-counter.png"),
            options: .atomic
        )
    }
}
