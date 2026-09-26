import Foundation
@testable import VisualDiffCore
import XCTest

final class VisualManifestApprovalTests: XCTestCase {
    func testDecodesApprovalPathUnderApprovalRoot() throws {
        let manifest = try VisualManifest.decode(Data(manifest(
            approval: "Tests/VisualRegression/Approvals/dynamic.json"
        ).utf8))

        XCTAssertEqual(
            manifest.cases[0].approval,
            "Tests/VisualRegression/Approvals/dynamic.json"
        )
    }

    func testRejectsAbsoluteApprovalPath() {
        assertManifestFails(manifest(approval: "/tmp/approval.json"))
    }

    func testRejectsApprovalPathTraversal() {
        assertManifestFails(manifest(
            approval: "Tests/VisualRegression/Approvals/../approval.json"
        ))
    }

    func testRejectsApprovalOutsideApprovalRoot() {
        assertManifestFails(manifest(
            approval: "Tests/VisualRegression/Other/approval.json"
        ))
    }

    private func manifest(approval: String) -> String {
        """
        {
          "schemaVersion": 1,
          "profile": "macos-26-arm64-xcode-26.6",
          "cases": [{
            "id": "dynamic",
            "baseline": "rolling-main",
            "current": "artifacts/visual/current/dynamic.png",
            "approval": "\(approval)",
            "maxChangedPixelRatio": 0.0,
            "maxChannelDelta": 0
          }]
        }
        """
    }

    private func assertManifestFails(
        _ json: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertThrowsError(
            try VisualManifest.decode(Data(json.utf8)),
            file: file,
            line: line
        )
    }
}
