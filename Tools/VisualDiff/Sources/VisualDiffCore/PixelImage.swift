import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

public enum PixelImageError: Error, Equatable {
    case invalidDimensions(width: Int, height: Int)
    case invalidRGBAByteCount(expected: Int, actual: Int)
    case imageTooLarge
    case cannotOpenPNG(URL)
    case cannotDecodePNG(URL)
    case cannotCreateColorSpace
    case cannotCreateBitmapContext
    case cannotCreateDataProvider
    case cannotCreateCGImage
    case cannotCreatePNGDestination(URL)
    case cannotFinalizePNG(URL)
}

public struct PixelImage: Sendable, Equatable {
    public let width: Int
    public let height: Int
    public let rgba: [UInt8]

    public init(width: Int, height: Int, rgba: [UInt8]) throws {
        guard width > 0, height > 0 else {
            throw PixelImageError.invalidDimensions(width: width, height: height)
        }

        let (pixelCount, pixelOverflow) = width.multipliedReportingOverflow(by: height)
        let (expectedByteCount, byteOverflow) = pixelCount.multipliedReportingOverflow(by: 4)
        guard !pixelOverflow, !byteOverflow else {
            throw PixelImageError.imageTooLarge
        }
        guard rgba.count == expectedByteCount else {
            throw PixelImageError.invalidRGBAByteCount(expected: expectedByteCount, actual: rgba.count)
        }

        self.width = width
        self.height = height
        self.rgba = rgba
    }

    public static func loadPNG(from url: URL) throws -> PixelImage {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else {
            throw PixelImageError.cannotOpenPNG(url)
        }
        guard let sourceImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            throw PixelImageError.cannotDecodePNG(url)
        }
        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) else {
            throw PixelImageError.cannotCreateColorSpace
        }

        let width = sourceImage.width
        let height = sourceImage.height
        let (pixelCount, pixelOverflow) = width.multipliedReportingOverflow(by: height)
        let (byteCount, byteOverflow) = pixelCount.multipliedReportingOverflow(by: 4)
        guard !pixelOverflow, !byteOverflow else {
            throw PixelImageError.imageTooLarge
        }

        var bytes = [UInt8](repeating: 0, count: byteCount)
        let drewImage = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress,
                width: width,
                height: height,
                bitsPerComponent: 8,
                bytesPerRow: width * 4,
                space: colorSpace,
                bitmapInfo: rgbaBitmapInfo.rawValue
            ) else {
                return false
            }

            context.interpolationQuality = .none
            context.draw(sourceImage, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }

        guard drewImage else {
            throw PixelImageError.cannotCreateBitmapContext
        }
        return try PixelImage(width: width, height: height, rgba: bytes)
    }

    public func writePNG(to url: URL) throws {
        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) else {
            throw PixelImageError.cannotCreateColorSpace
        }

        let data = Data(rgba) as CFData
        guard let provider = CGDataProvider(data: data) else {
            throw PixelImageError.cannotCreateDataProvider
        }
        guard let image = CGImage(
            width: width,
            height: height,
            bitsPerComponent: 8,
            bitsPerPixel: 32,
            bytesPerRow: width * 4,
            space: colorSpace,
            bitmapInfo: Self.rgbaBitmapInfo,
            provider: provider,
            decode: nil,
            shouldInterpolate: false,
            intent: .defaultIntent
        ) else {
            throw PixelImageError.cannotCreateCGImage
        }

        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        guard let destination = CGImageDestinationCreateWithURL(
            url as CFURL,
            UTType.png.identifier as CFString,
            1,
            nil
        ) else {
            throw PixelImageError.cannotCreatePNGDestination(url)
        }

        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else {
            throw PixelImageError.cannotFinalizePNG(url)
        }
    }

    private static let rgbaBitmapInfo = CGBitmapInfo.byteOrder32Big.union(
        CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue)
    )
}
