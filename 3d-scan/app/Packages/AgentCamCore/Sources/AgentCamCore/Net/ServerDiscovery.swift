import Foundation
import Network

/// Finds the Mac's AgentCam server over Bonjour (`_agentcam._tcp`). The server
/// puts its `host` (e.g. Honeypot.local) and `port` in the TXT record, so the
/// phone can connect by name instead of resolving the service endpoint.
///
/// Browsing triggers iOS's Local Network prompt, and the service type must be
/// listed under NSBonjourServices in Info.plist or browsing fails (-65555).
public final class ServerDiscovery: @unchecked Sendable {
    public enum Event: Sendable {
        case found(URL, name: String)
        case lost
        /// Usually Local Network access denied.
        case failed(String)
    }

    public static let serviceType = "_agentcam._tcp"
    public var onEvent: (@Sendable (Event) -> Void)?

    private let queue = DispatchQueue(label: "com.stocko.agentcam.discovery")
    private var browser: NWBrowser?

    public init() {}

    public func start() {
        queue.async { [self] in
            guard browser == nil else { return }
            let b = NWBrowser(for: .bonjourWithTXTRecord(type: Self.serviceType, domain: nil), using: .tcp)
            b.stateUpdateHandler = { [weak self] state in
                switch state {
                case .failed(let error): self?.onEvent?(.failed(Self.explain(error)))
                case .waiting(let error): self?.onEvent?(.failed(Self.explain(error)))
                default: break
                }
            }
            b.browseResultsChangedHandler = { [weak self] results, _ in self?.update(results) }
            b.start(queue: queue)
            browser = b
        }
    }

    public func stop() {
        queue.async { [self] in
            browser?.cancel()
            browser = nil
        }
    }

    private func update(_ results: Set<NWBrowser.Result>) {
        // More than one Mac is unusual; take a stable choice (by name).
        let servers = results.compactMap { result -> (String, URL)? in
            guard case .bonjour(let txt) = result.metadata, case .service(let name, _, _, _) = result.endpoint,
                  let host = txt["host"], let port = txt["port"].flatMap(Int.init),
                  let url = URL(string: "http://\(host):\(port)") else { return nil }
            return (name, url)
        }.sorted { $0.0 < $1.0 }
        if let (name, url) = servers.first {
            onEvent?(.found(url, name: name))
        } else {
            onEvent?(.lost)
        }
    }

    static func explain(_ error: NWError) -> String {
        if case .dns(let code) = error, code == -65570 || code == -65555 {
            return "Local Network access is off for AgentCam. Turn it on in Settings > Privacy & Security > Local Network."
        }
        return "Bonjour: \(error.localizedDescription)"
    }

    /// A manual address from Settings: "host", "host:port" or a full URL.
    public static func manualURL(_ text: String, defaultPort: Int = 47815) -> URL? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let withScheme = trimmed.contains("://") ? trimmed : "http://\(trimmed)"
        guard var c = URLComponents(string: withScheme), c.host?.isEmpty == false else { return nil }
        if c.port == nil { c.port = defaultPort }
        c.path = ""
        return c.url
    }
}
