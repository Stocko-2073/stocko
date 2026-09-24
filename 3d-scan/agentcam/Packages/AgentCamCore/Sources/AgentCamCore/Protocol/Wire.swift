import Foundation

/// JSON coding for the wire protocol, whose source of truth is the server's
/// models (agentcam/mcp/src/agentcam/models.py): snake_case keys, except the camera
/// matrix, which is `K` as in every vision text.
public enum Wire {
    public static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase     // leaves "K" alone
        return d
    }()

    public static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .custom { path in SnakeKey(snake(path.last!.stringValue)) }
        e.outputFormatting = [.sortedKeys]
        return e
    }()

    /// camelCase -> snake_case; an all-caps key such as `K` passes through.
    static func snake(_ key: String) -> String {
        if key.uppercased() == key { return key }
        var out = ""
        var previous: Character?
        for c in key {
            if c.isUppercase, let p = previous, p.isLowercase || p.isNumber {
                out.append("_")
            }
            out.append(Character(c.lowercased()))
            previous = c
        }
        return out
    }

    private struct SnakeKey: CodingKey {
        var stringValue: String
        var intValue: Int? { nil }
        init(_ s: String) { stringValue = s }
        init?(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { nil }
    }

    /// Every message carries its type in `t`.
    public static func messageType(_ data: Data) -> String? {
        struct Header: Decodable { let t: String }
        return try? decoder.decode(Header.self, from: data).t
    }

    public static func text<T: Encodable>(_ value: T) throws -> String {
        String(decoding: try encoder.encode(value), as: UTF8.self)
    }
}

public let protocolVersion = 1
