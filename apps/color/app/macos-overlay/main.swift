// Limitless Color screen filter for macOS.
//
// Captures each display with ScreenCaptureKit, runs every frame through the
// person's color profile (a 3D lookup table) on the GPU, and shows the result in
// a click-through window above everything else. The mouse pointer is drawn by
// the system on top, so it never lags.
//
// The Limitless Color app starts this helper and talks to it over stdin:
//   lut <path> <size>   load a lookup table (raw RGBA8, red index fastest)
//   on | off            show or hide the filter
//   fps <n>             frames per second (15-120, default 60)
//   quit
// It answers on stdout with: ready, on, off, error <reason>.

import AppKit
import CoreMedia
import CoreVideo
import Metal
import QuartzCore
import ScreenCaptureKit

let shaderSource = """
#include <metal_stdlib>
using namespace metal;

struct VOut { float4 pos [[position]]; float2 uv; };

vertex VOut vmain(uint vid [[vertex_id]]) {
    const float2 p[4] = { float2(-1, -1), float2(1, -1), float2(-1, 1), float2(1, 1) };
    VOut o;
    o.pos = float4(p[vid], 0, 1);
    o.uv = float2((p[vid].x + 1) * 0.5, 1 - (p[vid].y + 1) * 0.5);
    return o;
}

fragment float4 fmain(VOut in [[stage_in]],
                      texture2d<float> src [[texture(0)]],
                      texture3d<float> lut [[texture(1)]],
                      constant float &size [[buffer(0)]]) {
    constexpr sampler s(filter::linear, address::clamp_to_edge);
    float3 c = src.sample(s, in.uv).rgb;
    float3 coord = (c * (size - 1.0) + 0.5) / size;
    return float4(lut.sample(s, coord).rgb, 1.0);
}
"""

func say(_ line: String) {
    FileHandle.standardOutput.write((line + "\n").data(using: .utf8)!)
}

final class Renderer {
    let device: MTLDevice
    let queue: MTLCommandQueue
    let pipeline: MTLRenderPipelineState
    var textureCache: CVMetalTextureCache?
    private let lock = NSLock()
    private var lut: MTLTexture?
    private var lutSize: Float = 2

    init?() {
        guard let device = MTLCreateSystemDefaultDevice(), let queue = device.makeCommandQueue() else { return nil }
        self.device = device
        self.queue = queue
        do {
            let library = try device.makeLibrary(source: shaderSource, options: nil)
            let desc = MTLRenderPipelineDescriptor()
            desc.vertexFunction = library.makeFunction(name: "vmain")
            desc.fragmentFunction = library.makeFunction(name: "fmain")
            desc.colorAttachments[0].pixelFormat = .bgra8Unorm
            pipeline = try device.makeRenderPipelineState(descriptor: desc)
        } catch {
            say("error shader \(error.localizedDescription)")
            return nil
        }
        CVMetalTextureCacheCreate(nil, nil, device, nil, &textureCache)
        setIdentity()
    }

    func setIdentity() {
        let n = 2
        var bytes = [UInt8]()
        for b in 0..<n { for g in 0..<n { for r in 0..<n { bytes += [UInt8(r * 255), UInt8(g * 255), UInt8(b * 255), 255] } } }
        upload(bytes, size: n)
    }

    func load(path: String, size: Int) -> Bool {
        guard size >= 2, size <= 129, let data = FileManager.default.contents(atPath: path), data.count == size * size * size * 4 else {
            return false
        }
        upload([UInt8](data), size: size)
        return true
    }

    private func upload(_ bytes: [UInt8], size: Int) {
        let desc = MTLTextureDescriptor()
        desc.textureType = .type3D
        desc.pixelFormat = .rgba8Unorm
        desc.width = size
        desc.height = size
        desc.depth = size
        desc.usage = .shaderRead
        guard let tex = device.makeTexture(descriptor: desc) else { return }
        bytes.withUnsafeBytes { raw in
            tex.replace(region: MTLRegionMake3D(0, 0, 0, size, size, size), mipmapLevel: 0, slice: 0,
                        withBytes: raw.baseAddress!, bytesPerRow: size * 4, bytesPerImage: size * size * 4)
        }
        lock.lock()
        lut = tex
        lutSize = Float(size)
        lock.unlock()
    }

    func draw(_ pixels: CVPixelBuffer, into layer: CAMetalLayer) {
        guard let cache = textureCache else { return }
        let w = CVPixelBufferGetWidth(pixels), h = CVPixelBufferGetHeight(pixels)
        var cvTex: CVMetalTexture?
        CVMetalTextureCacheCreateTextureFromImage(nil, cache, pixels, nil, .bgra8Unorm, w, h, 0, &cvTex)
        lock.lock()
        let lut = self.lut
        var size = lutSize
        lock.unlock()
        guard let cvTex, let src = CVMetalTextureGetTexture(cvTex), let lut,
              let drawable = layer.nextDrawable(), let cb = queue.makeCommandBuffer() else { return }
        let pass = MTLRenderPassDescriptor()
        pass.colorAttachments[0].texture = drawable.texture
        pass.colorAttachments[0].loadAction = .dontCare
        pass.colorAttachments[0].storeAction = .store
        guard let enc = cb.makeRenderCommandEncoder(descriptor: pass) else { return }
        enc.setRenderPipelineState(pipeline)
        enc.setFragmentTexture(src, index: 0)
        enc.setFragmentTexture(lut, index: 1)
        enc.setFragmentBytes(&size, length: MemoryLayout<Float>.size, index: 0)
        enc.drawPrimitives(type: .triangleStrip, vertexStart: 0, vertexCount: 4)
        enc.endEncoding()
        cb.present(drawable)
        cb.addCompletedHandler { _ in _ = cvTex }  // keep the frame alive until the GPU is done
        cb.commit()
    }
}

