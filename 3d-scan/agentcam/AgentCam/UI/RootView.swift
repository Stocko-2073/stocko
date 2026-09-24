import AgentCamCore
import RealityKit
import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var model
    @Environment(Settings.self) private var settings
    @State private var showSettings = false
    @State private var confirmSkip = false

    var body: some View {
        VStack(spacing: 0) {
            camera
            hud
        }
        .background(Color.black.ignoresSafeArea())
        .overlay { if let p = model.placementPrompt { PlacementCard(placement: p) } }
        .overlay(alignment: .top) { if let t = model.toast { Toast(text: t) } }
        .sheet(isPresented: $showSettings) { SettingsView() }
        .confirmationDialog("Can't get this view?", isPresented: $confirmSkip, titleVisibility: .visible) {
            Button("Skip: can't reach it") { model.skipActive(reason: "can't reach that view") }
            Button("Skip: something's in the way") { model.skipActive(reason: "something is in the way") }
            Button("Skip: the page won't lock") { model.skipActive(reason: "the page won't lock") }
            Button("Keep trying", role: .cancel) {}
        } message: {
            Text(model.guidance.pageTurn.map { "Or: \($0). Photos stay correct as long as the object doesn't slide on the paper." }
                 ?? "You can also turn the page, object and all, to bring a view round to you.")
        }
    }

    /// The whole sensor image, 3:4, so what's on screen is what the photo gets.
    private var camera: some View {
        ZStack {
            if model.arAvailable {
                ARViewContainer(arView: model.arView)
            } else {
                Color(white: 0.1)
                Text("The camera view needs an iPhone.").foregroundStyle(.secondary)
            }
            GuidanceOverlay()
            BigInstruction()
            if settings.showDebug { DebugOverlay() }
        }
        .aspectRatio(3.0 / 4.0, contentMode: .fit)
        .clipped()
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Camera")
    }

    private var hud: some View {
        VStack(spacing: 10) {
            HStack {
                ConnectionBadge()
                Spacer()
                if model.outboxPending > 0 {
                    Label("\(model.outboxPending) to send", systemImage: "tray.and.arrow.up")
                        .font(.caption).foregroundStyle(.orange)
                }
                Button { showSettings = true } label: { Image(systemName: "gearshape").font(.title3) }
                    .accessibilityLabel("Settings")
            }
            RequestCard()
            Spacer(minLength: 0)
            HStack(alignment: .center) {
                Button { confirmSkip = true } label: {
                    Label("Can't reach", systemImage: "hand.raised").font(.subheadline.weight(.semibold))
                }
                .buttonStyle(.bordered)
                .disabled(model.active == nil)
                .frame(width: 130, alignment: .leading)
                Spacer()
                ReadinessRing().frame(width: 76, height: 76)
                Spacer()
                Thumbnail().frame(width: 130, alignment: .trailing)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .foregroundStyle(.white)
    }
}

struct ARViewContainer: UIViewRepresentable {
    let arView: ARView
    func makeUIView(context: Context) -> ARView { arView }
    func updateUIView(_ uiView: ARView, context: Context) {}
}

private struct ConnectionBadge: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let (color, text): (Color, String) = switch model.linkState {
        case .connected(let host): (.green, model.serverName ?? host)
        case .connecting(let host): (.yellow, "Connecting to \(host)…")
        case .reconnecting(_, let why): (.orange, why)
        case .searching: (.yellow, model.networkProblem ?? "Looking for your Mac…")
        case .idle: (.gray, "Offline")
        }
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(text).font(.caption).lineLimit(2)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Mac connection")
        .accessibilityValue(text)
    }
}

private struct RequestCard: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let a = model.active {
                HStack {
                    Text(a.id).font(.headline.monospaced())
                    Text("· \(model.pending.count) waiting").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Text(label(a)).font(.caption).foregroundStyle(.secondary)
                }
                if !a.note.isEmpty { Text(a.note).font(.title3.weight(.semibold)) }
                if let turn = model.guidance.pageTurn {
                    Label("Can't reach? \(turn)", systemImage: "arrow.triangle.2.circlepath")
                        .font(.subheadline).foregroundStyle(.cyan)
                }
            } else if let done = model.setComplete {
                Text("All done ✓").font(.title2.weight(.bold)).foregroundStyle(.green)
                Text(Self.summary(done) + ". You can put the phone down; your agent has them.")
                    .font(.subheadline).foregroundStyle(.secondary)
            } else if case .connected = model.linkState {
                Text("No photos requested. Your agent will queue some.").font(.subheadline).foregroundStyle(.secondary)
            } else {
                Text("Requests appear here once the Mac is connected.").font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Current request")
    }

    static func summary(_ done: (taken: Int, skipped: Int)) -> String {
        var text = done.taken == 1 ? "1 photo taken" : "\(done.taken) photos taken"
        if done.skipped > 0 { text += ", \(done.skipped) skipped" }
        return text
    }

    private func label(_ r: PhotoRequest) -> String {
        var parts = [r.options.lens.rawValue]
        if r.options.flash == .on { parts.append("flash") }
        if r.options.torch > 0 { parts.append("torch") }
        if r.options.raw != .none { parts.append(r.options.raw.rawValue) }
        if r.options.resolution == .mp48 { parts.append("48 MP") }
        if r.options.depth != .none { parts.append("depth") }
        if let hold = r.pose?.hold { parts.append(hold.rawValue) }
        return parts.joined(separator: " · ")
    }
}

