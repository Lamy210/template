import CryptoKit
import Foundation

enum CanonicalJSON {
    static func data(for value: some Encodable) -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        do {
            return try encoder.encode(value)
        } catch {
            preconditionFailure("Canonical JSON encoding failed: \(error)")
        }
    }

    static func sha256(_ value: some Encodable) -> String {
        let digest = SHA256.hash(data: data(for: value))
        let hex = digest.map { String(format: "%02x", $0) }.joined()
        return "sha256:" + hex
    }
}
