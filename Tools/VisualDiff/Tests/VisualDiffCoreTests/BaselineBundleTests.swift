import Foundation
@testable import VisualDiffCore
import XCTest

final class BaselineBundleTests: XCTestCase {
    func testValidBundleVerifiesEveryDeclaredImageDigest() throws {
        let fixture = try BundleFixture()
        let first = Data("first-image".utf8)
        let second = Data("second-image".utf8)
        try fixture.write(first, caseID: "settings-light")
        try fixture.write(second, caseID: "main-window")
        let manifest = fixture.manifest(cases: [
            .init(id: "settings-light", digest: ImageDigest.sha256(first)),
            .init(id: "main-window", digest: ImageDigest.sha256(second))
        ])

        let validated = try BaselineBundleValidator.validate(
            root: fixture.root,
            manifest: manifest,
            expectedProfileFingerprint: fixture.profileFingerprint,
            strict: true
        )

        XCTAssertEqual(validated.caseDigests["settings-light"], ImageDigest.sha256(first))
        XCTAssertEqual(validated.caseDigests["main-window"], ImageDigest.sha256(second))
    }

    func testRejectsMissingDeclaredImage() throws {
        let fixture = try BundleFixture()
        let manifest = fixture.manifest(cases: [
            .init(id: "missing", digest: ImageDigest.sha256(Data("missing".utf8)))
        ])

        XCTAssertThrowsError(try BaselineBundleValidator.validate(
            root: fixture.root,
            manifest: manifest,
            expectedProfileFingerprint: fixture.profileFingerprint,
            strict: true
        )) { error in
            guard case BaselineBundleError.missingImage(caseID: "missing") = error else {
                return XCTFail("Unexpected error: \(error)")
            }
        }
    }

    func testRejectsChangedImageDigest() throws {
        let fixture = try BundleFixture()
        try fixture.write(Data("changed".utf8), caseID: "settings-light")
        let manifest = fixture.manifest(cases: [
            .init(id: "settings-light", digest: ImageDigest.sha256(Data("expected".utf8)))
        ])

        XCTAssertThrowsError(try BaselineBundleValidator.validate(
            root: fixture.root,
            manifest: manifest,
            expectedProfileFingerprint: fixture.profileFingerprint,
            strict: true
        )) { error in
            guard case BaselineBundleError.digestMismatch(caseID: "settings-light", expected: _, actual: _) = error else {
                return XCTFail("Unexpected error: \(error)")
            }
        }
    }

    func testRejectsUnexpectedImageInStrictMode() throws {
        let fixture = try BundleFixture()
        let declared = Data("declared".utf8)
        try fixture.write(declared, caseID: "declared")
        try fixture.write(Data("unexpected".utf8), caseID: "unexpected")
        let manifest = fixture.manifest(cases: [
            .init(id: "declared", digest: ImageDigest.sha256(declared))
        ])

        XCTAssertThrowsError(try BaselineBundleValidator.validate(
            root: fixture.root,
            manifest: manifest,
            expectedProfileFingerprint: fixture.profileFingerprint,
            strict: true
        )) { error in
            guard case BaselineBundleError.unexpectedImage("unexpected.png") = error else {
                return XCTFail("Unexpected error: \(error)")
            }
        }
    }

    func testRejectsProfileFingerprintMismatchBeforeImageValidation() throws {
        let fixture = try BundleFixture()
        let manifest = fixture.manifest(cases: [])

        XCTAssertThrowsError(try BaselineBundleValidator.validate(
            root: fixture.root,
            manifest: manifest,
            expectedProfileFingerprint: "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            strict: true
        )) { error in
            guard case BaselineBundleError.profileMismatch(
                expected: "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
                actual: fixture.profileFingerprint
            ) = error else {
                return XCTFail("Unexpected error: \(error)")
            }
        }
    }

    func testRejectsDuplicateCaseIDs() throws {
        let fixture = try BundleFixture()
        let digest = ImageDigest.sha256(Data("same".utf8))
        let manifest = fixture.manifest(cases: [
            .init(id: "duplicate", digest: digest),
            .init(id: "duplicate", digest: digest)
        ])

        XCTAssertThrowsError(try BaselineBundleValidator.validate(
            root: fixture.root,
            manifest: manifest,
            expectedProfileFingerprint: fixture.profileFingerprint,
            strict: true
        )) { error in
            guard case BaselineBundleError.duplicateCaseID("duplicate") = error else {
                return XCTFail("Unexpected error: \(error)")
            }
        }
    }

    func testRejectsUnsafeCaseID() throws {
        let fixture = try BundleFixture()
        let manifest = fixture.manifest(cases: [
            .init(id: "../escape", digest: ImageDigest.sha256(Data("x".utf8)))
        ])

        XCTAssertThrowsError(try BaselineBundleValidator.validate(
            root: fixture.root,
            manifest: manifest,
            expectedProfileFingerprint: fixture.profileFingerprint,
            strict: true
        )) { error in
            guard case BaselineBundleError.invalidCaseID("../escape") = error else {
                return XCTFail("Unexpected error: \(error)")
            }
        }
    }
}

private final class BundleFixture {
    let root: URL
    let profileFingerprint = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    init() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(
            at: root.appendingPathComponent("images", isDirectory: true),
            withIntermediateDirectories: true
        )
    }

    deinit {
        try? FileManager.default.removeItem(at: root)
    }

    func write(_ data: Data, caseID: String) throws {
        try data.write(to: root.appendingPathComponent("images/\(caseID).png"), options: .atomic)
    }

    func manifest(cases: [BaselineBundleCase]) -> BaselineBundleManifest {
        BaselineBundleManifest(
            schemaVersion: 1,
            sourceRepository: "Lamy210/template",
            workflow: "visual-regression.yml",
            sourceRunID: "12345",
            runAttempt: 1,
            sourceSHA: "0123456789abcdef0123456789abcdef01234567",
            profileFingerprint: profileFingerprint,
            previousBaselineReference: nil,
            cases: cases
        )
    }
}
