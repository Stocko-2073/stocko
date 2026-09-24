import CoreImage
import CoreVideo
import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Image files for delivery. Everything stays on the sensor's pixel grid with
/// no orientation tag: K and the poses in meta.json refer to that grid, and
/// cv2.imread would otherwise rotate the image under them.
enum Encoding {
    private static let context = CIContext(options: [.cacheIntermediates: false])

    static func jpeg(_ buffer: CVPixelBuffer, quality: Double = 0.92) -> Data? {
        let image = CIImage(cvPixelBuffer: buffer)
        return context.jpegRepresentation(of: image, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!,
                                          options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: quality])
    }

    /// Small upright thumbnail for the HUD.
    static func thumbnail(_ buffer: CVPixelBuffer, rotationCw: Int, maxSide: CGFloat = 240) -> CGImage? {
        var image = CIImage(cvPixelBuffer: buffer)
        let orientation: CGImagePropertyOrientation = [0: .up, 90: .right, 180: .down, 270: .left][rotationCw] ?? .up
        image = image.oriented(orientation)
        let scale = maxSide / max(image.extent.width, image.extent.height)
        image = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        return context.createCGImage(image, from: image.extent)
    }

    /// Depth in metres (Float32) -> 16-bit PNG in millimetres; 0 = no depth.
    static func depthPNG(_ buffer: CVPixelBuffer) -> (data: Data, width: Int, height: Int)? {
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        guard CVPixelBufferGetPixelFormatType(buffer) == kCVPixelFormatType_DepthFloat32,
              let base = CVPixelBufferGetBaseAddress(buffer) else { return nil }
        let (w, h, stride) = (CVPixelBufferGetWidth(buffer), CVPixelBufferGetHeight(buffer), CVPixelBufferGetBytesPerRow(buffer))
        var mm = [UInt16](repeating: 0, count: w * h)
        for y in 0..<h {
            let row = (base + y * stride).assumingMemoryBound(to: Float32.self)
            for x in 0..<w {
                let v = row[x]
                mm[y * w + x] = v.isFinite && v > 0 ? UInt16(min(65535, (v * 1000).rounded())) : 0
            }
        }
        return png(pixels: mm.withUnsafeBytes { Data($0) }, width: w, height: h, bits: 16).map { ($0, w, h) }
    }

    /// ARKit confidence (0 low, 1 medium, 2 high) as an 8-bit PNG of those values.
    static func confidencePNG(_ buffer: CVPixelBuffer) -> Data? {
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddress(buffer) else { return nil }
        let (w, h, stride) = (CVPixelBufferGetWidth(buffer), CVPixelBufferGetHeight(buffer), CVPixelBufferGetBytesPerRow(buffer))
        var bytes = [UInt8](repeating: 0, count: w * h)
        for y in 0..<h { memcpy(&bytes[y * w], base + y * stride, w) }
        return png(pixels: Data(bytes), width: w, height: h, bits: 8)
    }

    private static func png(pixels: Data, width: Int, height: Int, bits: Int) -> Data? {
        let info: CGBitmapInfo = bits == 16 ? [CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue), .byteOrder16Little]
                                            : CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue)
        guard let provider = CGDataProvider(data: pixels as CFData),
              let image = CGImage(width: width, height: height, bitsPerComponent: bits, bitsPerPixel: bits,
                                  bytesPerRow: width * bits / 8, space: CGColorSpaceCreateDeviceGray(), bitmapInfo: info,
                                  provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent)
        else { return nil }
        let out = NSMutableData()
        guard let dest = CGImageDestinationCreateWithData(out, UTType.png.identifier as CFString, 1, nil) else { return nil }
        CGImageDestinationAddImage(dest, image, nil)
        return CGImageDestinationFinalize(dest) ? out as Data : nil
    }
}
