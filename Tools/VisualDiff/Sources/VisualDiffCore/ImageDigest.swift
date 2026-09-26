import CryptoKit
import Foundation

public enum ImageDigest {
    public static func sha256(_ data: Data) -> String {
        let digest = SHA256.hash(data: data)
        let hex = digest.map { String(format: "%02x", $0) }.joined()
        return "sha256:" + hex
    }

    public static func sha256(fileAt url: URL) throws -> String {
        try sha256(Data(contentsOf: url))
    }
}
