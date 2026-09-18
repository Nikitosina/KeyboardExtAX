<!-- mcp-name: io.github.Nikitosina/keyboard-ext-ax -->

# KeyboardExtAX

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

## What it provides

- One MCP tool: `keyboard_snapshot`
- A matching command-line interface: `keyboard-ext-ax`
- Flat, compact accessibility elements for agent use
- Integer `tap_x` and `tap_y` in Simulator logical coordinates
- One persistent XCTest runner per simulator
- Shared build cache across simulators
- Automatic port selection, test-plan configuration, logs, and result bundles
- Structured, machine-readable errors
- Optional raw XCTest output for diagnostics
- No dependency on any particular keyboard implementation

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

## Installation from source

Clone the repository:

```sh
git clone https://github.com/Nikitosina/KeyboardExtAX.git
cd KeyboardExtAX
```

Create an isolated environment and install the CLI plus MCP support:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

This provides two executables:

```text
.venv/bin/keyboard-ext-ax
.venv/bin/keyboard-ext-ax-mcp
```

The MCP server can be started with either `keyboard-ext-ax-mcp` or `keyboard-ext-ax mcp`.

The bundled Xcode project is ready to use. XcodeGen is needed only when modifying `keyboard_ext_ax/harness/project.yml`.

## Quick start: MCP

Configure `keyboard-ext-ax-mcp` as a stdio MCP server. Most MCP clients use a configuration shaped like this:

```json
{
  "mcpServers": {
    "KeyboardExtAX": {
      "command": "/absolute/path/to/KeyboardExtAX/.venv/bin/keyboard-ext-ax-mcp",
      "env": {
        "DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"
      }
    }
  }
}
```

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
.venv/bin/keyboard-ext-ax snapshot \
  --simulator <SIMULATOR_UDID> \
  --extension com.example.keyboard.extension
```

Write the result to a file:

```sh
.venv/bin/keyboard-ext-ax snapshot \
  --simulator <SIMULATOR_UDID> \
  --extension com.example.keyboard.extension \
  --output /tmp/keyboard.json
```

Use `--raw` to retain the nested tree and original XCTest descriptions:

```sh
.venv/bin/keyboard-ext-ax snapshot \
  --simulator <SIMULATOR_UDID> \
  --extension com.example.keyboard.extension \
  --raw
```

On attachment failures, raw mode also includes the initial and final XCTest query descriptions and the number of attempts.

## First-call lifecycle

The first snapshot for a simulator performs setup automatically:

1. Hash the KeyboardExtAX sources, Xcode version, and host architecture.
2. Build the XCTest harness if that build is not already cached.
3. Allocate a free loopback port.
4. Generate a simulator-specific `.xctestrun` configuration.
5. Start a persistent XCTest runner.
6. Cache the runner state for later calls.

Starting XCTest can disturb the client application's keyboard focus. KeyboardExtAX therefore returns this explicit result after creating a runner:

```json
{
  "ok": false,
  "error": {
    "code": "client_refocus_required",
    "message": "XCTest runner started; refocus the client text field and retry"
  },
  "simulator_udid": "…",
  "session_reused": false
}
```

Refocus the client text field and repeat the same MCP or CLI request. Warm calls reuse the runner directly.

KeyboardExtAX also retries extension attachment three times over one second before reporting `extension_not_active`. Successful first attempts do not pay this delay.

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

## Using coordinates with XcodeBuildMCP

A typical automation loop is:

1. Use XcodeBuildMCP to build, install, and launch the keyboard's containing app.
2. Open a client screen with a text field.
3. Focus the field and ensure the intended keyboard is visible.
4. Call `keyboard_snapshot`.
5. Find an element by `identifier` or `label`.
6. Pass its `tap_x` and `tap_y` to XcodeBuildMCP `tap`.
7. Request a fresh keyboard snapshot after any layout-changing action.
8. Verify resulting text through the client application's accessibility tree.

Example pseudocode:

```text
snapshot = keyboard_snapshot(simulator_id, extension_bundle_id)
space = snapshot.elements.first(where: identifier == "space")
XcodeBuildMCP.tap(x: space.tap_x, y: space.tap_y)
```

Always refresh after Shift, globe, numbers/symbols, Return, vertical navigation, overlays, or any action that can replace keys. KeyboardExtAX intentionally returns coordinates rather than retaining XCTest element handles.

## Session management

Inspect all cached simulator sessions:

```sh
.venv/bin/keyboard-ext-ax status
```

Inspect one simulator:

```sh
.venv/bin/keyboard-ext-ax status --simulator <SIMULATOR_UDID>
```

Stop one runner:

```sh
.venv/bin/keyboard-ext-ax stop --simulator <SIMULATOR_UDID>
```

Stop every runner:

```sh
.venv/bin/keyboard-ext-ax stop --all
```

One runner is maintained per simulator. Multiple simulators can be queried concurrently; each receives an independent port, state file, log, and result bundle.

## Cache layout

The default cache root is:

```text
~/Library/Caches/KeyboardExtAX
```

It contains:

```text
builds/<build-key>/          Shared XCTest build products
sessions/<simulator-udid>/   Runner state, log, lock, and result bundle
```

Override the location with either:

```sh
keyboard-ext-ax --cache-dir /custom/cache snapshot …
```

or:

```sh
export KEYBOARD_EXT_AX_CACHE_DIR=/custom/cache
```

Build products are invalidated when the harness source, checked-in Xcode project, Xcode version, or host architecture changes.

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

## Troubleshooting

### The keyboard is visible, but `extension_not_active` is returned

Confirm that the visible keyboard belongs to the requested extension. iOS can silently return to the system keyboard when focus changes. Wait for the keyboard transition to finish, then repeat the request without changing the UI again. Use `raw: true` if the failure persists.

### The software keyboard does not appear

Disable **Simulator → I/O → Keyboard → Connect Hardware Keyboard**.

### Coordinates look offset

Use the coordinates directly with the same simulator. Screenshot files may be scaled and are not the coordinate space used by XCTest.

### A previously found key no longer works

Take a fresh snapshot. Keyboard layouts and references can change after Shift, locale switches, symbols, suggestions, overlays, and vertical transitions.

### The wrong Xcode is used

Set the desired developer directory:

```sh
export DEVELOPER_DIR=/Applications/Xcode-26.5.0.app/Contents/Developer
```

For a one-off CLI call:

```sh
keyboard-ext-ax \
  --developer-dir /Applications/Xcode-26.5.0.app/Contents/Developer \
  snapshot \
  --simulator <SIMULATOR_UDID> \
  --extension com.example.keyboard.extension