private struct Thumbnail: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        if let image = model.lastThumbnail {
            Image(decorative: image, scale: 1).resizable().scaledToFit()
                .frame(width: 56, height: 56).clipShape(RoundedRectangle(cornerRadius: 6))
        } else {
            Color.clear.frame(width: 56, height: 56)
        }
    }
}

/// The edge arrow toward an off-screen target and the hold-still ring.
private struct GuidanceOverlay: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        GeometryReader { geo in
            let size = geo.size
            if let d = model.guidance.arrow {
                let inset: CGFloat = 36
                let (hx, hy) = (size.width / 2 - inset, size.height / 2 - inset)
                // Where the ray from the centre leaves the inset rectangle.
                let t = min(abs(d.x) > 1e-9 ? hx / abs(d.x) : .infinity, abs(d.y) > 1e-9 ? hy / abs(d.y) : .infinity)
                Image(systemName: "arrowshape.up.fill")
                    .font(.system(size: 40))
                    .foregroundStyle(.yellow)
                    .shadow(radius: 3)
                    .rotationEffect(.radians(atan2(d.x, -d.y)))
                    .position(x: size.width / 2 + d.x * t, y: size.height / 2 + d.y * t)
                    .accessibilityLabel("Move toward the target")
            }
            if model.guidance.holdProgress > 0 {
                Circle()
                    .trim(from: 0, to: model.guidance.holdProgress)
                    .stroke(.green, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .frame(width: 64, height: 64)
                    .position(x: size.width / 2, y: size.height / 2)
            }
        }
        .allowsHitTesting(false)
    }
}

private struct DebugOverlay: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        let p = model.page
        VStack(alignment: .leading, spacing: 2) {
            Text("ARKit \(p.arkit)")
            Text("markers \(p.markersUsed)/\(p.markersSeen) \(p.locked ? "LOCKED" : "not locked") gen \(p.generation)")
            if let t = p.tiltDeg, let j = p.jitterMm { Text(String(format: "tilt %.1f° jitter %.1f mm", t, j)) }
            if let r = p.rejection { Text("rejected: \(r)") }
        }
        .font(.caption2.monospaced())
        .padding(6)
        .background(.black.opacity(0.5))
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
        .allowsHitTesting(false)
    }
}

private struct PlacementCard: View {
    @Environment(AppModel.self) private var model
    let placement: Placement

    var body: some View {
        VStack(spacing: 14) {
            Text("Move the object").font(.headline)
            Text(placement.instruction).multilineTextAlignment(.center)
            Button("Done") { model.confirmPlacement() }.buttonStyle(.borderedProminent)
        }
        .padding(20)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
        .padding(32)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Placement")
    }
}

private struct Toast: View {
    let text: String
    var body: some View {
        Text(text).font(.footnote).padding(.horizontal, 12).padding(.vertical, 8)
            .background(.black.opacity(0.7), in: Capsule()).foregroundStyle(.white)
            .padding(.top, 8).padding(.horizontal, 16)
            .transition(.opacity)
    }
}

/// The one thing to do now, big enough to read at arm's length.
private struct BigInstruction: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let g = model.guidance
        VStack(spacing: 4) {
            Spacer()
            if model.active == nil, model.setComplete != nil {
                Text("All done ✓")
                    .font(.system(size: 34, weight: .bold, design: .rounded))
                    .foregroundStyle(.green)
            } else if let primary = g.primary {
                Text(primary)
                    .font(.system(size: 34, weight: .bold, design: .rounded).monospacedDigit())
                    .foregroundStyle(g.aligned ? .green : g.readiness == .findingPage ? .yellow : .white)
                if !g.secondary.isEmpty {
                    Text(g.secondary.joined(separator: "   "))
                        .font(.title3.weight(.semibold).monospacedDigit())
                        .foregroundStyle(.white.opacity(0.9))
                }
            }
        }
        .multilineTextAlignment(.center)
        .shadow(color: .black, radius: 4)
        .padding(.horizontal, 12)
        .padding(.bottom, 18)
        .frame(maxWidth: .infinity)
        .allowsHitTesting(false)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Instruction")
    }
}

/// Where things stand, in place of a shutter: finding the page, lining up,
/// holding (the ring fills), taking the photo.
private struct ReadinessRing: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let g = model.guidance
        let (icon, color): (String, Color) = switch g.readiness {
        case .idle: ("pause", .gray)
        case .findingPage: ("viewfinder", .yellow)
        case .aligning: ("scope", .white)
        case .holding: ("hand.raised.fill", .green)
        case .capturing: ("camera.fill", .green)
        }
        ZStack {
            Circle().stroke(color.opacity(0.35), lineWidth: 6)
            Circle()
                .trim(from: 0, to: g.readiness == .capturing ? 1 : g.holdProgress)
                .stroke(.green, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Image(systemName: icon).font(.system(size: 26, weight: .semibold)).foregroundStyle(color)
        }
        .accessibilityElement()
        .accessibilityLabel("Readiness")
        .accessibilityValue(String(describing: g.readiness))
    }
}
