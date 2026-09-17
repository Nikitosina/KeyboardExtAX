import Foundation
import Network
import XCTest

private final class SnapshotNode {
    let type: String
    let rawDescription: String
    let identifier: String?
    let label: String?
    let frame: [String: Double]?
    var children: [SnapshotNode] = []

    init(type: String, rawDescription: String, identifier: String?, label: String?, frame: [String: Double]?) {
        self.type = type
        self.rawDescription = rawDescription
        self.identifier = identifier
        self.label = label
        self.frame = frame
    }

    var dictionary: [String: Any] {
        [
            "type": type,
            "raw_description": rawDescription,
            "identifier": identifier ?? NSNull(),
            "label": label ?? NSNull(),
            "frame": frame ?? NSNull(),
            "center": center ?? NSNull(),
            "children": children.map(\.dictionary),
        ]
    }

    private var center: [String: Double]? {
        guard
            let frame,
            let x = frame["x"],
            let y = frame["y"],
            let width = frame["width"],
            let height = frame["height"]
        else {
            return nil
        }
        return ["x": x + width / 2, "y": y + height / 2]
    }
}

private struct PendingCommand {
    let request: [String: Any]
    let connection: NWConnection
}

private final class CommandServer: @unchecked Sendable {
    private let listener: NWListener
    private let queue = DispatchQueue(label: "dev.keyboardextax.server")
    private let condition = NSCondition()
    private var commands: [PendingCommand] = []

    init(port: NWEndpoint.Port) throws {
        listener = try NWListener(using: .tcp, on: port)
        listener.newConnectionHandler = { [weak self] connection in
            self?.receive(from: connection)
        }
    }

    func start() {
        listener.start(queue: queue)
    }

    func nextCommand() -> PendingCommand {
        condition.lock()
        while commands.isEmpty {
            condition.wait()
        }
        let command = commands.removeFirst()
        condition.unlock()
        return command
    }

    func respond(_ response: [String: Any], to connection: NWConnection) throws {
        var data = try JSONSerialization.data(withJSONObject: response, options: [.sortedKeys])
        data.append(0x0A)
        let sent = DispatchSemaphore(value: 0)
        connection.send(content: data, completion: .contentProcessed { _ in sent.signal() })
        _ = sent.wait(timeout: .now() + 2)
        connection.cancel()
    }

    func cancel() {
        listener.cancel()
    }

    private func receive(from connection: NWConnection) {
        connection.start(queue: queue)
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { [weak self] data, _, _, _ in
            guard
                let self,
                let data,
                let request = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else {
                connection.cancel()
                return
            }
            condition.lock()
            commands.append(PendingCommand(request: request, connection: connection))
            condition.signal()
            condition.unlock()
        }
    }
}

final class PersistentKeyboardExtAXTests: XCTestCase {
    private let environment = ProcessInfo.processInfo.environment
    private var cachedKeyboard: XCUIApplication?
    private var cachedBundleID: String?

    func testServeSnapshots() throws {
        continueAfterFailure = true
        let portValue = UInt16(environment["KEYBOARD_EXT_AX_PORT"] ?? "19427") ?? 19_427
        let port = NWEndpoint.Port(rawValue: portValue)!
        let server = try CommandServer(port: port)
        server.start()
        print("KEYBOARD_EXT_AX_READY port=\(portValue)")

        var shouldStop = false
        while !shouldStop {
            let pending = server.nextCommand()
            let requestID = pending.request["id"] ?? NSNull()
            let command = pending.request["command"] as? String
            if command == "snapshot" {
                do {
                    let response = try makeSnapshot(request: pending.request, requestID: requestID)
                    try server.respond(response, to: pending.connection)
                } catch let error as SnapshotError {
                    try server.respond(
                        [
                            "id": requestID,
                            "ok": false,
                            "error": ["code": error.code, "message": error.localizedDescription],
                        ],
                        to: pending.connection
                    )
                } catch {
                    try server.respond(
                        [
                            "id": requestID,
                            "ok": false,
                            "error": ["code": "snapshot_failed", "message": error.localizedDescription],
                        ],
                        to: pending.connection
                    )
                }
            } else if command == "ping" {
                try server.respond(
                    [
                        "id": requestID,
                        "ok": true,
                        "simulator_udid": environment["SIMULATOR_UDID"].map { $0 as Any } ?? NSNull(),
                    ],
                    to: pending.connection
                )
            } else if command == "shutdown" {
                try server.respond(["id": requestID, "ok": true], to: pending.connection)
                shouldStop = true
            } else {
                try server.respond(
                    [
                        "id": requestID,
                        "ok": false,
                        "error": ["code": "unknown_command", "message": "unknown command"],
                    ],
                    to: pending.connection
                )
            }
        }
        server.cancel()
    }

    private func makeSnapshot(request: [String: Any], requestID: Any) throws -> [String: Any] {
        guard
            let extensionBundleID = request["extension_bundle_id"] as? String,
            !extensionBundleID.isEmpty
        else {
            throw SnapshotError.extensionBundleIDMissing
        }

        let start = CFAbsoluteTimeGetCurrent()
        let includeDiagnostics = request["raw"] as? Bool == true
        if cachedBundleID == extensionBundleID, let cachedKeyboard {
            let attempt = snapshotResponse(
                keyboard: cachedKeyboard,
                extensionBundleID: extensionBundleID,
                requestID: requestID,
                start: start
            )
            if let response = attempt.response {
                return response
            }
            if includeDiagnostics {
                return attachmentDiagnosticResponse(
                    descriptions: attempt.descriptions,
                    requestID: requestID,
                    start: start
                )
            }
        }

        let keyboard = XCUIApplication(bundleIdentifier: extensionBundleID)
        let attempt = snapshotResponse(
            keyboard: keyboard,
            extensionBundleID: extensionBundleID,
            requestID: requestID,
            start: start
        )
        guard let response = attempt.response else {
            cachedKeyboard = nil
            cachedBundleID = nil
            if includeDiagnostics {
                return attachmentDiagnosticResponse(
                    descriptions: attempt.descriptions,
                    requestID: requestID,
                    start: start
                )
            }
            throw SnapshotError.extensionNotActive
        }
        cachedKeyboard = keyboard
        cachedBundleID = extensionBundleID
        return response
    }

