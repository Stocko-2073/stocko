import CoreBluetooth
import CryptoKit
// Native Mac maintenance client; drive continues to use the existing normalized protocol.
import Foundation

private let managementService = CBUUID(string: "7b1a0000-6f4b-4c2e-9d3a-2e5f1c8a9b01")
private let managementRequest = CBUUID(string: "7b1a0004-6f4b-4c2e-9d3a-2e5f1c8a9b01")
private let managementResponse = CBUUID(string: "7b1a0005-6f4b-4c2e-9d3a-2e5f1c8a9b01")

final class ManagementCLI: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate,
  @unchecked Sendable
{
  static let commands: Set<String> = [
    "exec", "shell", "logs", "stream", "jobs", "wifi", "diagnostics", "ota",
  ]
  var args: [String]
  var host: String?
  var bleName: String?
  var json = false
  var timeout: Double = 90
  var explicitTimeout = false
  var deadline = 60000
  var central: CBCentralManager!
  var peripheral: CBPeripheral?
  var requestChar: CBCharacteristic?
  var ws: URLSessionWebSocketTask?
  var generation = 0
  var fragments: [Data] = []
  var writing = false
  var txID: UInt16 = 0
  var rxID: UInt16 = 0
  var rx = Data()
  var rxStarted = Date.distantPast
  var nextID = 0
  var currentID = 0
  var currentJob: Int?
  var hello: [String: Any] = [:]
  var collected = ""
  var completion: ((Int) -> Void)?
  var timer: DispatchSourceTimer?
  var interrupt: DispatchSourceSignal?
  var leaseTimer: DispatchSourceTimer?
  var pollTimer: DispatchSourceTimer?
  var renewSequence = 0
  var cancelID: Int?
  var began = false
  var updating = false
  var reconnecting = false
  var updateBoot = ""
  var expected: [String: Any]?
  var updateStarted = Date()
  var observedDropped = 0

  init(arguments: [String]) {
    args = arguments
    super.init()
    for option in ["--wifi", "--ble", "--timeout", "--deadline"] {
      if let i = args.firstIndex(of: option) {
        guard i + 1 < args.count else { fail(2, "missing value for \(option)") }
        let value = args[i + 1]
        switch option {
        case "--wifi": host = value
        case "--ble": bleName = value
        case "--timeout":
          timeout = Double(value) ?? 0
          explicitTimeout = true
        default: deadline = Int(value) ?? 0
        }
        args.removeSubrange(i...i + 1)
      }
    }
    if let i = args.firstIndex(of: "--json") {
      json = true
      args.remove(at: i)
    }
    guard !(host != nil && bleName != nil), timeout > 0, timeout.isFinite,
      deadline > 0, deadline <= 3_600_000
    else { fail(2, "invalid transport, timeout or deadline") }
  }
  func fail(_ code: Int32, _ message: String) -> Never {
    if json,
      let data = try? JSONSerialization.data(
        withJSONObject: ["type": "error", "code": code, "error": message], options: [.sortedKeys])
    {
      print(String(decoding: data, as: UTF8.self))
    } else {
      FileHandle.standardError.write(Data((message + "\n").utf8))
    }
    exit(code)
  }
  func note(_ message: String) { FileHandle.standardError.write(Data((message + "\n").utf8)) }
  func run() -> Never {
    signal(SIGINT, SIG_IGN)
    let sig = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
    sig.setEventHandler { [self] in
      leaseTimer?.cancel()
      if let job = currentJob {
        cancelID = send(["op": "cancel", "job": job])
        note("cancelling job \(job)")
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [self] in
          fail(4, "cancellation was not acknowledged; inspect the job after reconnecting")
        }
      } else {
        exit(130)
      }

    }
    sig.resume()
    interrupt = sig
    armTimeout(timeout)
    connect()
    dispatchMain()
  }
  func armTimeout(_ seconds: Double) {
    timer?.cancel()
    let t = DispatchSource.makeTimerSource(queue: .main)
    t.schedule(deadline: .now() + seconds)
    t.setEventHandler { [self] in
      fail(
        124,
        updating
          ? "update not confirmed; reconnect and inspect diagnostics"
          : "request timed out; bounded jobs may still be running")
    }
    t.resume()
    timer = t
  }
  func connect() {
    generation += 1
    let g = generation
    if let host {
      guard let url = URL(string: "ws://\(host)/manage") else { fail(2, "invalid Wi-Fi host") }
      let task = URLSession.shared.webSocketTask(with: url)
      ws = task
      task.resume()
      receiveWS(task, generation: g)
    } else {
      if central == nil {
        central = CBCentralManager(delegate: self, queue: .main)
      } else if central.state == .poweredOn {
        central.scanForPeripherals(withServices: [managementService])
      }
    }
  }
  func receiveWS(_ task: URLSessionWebSocketTask, generation g: Int) {
    Task {
      do {
        let message = try await task.receive()
        DispatchQueue.main.async { [self] in
          guard g == generation else { return }
          switch message {
          case .string(let s): receive(Data(s.utf8))
          case .data(let d): receive(d)
          @unknown default: fail(4, "unsupported WebSocket message")
          }
          receiveWS(task, generation: g)
        }
      } catch {
        DispatchQueue.main.async { [self] in
          if g == generation { disconnected(error.localizedDescription) }
        }
      }
    }
  }
  func disconnected(_ reason: String) {
    fragments = []
    writing = false
    requestChar = nil
    rx = Data()
    guard updating else { fail(4, "connection lost: \(reason); inspect jobs after reconnecting") }
    if reconnecting { return }
    reconnecting = true
    pollTimer?.cancel()
    leaseTimer?.cancel()
    completion = nil
    currentJob = nil
    note("reconnecting to verify candidate")
    DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [self] in
      reconnecting = false
      connect()
    }
  }
  @discardableResult func send(_ fields: [String: Any]) -> Int {
    nextID += 1
    var message = fields
    message["id"] = nextID
    message["session"] = hello["session"]
    guard let data = try? JSONSerialization.data(withJSONObject: message), data.count < 768 else {
      fail(2, "request exceeds firmware limit")
    }
    if let ws, host != nil {
      let g = generation
      Task {
        do { try await ws.send(.string(String(decoding: data, as: UTF8.self))) } catch {
          DispatchQueue.main.async { [self] in
            if g == generation { disconnected(error.localizedDescription) }
          }
        }
      }
    } else {
      guard let p = peripheral, requestChar != nil else { fail(4, "BLE management is unavailable") }
      txID &+= 1
      let count = max(1, min(507, p.maximumWriteValueLength(for: .withResponse)) - 5)
      for off in stride(from: 0, to: data.count, by: count) {
        let end = min(data.count, off + count)
        var fragment = Data([
          UInt8((off == 0 ? 1 : 0) | (end == data.count ? 2 : 0)), UInt8(truncatingIfNeeded: txID),
          UInt8(txID >> 8), UInt8(truncatingIfNeeded: off), UInt8(off >> 8),
        ])
        fragment.append(data[off..<end])
        fragments.append(fragment)
      }
      guard fragments.count <= 128 else { fail(4, "BLE outgoing queue full") }
      writeNext()
    }
    return nextID
  }
  func writeNext() {
    if !writing, !fragments.isEmpty, let p = peripheral, let c = requestChar {
      writing = true
      p.writeValue(fragments.removeFirst(), for: c, type: .withResponse)
    }
  }
  func request(_ fields: [String: Any], done: @escaping (Int) -> Void) {
    currentJob = nil
    collected = ""
    completion = done
    currentID = send(fields)
    if !updating { armTimeout(timeout) }
  }
  func exec(_ words: [String], done: @escaping (Int) -> Void) {
    request(["op": "exec", "args": words, "deadline_ms": deadline], done: done)
  }
  func finish(_ code: Int) {
    if code != 0 { fail(Int32(code), "command failed (exit \(code))") }
    exit(0)
  }
  func receive(_ data: Data) {
    guard let r = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
      let type = r["type"] as? String
    else { fail(4, "malformed management response") }
    if json { print(String(decoding: data, as: UTF8.self)) }
    let dropped = r["dropped"] as? Int ?? 0
    if dropped > observedDropped {
      note(
        "warning: \(dropped-observedDropped) response records dropped; retained output is available with jobs result"
      )
      observedDropped = dropped
    }
    if type == "hello" {
      guard r["protocol"] as? Int == 1 else { fail(3, "unsupported management protocol") }
      hello = r
      nextID = 0
      observedDropped = 0
      if updating {
        verifyCandidate()
        return
      }
      if !began {
        began = true
        startCommand()
      }
      return
    }
    let id = r["id"] as? Int ?? 0
    if type == "output", let text = r["data"] as? String {
      if id == currentID { collected += text }
      if !json { print(text, terminator: "") }
    }
    if type == "log" || type == "stream" {
      if !json { print(r["data"] as? String ?? "") }
      if let lost = r["lost"] as? Int, lost > 0 { note("\(lost) retained log records overwritten") }
    }
    if type == "jobs", !json, let entries = r["jobs"] as? [[String: Any]] {
      for entry in entries {
        print(
          "job \(entry["job"] ?? "?"): \((entry["done"] as? Bool ?? false) ? "finished" : "running"), code \(entry["code"] ?? "?")"
        )
      }
    }
    if type == "job", !json {
      print(
        "job \(r["job"] ?? "?"): \((r["done"] as? Bool ?? false) ? "finished" : "running"), code \(r["code"] ?? "?")"
      )
    }
    if id == currentID && type == "result" {
      if !json { print(r["data"] as? String ?? "", terminator: "") }
      let offset = r["next"] as? Int ?? 0
      let total = r["total"] as? Int ?? 0
      if offset < total {
        currentID = send(["op": "result", "job": r["job"] ?? 0, "offset": offset])
      } else {
        if r["done"] as? Bool != true { note("job still running") }
        let cb = completion
        completion = nil
        cb?(r["code"] as? Int ?? 0)
      }
    }
    if id == currentID && type == "accepted" {
      currentJob = r["job"] as? Int
      note("accepted job \(currentJob ?? 0)")
    }
    if id == cancelID && type == "finished" {
      if (r["code"] as? Int ?? 1) == 0 { exit(130) }
      fail(1, "cancellation refused; inspect retained job result")
    }
    if id == currentID && type == "finished" {
      if cancelID != nil { return }
      if !json, let error = r["error"] as? String { note(error) }
      currentJob = nil
      leaseTimer?.cancel()
      if let truncated = r["truncated"] as? Int, truncated > 0 {
        note("warning: retained output truncated by \(truncated) bytes")
      }
      let cb = completion
      completion = nil
      cb?(r["code"] as? Int ?? 1)
    }
    if id == currentID && type == "running" {
      note("job still running")
      completion?(0)
      completion = nil
    }
  }
  func startCommand() {
    let command = args[0]
    let words = Array(args.dropFirst())
    switch command {
    case "exec":
      guard !words.isEmpty else { fail(2, "exec requires command arguments") }
      exec(words) { [self] in finish($0) }
      startLeaseIfNeeded(words)
    case "diagnostics": request(["op": "diagnostics"]) { [self] in finish($0) }
    case "wifi": exec(["wifi"] + words) { [self] in finish($0) }
    case "jobs":
      if words.isEmpty {
        request(["op": "jobs"]) { [self] in finish($0) }
      } else if words.count == 2, ["result", "cancel"].contains(words[0]), let id = Int(words[1]),
        id > 0
      {
        request(["op": words[0], "job": id]) { [self] in finish($0) }
      } else {
        fail(2, "jobs [result|cancel ID]")
      }
    case "logs":
      request(["op": "logs", "since": Int(words.first ?? "0") ?? 0]) { [self] code in
        if code != 0 { finish(code) }
        timer?.cancel()
      }
    case "stream":
      exec(["stream", "on", words.first ?? "20"]) { [self] code in
        if code != 0 { finish(code) }
        timer?.cancel()
      }
    case "shell": shellPrompt()
    case "ota": ota(words)
    default: fail(2, "unsupported command")
    }
  }
  func startLeaseIfNeeded(_ words: [String]) {
    let continuous =
      (words.first == "drive" && words.count > 3 && Double(words[3]) == 0)
      || (words.first == "wheel" && words.count > 2
        && (words[2] == "spin" || (words[2] == "vel" && words.count > 4 && Double(words[4]) == 0)
          || (words[2] == "loop" && words.last == "on")))
    guard continuous else { return }
    renewSequence = 0
    let t = DispatchSource.makeTimerSource(queue: .main)
    t.schedule(deadline: .now() + 0.3, repeating: 0.3)
    t.setEventHandler { [self] in
      if let job = currentJob {
        renewSequence += 1
        send(["op": "renew", "job": job, "seq": renewSequence])
      }
    }
    t.resume()
    leaseTimer = t
  }
  func shellPrompt() {
    timer?.cancel()
    if !json {
      print("ubot> ", terminator: "")
      fflush(stdout)
    }
    DispatchQueue.global().async { [self] in
      guard let line = readLine() else { exit(0) }
      DispatchQueue.main.async { [self] in
        do {
          let words = try Self.split(line)
          if words.isEmpty {
            shellPrompt()
            return
          }
          if words == ["exit"] || words == ["quit"] { exit(0) }
          exec(words) { [self] code in
            if code != 0 { note("exit \(code)") }
            shellPrompt()
          }
          startLeaseIfNeeded(words)
        } catch {
          note("unclosed quote or escape")
          shellPrompt()
        }
      }
    }
  }
  static func split(_ text: String) throws -> [String] {
    var result: [String] = []
    var word = ""
    var quote: Character?
    var escape = false
    var started = false
    for c in text {
      if escape {
        word.append(c)
        escape = false
        started = true
      } else if c == "\\" && quote != "'" {
        escape = true
        started = true
      } else if let q = quote {
        if c == q { quote = nil } else { word.append(c) }
      } else if c == "'" || c == "\"" {
        quote = c
        started = true
      } else if c.isWhitespace {
        if started {
          result.append(word)
          word = ""
          started = false
        }
      } else {
        word.append(c)
        started = true
      }
    }
    if quote != nil || escape { throw NSError(domain: "shell", code: 2) }
    if started { result.append(word) }
    return result
  }
  func ota(_ words: [String]) {
    guard let action = words.first else {
      exec(["ota"]) { [self] in finish($0) }
      return
    }
    switch action {
    case "confirm":
      guard words.count == 3 else { fail(2, "ota confirm EXPECTED_VERSION EXPECTED_ELF_SHA256") }
      request([
        "op": "confirm", "version": words[1], "image": words[2], "boot": hello["boot"] ?? "",
      ]) { [self] in finish($0) }
    case "cancel": exec(["ota", "cancel"]) { [self] in finish($0) }
    case "source":
      guard words.count == 2 else { fail(2, "ota source https://bucket") }
      exec(["ota", "url", words[1]]) { [self] in finish($0) }
    case "check":
      exec(["ota", "check"]) { [self] code in
        if code != 0 { finish(code) }
        exec(["ota"]) { [self] in finish($0) }
      }
    case "upload":
      guard words.count == 2, let host else { fail(2, "ota upload FILE.bin requires --wifi HOST") }
      let file = URL(fileURLWithPath: words[1])
      do {
        let data = try Data(contentsOf: file, options: .mappedIfSafe)
        guard data.count >= 288, data[0] == 0xe9, data[12] == 9, data[13] == 0 else {
          fail(2, "not an ESP32-S3 application image")
        }
        func field(_ start: Int, _ count: Int) -> String {
          String(decoding: data[start..<start + count].prefix(while: { $0 != 0 }), as: UTF8.self)
        }
        let metadata: [String: Any] = [
          "version": field(48, 32), "project": field(80, 32), "target": "esp32s3",
          "size": data.count,
          "sha256": SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(),
          "image": data[176..<208].map { String(format: "%02x", $0) }.joined(),
        ]
        beginUpdate(metadata)
        guard let url = URL(string: "http://\(host)/ota") else { fail(2, "invalid host") }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.timeoutInterval = explicitTimeout ? timeout : 240
        for (header, key) in [
          ("Version", "version"), ("Project", "project"), ("Target", "target"),
          ("SHA256", "sha256"), ("Image", "image"),
        ] { req.setValue(metadata[key] as? String, forHTTPHeaderField: "X-Ubot-\(header)") }
        note("uploading \(data.count) bytes")
        URLSession.shared.uploadTask(with: req, fromFile: file) { [self] _, response, error in
          DispatchQueue.main.async { [self] in
            if let error { fail(4, "upload interrupted: \(error.localizedDescription)") }
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
              fail(1, "upload refused or invalid image")
            }
            note("image written; awaiting reboot and confirmation")
          }
        }.resume()
        pollUpdate()
      } catch { fail(2, "cannot read image: \(error)") }
    case "install":
      if words.count == 2 {
        fetchRelease(words[1])
      } else if words.count == 1 {
        exec(["ota"]) { [self] code in
          if code != 0 { finish(code) }
          guard
            let line = collected.split(separator: "\n").first(where: {
              $0.hasPrefix("stored url: https://")
            })
          else { fail(2, "configure ota source first") }
          fetchRelease(
            String(line.dropFirst(12)).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
              + "/manifest.json")
        }
      } else {
        fail(2, "ota install [https://.../manifest.json]")
      }
    default: fail(2, "ota [source URL | check | install [MANIFEST_URL] | upload FILE.bin]")
    }
  }
  func fetchRelease(_ address: String) {
    guard let url = URL(string: address), url.scheme == "https" else {
      fail(2, "HTTPS manifest URL required")
    }
    URLSession.shared.dataTask(with: url) { [self] data, response, error in
      DispatchQueue.main.async { [self] in
        guard error == nil, (response as? HTTPURLResponse)?.statusCode == 200, let data,
          data.count < 1536,
          let manifest = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        else { fail(4, "could not fetch release manifest") }
        beginUpdate(manifest)
        exec(["ota", "start", address]) { [self] code in if code != 0 { finish(code) } }
        pollUpdate()
      }
    }.resume()
  }
  func beginUpdate(_ manifest: [String: Any]) {
    guard manifest["project"] as? String == hello["project"] as? String,
      manifest["target"] as? String == "esp32s3",
      let image = manifest["image"] as? String, image.count == 64,
      let sha = manifest["sha256"] as? String, sha.count == 64,
      let version = manifest["version"] as? String, !version.isEmpty
    else { fail(2, "invalid release identity") }
    expected = manifest
    updating = true
    updateBoot = hello["boot"] as? String ?? ""
    updateStarted = Date()
    armTimeout(explicitTimeout ? timeout : 240)
  }
  func pollUpdate() {
    let t = DispatchSource.makeTimerSource(queue: .main)
    t.schedule(deadline: .now() + 1, repeating: 2)
    t.setEventHandler { [self] in if !reconnecting { send(["op": "exec", "args": ["ota"]]) } }
    t.resume()
    pollTimer = t
  }
  func verifyCandidate() {
    guard hello["boot"] as? String != updateBoot else {
      pollUpdate()
      return
    }
    guard hello["version"] as? String == expected?["version"] as? String,
      hello["image"] as? String == expected?["image"] as? String
    else { fail(1, "rollback or unexpected image after update; run diagnostics") }
    pollTimer?.cancel()
    request([
      "op": "confirm", "version": expected?["version"] ?? "", "image": expected?["image"] ?? "",
      "boot": hello["boot"] ?? "",
    ]) { [self] code in
      if code != 0 { fail(1, "candidate rejected health confirmation") }
      note("verified and confirmed \(hello["version"] ?? "")")
      exit(0)
    }
  }
  func centralManagerDidUpdateState(_ central: CBCentralManager) {
    if central.state == .poweredOn {
      central.scanForPeripherals(withServices: [managementService])
    } else if central.state == .unauthorized || central.state == .unsupported
      || central.state == .poweredOff
    {
      fail(4, "Bluetooth unavailable or permission denied")
    }
  }
  func centralManager(
    _ central: CBCentralManager, didDiscover p: CBPeripheral, advertisementData: [String: Any],
    rssi: NSNumber
  ) {
    if let name = bleName, name != p.name && name != p.identifier.uuidString { return }
    central.stopScan()
    peripheral = p
    p.delegate = self
    central.connect(p)
  }
  func centralManager(_ central: CBCentralManager, didConnect p: CBPeripheral) {
    p.discoverServices([managementService])
  }
  func centralManager(_ central: CBCentralManager, didFailToConnect p: CBPeripheral, error: Error?)
  { disconnected(error?.localizedDescription ?? "BLE connect failed") }
  func centralManager(
    _ central: CBCentralManager, didDisconnectPeripheral p: CBPeripheral, error: Error?
  ) { disconnected(error?.localizedDescription ?? "BLE disconnected") }
  func peripheral(_ p: CBPeripheral, didDiscoverServices error: Error?) {
    guard error == nil, let service = p.services?.first(where: { $0.uuid == managementService })
    else { fail(3, "management service missing") }
    p.discoverCharacteristics([managementRequest, managementResponse], for: service)
  }
  func peripheral(
    _ p: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?
  ) {
    requestChar = service.characteristics?.first(where: { $0.uuid == managementRequest })
    guard error == nil, requestChar != nil,
      let response = service.characteristics?.first(where: { $0.uuid == managementResponse })
    else { fail(3, "firmware has no BLE management characteristics") }
    p.setNotifyValue(true, for: response)
  }
  func peripheral(
    _ p: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?
  ) { if let error { fail(4, "indications failed: \(error)") } }
  func peripheral(
    _ p: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?
  ) {
    writing = false
    if let error { fail(1, "BLE request refused: \(error)") }
    writeNext()
  }
  func peripheral(
    _ p: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?
  ) {
    guard characteristic.uuid == managementResponse, error == nil, let data = characteristic.value,
      data.count > 5
    else { fail(4, "invalid BLE management fragment") }
    let b = [UInt8](data)
    let id = UInt16(b[1]) | UInt16(b[2]) << 8
    let off = Int(b[3]) | Int(b[4]) << 8
    if b[0] & 1 != 0 {
      guard off == 0 else { fail(4, "fragment offset") }
      rx = Data()
      rxID = id
      rxStarted = Date()
    }
    guard b[0] & 0xfc == 0, id == rxID, off == rx.count, rx.count + data.count - 5 < 768,
      Date().timeIntervalSince(rxStarted) < 10
    else { fail(4, "fragment sequence or size") }
    rx.append(contentsOf: b.dropFirst(5))
    if b[0] & 2 != 0 {
      receive(rx)
      rx = Data()
    }
  }
}
