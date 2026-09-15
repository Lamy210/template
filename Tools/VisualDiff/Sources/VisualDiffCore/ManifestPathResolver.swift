import Foundation

enum ManifestPathResolver {
    static func requireRegularFile(
        _ url: URL,
        missingError: ManifestRunnerError
    ) throws {
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw missingError
        }
        guard isRegularFile(url) else {
            throw ManifestRunnerError.notRegularFile(url.path)
        }
    }

    static func isRegularFile(_ url: URL) -> Bool {
        guard let values = try? url.resourceValues(forKeys: [.isRegularFileKey]) else {
            return false
        }
        return values.isRegularFile == true
    }

    static func confinedRepositoryURL(
        repoRoot: URL,
        relativePath: String,
        allowedRelativeRoot: String
    ) throws -> URL {
        let allowedRoot = repoRoot
            .appendingPathComponent(allowedRelativeRoot, isDirectory: true)
            .standardizedFileURL
            .resolvingSymlinksInPath()
        let candidate = repoRoot
            .appendingPathComponent(relativePath)
            .standardizedFileURL
            .resolvingSymlinksInPath()
        guard isDescendant(candidate, of: allowedRoot) else {
            throw ManifestRunnerError.unsafeResolvedPath(relativePath)
        }
        return candidate
    }

    static func confinedChildURL(root: URL, childName: String) throws -> URL {
        let resolvedRoot = root.standardizedFileURL.resolvingSymlinksInPath()
        let candidate = root
            .appendingPathComponent(childName)
            .standardizedFileURL
            .resolvingSymlinksInPath()
        guard isDescendant(candidate, of: resolvedRoot) else {
            throw ManifestRunnerError.unsafeResolvedPath(childName)
        }
        return candidate
    }

    private static func isDescendant(_ candidate: URL, of root: URL) -> Bool {
        let rootPath = root.path.hasSuffix("/") ? root.path : root.path + "/"
        return candidate.path == root.path || candidate.path.hasPrefix(rootPath)
    }
}

enum ManifestReportIO {
    static func prepareCaseOutput(caseID: String, outputRoot: URL) throws -> URL {
        let caseRoot = outputRoot.appendingPathComponent(caseID, isDirectory: true)
        if FileManager.default.fileExists(atPath: caseRoot.path) {
            try FileManager.default.removeItem(at: caseRoot)
        }
        try FileManager.default.createDirectory(at: caseRoot, withIntermediateDirectories: true)
        return caseRoot
    }

    static func write(report: VisualCaseRunReport, to url: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        try encoder.encode(report).write(to: url, options: .atomic)
    }
}