/// One display: its capture stream and the window that shows the corrected picture.
final class DisplayFilter: NSObject, SCStreamOutput, SCStreamDelegate {
    let window: NSWindow
    let layer = CAMetalLayer()
    let renderer: Renderer
    var stream: SCStream?
    let queue = DispatchQueue(label: "limitless.capture", qos: .userInteractive)

    init(screen: NSScreen, renderer: Renderer) {
        self.renderer = renderer
        window = NSWindow(contentRect: screen.frame, styleMask: .borderless, backing: .buffered, defer: false, screen: screen)
        super.init()
        window.setFrame(screen.frame, display: false)
        window.level = .screenSaver
        window.ignoresMouseEvents = true
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.isReleasedWhenClosed = false
        window.sharingType = .none
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        layer.device = renderer.device
        layer.pixelFormat = .bgra8Unorm
        layer.framebufferOnly = true
        layer.isOpaque = false
        layer.colorspace = CGColorSpace(name: CGColorSpace.sRGB)
        layer.contentsScale = screen.backingScaleFactor
        layer.drawableSize = CGSize(width: screen.frame.width * screen.backingScaleFactor,
                                    height: screen.frame.height * screen.backingScaleFactor)
        let view = NSView(frame: NSRect(origin: .zero, size: screen.frame.size))
        view.wantsLayer = true
        view.layer = layer
        window.contentView = view
    }

    func start(display: SCDisplay, excluding apps: [SCRunningApplication], scale: CGFloat, fps: Int32) {
        let filter = SCContentFilter(display: display, excludingApplications: apps, exceptingWindows: [])
        let cfg = SCStreamConfiguration()
        cfg.width = Int(CGFloat(display.width) * scale)
        cfg.height = Int(CGFloat(display.height) * scale)
        cfg.pixelFormat = kCVPixelFormatType_32BGRA
        cfg.minimumFrameInterval = CMTime(value: 1, timescale: fps)
        cfg.queueDepth = 4
        cfg.showsCursor = false
        cfg.colorSpaceName = CGColorSpace.sRGB
        let stream = SCStream(filter: filter, configuration: cfg, delegate: self)
        do {
            try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: queue)
        } catch {
            say("error stream \(error.localizedDescription)")
            return
        }
        self.stream = stream
        stream.startCapture { error in
            if let error { say("error capture \(error.localizedDescription)") }
        }
        window.orderFrontRegardless()
    }

    func stop() {
        stream?.stopCapture { _ in }
        stream = nil
        window.orderOut(nil)
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen, sampleBuffer.isValid,
              let attachments = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
              let rawStatus = attachments.first?[.status] as? Int,
              SCFrameStatus(rawValue: rawStatus) == .complete,
              let pixels = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        renderer.draw(pixels, into: layer)
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        say("error stopped \(error.localizedDescription)")
    }
}

final class Controller: NSObject {
    let renderer: Renderer
    var filters: [DisplayFilter] = []
    var enabled = false
    var fps: Int32 = 60

    init(renderer: Renderer) {
        self.renderer = renderer
        super.init()
        NotificationCenter.default.addObserver(self, selector: #selector(screensChanged),
                                               name: NSApplication.didChangeScreenParametersNotification, object: nil)
    }

    @objc func screensChanged() {
        if enabled { restart() }
    }

    func handle(_ line: String) {
        let parts = line.split(separator: " ", maxSplits: 2).map(String.init)
        guard let cmd = parts.first else { return }
        switch cmd {
        case "lut":
            // The path may contain spaces, so the size comes first after "lut" is split off the end.
            let rest = line.dropFirst(4)
            guard let space = rest.lastIndex(of: " "), let size = Int(rest[rest.index(after: space)...]) else {
                say("error lut-format"); return
            }
            let path = String(rest[..<space])
            if !renderer.load(path: path, size: size) { say("error lut-read") }
        case "on":
            enabled = true
            restart()
        case "off":
            enabled = false
            stopAll()
            say("off")
        case "fps":
            if parts.count > 1, let n = Int32(parts[1]) { fps = max(15, min(120, n)) }
            if enabled { restart() }
        case "quit":
            stopAll()
            exit(0)
        default:
            say("error unknown-command")
        }
    }

    func stopAll() {
        filters.forEach { $0.stop() }
        filters = []
    }

    func restart() {
        stopAll()
        if !CGPreflightScreenCaptureAccess() {
            CGRequestScreenCaptureAccess()
            say("error permission")
            return
        }
        SCShareableContent.getExcludingDesktopWindows(false, onScreenWindowsOnly: true) { content, error in
            DispatchQueue.main.async {
                guard let content, error == nil else {
                    say("error permission")
                    return
                }
                guard self.enabled else { return }
                let me = content.applications.filter { $0.processID == getpid() }
                for display in content.displays {
                    guard let screen = NSScreen.screens.first(where: {
                        ($0.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value == display.displayID
                    }) else { continue }
                    let f = DisplayFilter(screen: screen, renderer: self.renderer)
                    f.start(display: display, excluding: me, scale: screen.backingScaleFactor, fps: self.fps)
                    self.filters.append(f)
                }
                say("on")
            }
        }
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
guard let renderer = Renderer() else {
    say("error no-gpu")
    exit(1)
}
let controller = Controller(renderer: renderer)

Thread {
    while let line = readLine() {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { continue }
        DispatchQueue.main.async { controller.handle(trimmed) }
    }
    // The app that started us has gone away.
    DispatchQueue.main.async { controller.stopAll(); exit(0) }
}.start()

say("ready")
app.run()
