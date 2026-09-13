import Darwin
import Foundation
import VisualDiffCore

enum CLIError: Error, CustomStringConvertible {
    case usage(String)
    case missingValue(String)
    case invalidBoolean(String)
    case unknownArgument(String)

    var description: String {
        switch self {
        case let .usage(message): message
        case let .missingValue(argument): "Missing value for \(argument)"
        case let .invalidBoolean(value): "Expected true or false, got \(value)"
        case let .unknownArgument(argument): "Unknown argument: \(argument)"
        }
    }
}

struct Arguments {
    private var values: [String: String] = [:]

    init(_ raw: ArraySlice<String>) throws {
        var index = raw.startIndex
        while index < raw.endIndex {
            let key = raw[index]
            guard key.hasPrefix("--") else { throw CLIError.unknownArgument(key) }
            let valueIndex = raw.index(after: index)
            guard valueIndex < raw.endIndex else { throw CLIError.missingValue(key) }
            values[key] = raw[valueIndex]
            index = raw.index(after: valueIndex)
        }
    }

    func require(_ key: String) throws -> String {
        guard let value = values[key], !value.isEmpty else { throw CLIError.missingValue(key) }
        return value
    }

    func optional(_ key: String) -> String? {
        guard let value = values[key], !value.isEmpty else { return nil }
        return value
    }

    func boolean(_ key: String, default defaultValue: Bool = false) throws -> Bool {
        guard let value = values[key] else { return defaultValue }
        switch value.lowercased() {
        case "true": return true
        case "false": return false
        default: throw CLIError.invalidBoolean(value)
        }
    }
}

func pathURL(_ path: String, relativeTo root: URL) -> URL {
    if path.hasPrefix("/") { return URL(fileURLWithPath: path) }
    return root.appendingPathComponent(path)
}

func fail(_ message: String, code: Int32) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(code)
}

func usage() -> String {
    """
    Usage:
      visual-diff validate-manifest --manifest <path> --repo-root <path>
      visual-diff compare-manifest --manifest <path> --repo-root <path> \\
        --current-profile <path> --rolling-root <path-or-empty> \\
        --rolling-profile <path-or-empty> --output <path> \\
        --current-sha <sha> --baseline-run-id <id-or-empty> \\
        --bootstrap-rolling <true|false>
    """
}

let raw = CommandLine.arguments

guard raw.count >= 2 else { fail(usage(), code: 2) }
let command = raw[1]

do {
    let arguments = try Arguments(raw.dropFirst(2))
    let repoRoot = URL(fileURLWithPath: try arguments.require("--repo-root"), isDirectory: true)
        .standardizedFileURL
    let manifestURL = pathURL(try arguments.require("--manifest"), relativeTo: repoRoot)
    let manifest = try VisualManifest.load(from: manifestURL)

    switch command {
    case "validate-manifest":
        print("Manifest valid: \(manifest.cases.count) case(s), profile=\(manifest.profile)")

    case "compare-manifest":
        let currentProfileURL = pathURL(try arguments.require("--current-profile"), relativeTo: repoRoot)
        let outputRoot = pathURL(try arguments.require("--output"), relativeTo: repoRoot)
        let rollingRoot = arguments.optional("--rolling-root").map { pathURL($0, relativeTo: repoRoot) }
        let rollingProfile = arguments.optional("--rolling-profile").map { pathURL($0, relativeTo: repoRoot) }
        let summary = try ManifestRunner.run(
            manifest: manifest,
            configuration: ManifestRunConfiguration(
                repoRoot: repoRoot,
                currentProfileURL: currentProfileURL,
                rollingRoot: rollingRoot,
                rollingProfileURL: rollingProfile,
                outputRoot: outputRoot,
                currentSHA: try arguments.require("--current-sha"),
                baselineRunID: arguments.optional("--baseline-run-id"),
                bootstrapRolling: try arguments.boolean("--bootstrap-rolling")
            )
        )

        for report in summary.cases {
            print("\(report.caseID)\t\(report.baseline.rawValue)\t\(report.status.rawValue)")
        }
        if summary.hasFailures { exit(1) }

    default:
        throw CLIError.usage(usage())
    }
} catch {
    fail("visual-diff: \(error)\n\(usage())", code: 2)
}