    private func snapshotResponse(
        keyboard: XCUIApplication,
        extensionBundleID: String,
        requestID: Any,
        start: CFAbsoluteTime
    ) -> (response: [String: Any]?, descriptions: [String]) {
        var descriptions: [String] = []
        for delay in [0.0, 0.25, 0.75] {
            if delay > 0 {
                Thread.sleep(forTimeInterval: delay)
            }
            let description = keyboard.debugDescription
            descriptions.append(description)
            guard let root = parseTree(description) else { continue }
            let pid = firstCapture(in: description, pattern: #"pid: ([0-9]+)"#).flatMap(Int.init)
            return ([
                "id": requestID,
                "snapshot_id": UUID().uuidString,
                "ok": true,
                "simulator_udid": environment["SIMULATOR_UDID"].map { $0 as Any } ?? NSNull(),
                "extension_bundle_id": extensionBundleID,
                "pid": pid.map { $0 as Any } ?? NSNull(),
                "elapsed_ms": (CFAbsoluteTimeGetCurrent() - start) * 1_000,
                "tree": root.dictionary,
            ], descriptions)
        }
        return (nil, descriptions)
    }

    private func attachmentDiagnosticResponse(
        descriptions: [String],
        requestID: Any,
        start: CFAbsoluteTime
    ) -> [String: Any] {
        let initialDescription = descriptions.first ?? ""
        let finalDescription = descriptions.last ?? ""
        return [
            "id": requestID,
            "ok": false,
            "error": [
                "code": SnapshotError.extensionNotActive.code,
                "message": SnapshotError.extensionNotActive.localizedDescription,
            ],
            "diagnostics": [
                "attempt_count": descriptions.count,
                "initial_debug_description": initialDescription,
                "final_debug_description": finalDescription,
                "contains_element_subtree": finalDescription.contains("Element subtree:\n"),
                "contains_path_to_element": finalDescription.contains("\nPath to element:"),
            ],
            "elapsed_ms": (CFAbsoluteTimeGetCurrent() - start) * 1_000,
        ]
    }

    private func parseTree(_ description: String) -> SnapshotNode? {
        guard
            let subtreeStart = description.range(of: "Element subtree:\n")?.upperBound,
            let subtreeEnd = description.range(of: "\nPath to element:", range: subtreeStart..<description.endIndex)?.lowerBound
        else {
            return nil
        }

        var stack: [SnapshotNode] = []
        var root: SnapshotNode?
        for line in description[subtreeStart..<subtreeEnd].split(separator: "\n", omittingEmptySubsequences: true).map(String.init) {
            let leadingSpaces = line.prefix { $0 == " " }.count
            let depth = leadingSpaces <= 1 ? 0 : (leadingSpaces - 2) / 2
            let raw = line.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "→", with: "")
            let node = SnapshotNode(
                type: raw.split(separator: ",", maxSplits: 1).first.map(String.init) ?? raw,
                rawDescription: raw,
                identifier: firstCapture(in: raw, pattern: #"identifier: '([^']*)'"#),
                label: firstCapture(in: raw, pattern: #"label: '([^']*)'"#),
                frame: parseFrame(raw)
            )

            if depth == 0 {
                root = node
                stack = [node]
            } else if depth <= stack.count {
                stack = Array(stack.prefix(depth))
                stack.last?.children.append(node)
                stack.append(node)
            }
        }
        return root
    }

    private func parseFrame(_ value: String) -> [String: Double]? {
        let pattern = #"\{\{(-?[0-9.]+), (-?[0-9.]+)\}, \{(-?[0-9.]+), (-?[0-9.]+)\}\}"#
        guard let captures = captures(in: value, pattern: pattern), captures.count == 4 else {
            return nil
        }
        let numbers = captures.compactMap(Double.init)
        guard numbers.count == 4 else { return nil }
        return ["x": numbers[0], "y": numbers[1], "width": numbers[2], "height": numbers[3]]
    }

    private func firstCapture(in value: String, pattern: String) -> String? {
        captures(in: value, pattern: pattern)?.first
    }

    private func captures(in value: String, pattern: String) -> [String]? {
        guard
            let expression = try? NSRegularExpression(pattern: pattern),
            let match = expression.firstMatch(in: value, range: NSRange(value.startIndex..., in: value))
        else {
            return nil
        }
        return (1..<match.numberOfRanges).compactMap { index in
            Range(match.range(at: index), in: value).map { String(value[$0]) }
        }
    }
}

private enum SnapshotError: LocalizedError {
    case extensionBundleIDMissing
    case extensionNotActive

    var code: String {
        switch self {
        case .extensionBundleIDMissing:
            return "extension_bundle_id_missing"
        case .extensionNotActive:
            return "extension_not_active"
        }
    }

    var errorDescription: String? {
        switch self {
        case .extensionBundleIDMissing:
            return "extension_bundle_id is required"
        case .extensionNotActive:
            return "keyboard extension is not active; focus a text field that presents it and retry"
        }
    }
}
