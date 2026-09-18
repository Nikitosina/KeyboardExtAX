<!-- mcp-name: io.github.Nikitosina/keyboard-ext-ax -->

# KeyboardExtAX

![KeyboardExtAX accessibility snapshot illustration](.github/assets/keyboard-ext-ax-header.png)

Fast, read-only accessibility snapshots of active third-party iOS keyboard extensions in Simulator.

## Why this project exists

A custom iOS keyboard runs in a separate app-extension process. When a client app presents that keyboard, ordinary UI automation usually sees the client application's accessibility tree but not the keyboard's useful descendants. The entire keyboard may appear as one opaque element.

That creates a practical automation gap:

- screenshots can show the keyboard, but extracting reliable tap coordinates from pixels is slow and brittle;
- the client application's accessibility snapshot does not necessarily expose the extension's keys and controls;
- starting a new XCTest session for every query is expensive and can disturb keyboard focus;
- XCTest element handles become stale whenever the keyboard changes layout;
- automation agents should not need to manage test plans, ports, build products, or runner processes.

KeyboardExtAX fills that gap. It attaches XCTest directly to the already-running keyboard extension by bundle identifier, parses its accessibility hierarchy, and returns plain JSON with absolute logical coordinates. A persistent runner keeps warm snapshots fast, while a small controller owns building, caching, ports, and per-simulator lifecycle.