```

### A build or runner fails

KeyboardExtAX includes absolute log paths in `build_failed` and `runner_start_failed` responses. Start with the returned log rather than manually editing `.xctestrun` files or selecting ports.

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

## Privacy and security

- The MCP server and XCTest runner communicate locally over a dynamically selected loopback port.
- KeyboardExtAX does not send data to a remote service.
- KeyboardExtAX does not perform gestures or modify text.
- Snapshot output can contain visible key labels, suggestions, and other accessibility text. Treat captured output as potentially sensitive.
- Build products, logs, state, and result bundles remain under the local cache directory.

## Distribution

Source installation is currently the supported path. The wheel and source distribution bundle the Xcode project, host source, and UI-test source under `keyboard_ext_ax/harness`, so installed packages do not depend on a repository checkout.

The planned public distribution has two layers:

1. **PyPI** as the canonical Python package and MCP Registry package.
2. **Homebrew** as the recommended macOS installation experience.

Planned consumer commands are:

```sh
# Run the MCP server without a persistent installation
uvx keyboard-ext-ax mcp

# Or install both executables permanently
uv tool install keyboard-ext-ax
```

and:

```sh
brew install nikitosina/tap/keyboard-ext-ax
```

These commands will be enabled after the first packages are published.

The Homebrew formula should install the application into an isolated Python virtual environment with all dependencies declared as formula resources. A custom [`Nikitosina/homebrew-tap`](https://github.com/Nikitosina/homebrew-tap) can provide the formula immediately; bottles can later make installation fully prebuilt for supported macOS architectures.

The XCTest harness should still be built once on the consumer's machine and cached. Distributing precompiled `.xctestrun` products is intentionally avoided because they are coupled to Xcode versions, architectures, SDKs, and build paths.

After the PyPI release, the MCP server can be listed in the official MCP Registry under:

```text
io.github.Nikitosina/keyboard-ext-ax
```

The registry provides discovery metadata; PyPI and Homebrew remain responsible for delivering the software.

## Development

Regenerate the checked-in Xcode project after changing the bundled harness specification:

```sh
cd keyboard_ext_ax/harness
xcodegen generate
```

Run Python tests without MCP support:

```sh
python3 -m unittest discover -s Tests -v
```

Run the complete test suite from the development environment:

```sh
.venv/bin/python -m unittest discover -s Tests -v
```

Build the Xcode project with the `KeyboardExtAX` scheme in `keyboard_ext_ax/harness/KeyboardExtAX.xcodeproj`.

When changing the parser, validate against every claimed Xcode version and preserve raw XCTest descriptions as fixtures where possible.

## Contributing

Issues and focused pull requests are welcome. Please include:

- macOS and Xcode versions;
- Simulator runtime and device type;
- keyboard extension bundle identifier, when it can be shared;
- the machine-readable error response;
- raw diagnostics with sensitive text removed.

## License

KeyboardExtAX is available under the [MIT License](LICENSE).
