public enum VisualComparator {
    public static func compare(
        expected: PixelImage,
        actual: PixelImage,
        policy: ComparisonPolicy
    ) -> ComparisonResult {
        guard expected.width == actual.width, expected.height == actual.height else {
            return dimensionMismatchResult(expected: expected, actual: actual)
        }

        let pixelCount = expected.width * expected.height
        var changedPixelCount = 0
        var maxChannelDelta = 0
        var diffBytes = [UInt8](repeating: 0, count: expected.rgba.count)

        for pixel in 0 ..< pixelCount {
            let offset = pixel * 4
            var pixelMaxDelta = 0

            for channel in 0 ..< 4 {
                let delta = abs(Int(expected.rgba[offset + channel]) - Int(actual.rgba[offset + channel]))
                pixelMaxDelta = max(pixelMaxDelta, delta)
                maxChannelDelta = max(maxChannelDelta, delta)
            }

            if pixelMaxDelta > 0 {
                changedPixelCount += 1
                diffBytes[offset] = 255
                diffBytes[offset + 1] = 0
                diffBytes[offset + 2] = 0
                diffBytes[offset + 3] = 255
            } else {
                diffBytes[offset] = expected.rgba[offset] / 4
                diffBytes[offset + 1] = expected.rgba[offset + 1] / 4
                diffBytes[offset + 2] = expected.rgba[offset + 2] / 4
                diffBytes[offset + 3] = 255
            }
        }

        let changedPixelRatio = Double(changedPixelCount) / Double(pixelCount)
        let passed = changedPixelRatio <= policy.maxChangedPixelRatio
            && maxChannelDelta <= Int(policy.maxChannelDelta)
        let report = ComparisonReport(
            passed: passed,
            dimensionMismatch: false,
            expectedWidth: expected.width,
            expectedHeight: expected.height,
            actualWidth: actual.width,
            actualHeight: actual.height,
            changedPixelCount: changedPixelCount,
            changedPixelRatio: changedPixelRatio,
            maxChannelDelta: maxChannelDelta
        )

        return ComparisonResult(
            report: report,
            diff: makeImage(width: expected.width, height: expected.height, rgba: diffBytes)
        )
    }

    private static func dimensionMismatchResult(
        expected: PixelImage,
        actual: PixelImage
    ) -> ComparisonResult {
        let separatorWidth = 1
        let (partialWidth, partialOverflow) = expected.width.addingReportingOverflow(separatorWidth)
        let (combinedWidth, widthOverflow) = partialWidth.addingReportingOverflow(actual.width)
        guard !partialOverflow, !widthOverflow else {
            return fallbackDimensionMismatchResult(expected: expected, actual: actual)
        }

        let height = max(expected.height, actual.height)
        let (pixelCount, pixelOverflow) = combinedWidth.multipliedReportingOverflow(by: height)
        let (byteCount, byteOverflow) = pixelCount.multipliedReportingOverflow(by: 4)
        guard !pixelOverflow, !byteOverflow else {
            return fallbackDimensionMismatchResult(expected: expected, actual: actual)
        }

        var bytes = [UInt8](repeating: 0, count: byteCount)
        fill(image: expected, into: &bytes, canvasWidth: combinedWidth, xOffset: 0)

        for y in 0 ..< height {
            let offset = ((y * combinedWidth) + expected.width) * 4
            bytes[offset] = 255
            bytes[offset + 1] = 0
            bytes[offset + 2] = 0
            bytes[offset + 3] = 255
        }

        fill(
            image: actual,
            into: &bytes,
            canvasWidth: combinedWidth,
            xOffset: expected.width + separatorWidth
        )

        return ComparisonResult(
            report: dimensionMismatchReport(expected: expected, actual: actual),
            diff: makeImage(width: combinedWidth, height: height, rgba: bytes)
        )
    }

    private static func fallbackDimensionMismatchResult(
        expected: PixelImage,
        actual: PixelImage
    ) -> ComparisonResult {
        ComparisonResult(
            report: dimensionMismatchReport(expected: expected, actual: actual),
            diff: makeImage(width: 1, height: 1, rgba: [255, 0, 0, 255])
        )
    }

    private static func dimensionMismatchReport(
        expected: PixelImage,
        actual: PixelImage
    ) -> ComparisonReport {
        ComparisonReport(
            passed: false,
            dimensionMismatch: true,
            expectedWidth: expected.width,
            expectedHeight: expected.height,
            actualWidth: actual.width,
            actualHeight: actual.height,
            changedPixelCount: max(expected.width * expected.height, actual.width * actual.height),
            changedPixelRatio: 1,
            maxChannelDelta: 255
        )
    }

    private static func fill(
        image: PixelImage,
        into canvas: inout [UInt8],
        canvasWidth: Int,
        xOffset: Int
    ) {
        for y in 0 ..< image.height {
            for x in 0 ..< image.width {
                let sourceOffset = ((y * image.width) + x) * 4
                let destinationOffset = ((y * canvasWidth) + xOffset + x) * 4
                canvas[destinationOffset] = image.rgba[sourceOffset]
                canvas[destinationOffset + 1] = image.rgba[sourceOffset + 1]
                canvas[destinationOffset + 2] = image.rgba[sourceOffset + 2]
                canvas[destinationOffset + 3] = image.rgba[sourceOffset + 3]
            }
        }
    }

    private static func makeImage(width: Int, height: Int, rgba: [UInt8]) -> PixelImage {
        do {
            return try PixelImage(width: width, height: height, rgba: rgba)
        } catch {
            preconditionFailure("VisualComparator generated an invalid PixelImage: \(error)")
        }
    }
}