KeyboardExtAX observes only. Use a separate automation tool, such as [XcodeBuildMCP](https://github.com/cameroncooke/XcodeBuildMCP), to launch apps, focus text fields, and perform gestures with the returned coordinates.

## Quick start: MCP

Configure `keyboard-ext-ax-mcp` as a stdio MCP server. Most MCP clients use a configuration shaped like this:

```json
{
  "mcpServers": {
    "KeyboardExtAX": {
      "command": "keyboard-ext-ax-mcp",
      "env": {
        "DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"
      }
    }
  }
}
```

If the MCP client does not inherit your shell `PATH`, replace the command with the absolute path printed by `command -v keyboard-ext-ax-mcp`.

The server exposes one tool:

```text
keyboard_snapshot(
  simulator_id: "<SIMULATOR_UDID>",
  extension_bundle_id: "com.example.keyboard.extension",
  raw: false
)
```

Example input:

```json
{
  "simulator_id": "2D78332B-A3C3-4CEE-962B-99EF531FD201",
  "extension_bundle_id": "com.example.keyboard.extension"
}
```

The result is returned as structured MCP content. The MCP layer delegates directly to the same controller used by the CLI, so build caching, sessions, errors, and output are identical.

## Quick start: CLI

With the client text field focused and the requested keyboard visible:

```sh
keyboard-ext-ax snapshot \
  --simulator <SIMULATOR_UDID> \
  --extension com.example.keyboard.extension
```

Add `--output /tmp/keyboard.json` to write the result to a file. Add `--raw` for the nested tree and XCTest diagnostics.

## Scope and limitations

KeyboardExtAX currently supports:

- macOS hosts;
- iOS Simulator;
- third-party keyboard extensions;
- Xcode 26.5;
- read-only accessibility snapshots.

It does **not**:

- tap, swipe, or type;
- launch or foreground the client app;
- select or enable a keyboard for the user;
- access physical iOS devices;
- guarantee compatibility with widgets, Live Activities, or other extension types;
- guarantee parser compatibility with untested Xcode versions.

The parser reads `XCUIApplication.debugDescription`. Its text format is not a documented compatibility contract, so each Xcode version must be validated before support is claimed.

## Requirements

- macOS
- Xcode 26.5 with the desired iOS Simulator runtime installed
- Python 3.10 or newer
- A keyboard app and extension already installed in the target simulator
- The keyboard enabled in **Settings → General → Keyboard → Keyboards**
- A foreground client app with a focused text field

If multiple Xcode installations are present, select one with `DEVELOPER_DIR` or `--developer-dir`:

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
```

## Installation

### Homebrew (recommended)

```sh
brew install nikitosina/tap/keyboard-ext-ax
```

### PyPI with uv

Install both executables permanently:

```sh
uv tool install keyboard-ext-ax
```

Or run the MCP server without a persistent installation:

```sh
uvx keyboard-ext-ax mcp
```

### From source

```sh
git clone https://github.com/Nikitosina/KeyboardExtAX.git
cd KeyboardExtAX
python3 -m venv .venv
.venv/bin/python -m pip install -e .
source .venv/bin/activate
```

Every installation provides `keyboard-ext-ax` and `keyboard-ext-ax-mcp`. The MCP server can be started with either `keyboard-ext-ax-mcp` or `keyboard-ext-ax mcp`.

The bundled Xcode project is ready to use. XcodeGen is needed only when modifying `keyboard_ext_ax/harness/project.yml`.

## Output

The default response is a compact, flat array:

```json
{
  "ok": true,
  "snapshot_id": "9543E2AA-C4D9-4281-9645-7792F7953FE3",
  "simulator_udid": "2D78332B-A3C3-4CEE-962B-99EF531FD201",
  "extension_bundle_id": "com.example.keyboard.extension",
  "pid": 12345,
  "elapsed_ms": 103.4,
  "round_trip_ms": 106.1,
  "session_reused": true,
  "total_ms": 171.8,
  "elements": [
    {
      "ref": "0.0.3",
      "type": "Key",
      "identifier": "space",
      "label": "Space",
      "frame": {
        "x": 112,
        "y": 746,
        "width": 178,
        "height": 44
      },
      "center": {
        "x": 201,
        "y": 768
      },
      "tap_x": 201,
      "tap_y": 768
    }
  ]
}
```

### Element fields

| Field | Meaning |
|---|---|
| `ref` | Stable path within this snapshot only. Refresh it after layout changes. |
| `type` | XCTest accessibility element type. |
| `identifier` | Accessibility identifier, when provided by the extension. |
| `label` | Accessibility label, when provided by the extension. |
| `frame` | Absolute logical frame in Simulator coordinates. |
| `center` | Exact floating-point frame center. |
| `tap_x`, `tap_y` | Rounded integer center, ready for a gesture tool. |

Coordinates are Simulator logical coordinates, not screenshot pixels. Do not rescale them before passing them to XcodeBuildMCP for the same simulator.

## Session management

```sh
keyboard-ext-ax status
keyboard-ext-ax status --simulator <SIMULATOR_UDID>
keyboard-ext-ax stop --simulator <SIMULATOR_UDID>
keyboard-ext-ax stop --all
```

One runner is maintained per simulator. Multiple simulators can be queried concurrently.

## Errors

Errors are JSON objects with stable codes.

| Code | Meaning | Recovery |
|---|---|---|
| `client_refocus_required` | A new or restarted runner is ready. | Refocus the client text field and repeat the request. |
| `extension_not_active` | XCTest could not attach after three attempts. | Confirm that the requested extension—not the system keyboard—is visible, then retry. |
| `runner_start_failed` | The persistent XCTest runner did not become ready. | Inspect the returned `log` and `log_tail`. |
| `build_failed` | The XCTest harness failed to build. | Inspect the returned build log and verify the selected Xcode. |
| `xcode_unavailable` | Xcode could not be located or queried. | Set `DEVELOPER_DIR` or pass `--developer-dir`. |
| `extension_bundle_id_missing` | The runner received no extension identifier. | Supply `extension_bundle_id`. |
| `snapshot_failed` | XCTest raised an unexpected snapshot error. | Retry with `raw: true` and inspect diagnostics. |

The CLI exits with:

- `0` for success;
- `2` for a normal snapshot-state error such as inactive extension;
- `1` for lifecycle, build, or controller failures.

## Architecture

```text
MCP client / CLI
        │
        ▼
KeyboardExtAXController
  ├─ build cache
  ├─ per-simulator lock and state
  ├─ free-port allocation
  └─ XCTest runner lifecycle
        │  JSON over loopback TCP
        ▼
PersistentKeyboardExtAXTests
        │  XCUIApplication(bundleIdentifier:)
        ▼
Active keyboard extension process
        │
        ▼
Parsed tree → compact elements → MCP/CLI JSON
```

The host app included in this repository is XCTest scaffolding. Snapshot mode does not launch it and does not replace the consumer's foreground client app.

## License

KeyboardExtAX is available under the [MIT License](LICENSE).
