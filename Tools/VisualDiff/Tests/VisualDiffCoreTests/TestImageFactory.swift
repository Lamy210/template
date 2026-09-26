import VisualDiffCore

enum TestImageFactory {
    static func solid(
        width: Int,
        height: Int,
        rgba: [UInt8]
    ) throws -> PixelImage {
        precondition(rgba.count == 4)
        return try PixelImage(
            width: width,
            height: height,
            rgba: Array(repeating: rgba, count: width * height).flatMap(\.self)
        )
    }
}
