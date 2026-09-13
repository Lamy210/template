import CryptoKit
import Foundation

enum CanonicalJSON {
    static func data<T: Encodable>(for value: T) -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        do {
            return try encoder.encode(value)
        } catch {
            preconditionFailure("Canonical JSON encoding failed: \(error)")
        }
    }

    static func sha256<T: Encodable>(_ value: T) -> String {
        let digest = SHA256.hash(data: data(for: value))
        let hex = digest.map { String(format: "%02x", $0) }.joined()
        return "sha256:" + hex
    }
}
