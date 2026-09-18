# Contributing

Issues and focused pull requests are welcome. Please include:

- macOS and Xcode versions;
- Simulator runtime and device type;
- keyboard extension bundle identifier, when it can be shared;
- the machine-readable error response;
- raw diagnostics with sensitive text removed.

## Development

Install the project in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Run the test suite:

```sh
.venv/bin/python -m unittest discover -s Tests -v
```

After changing `keyboard_ext_ax/harness/project.yml`, regenerate the checked-in Xcode project:

```sh
cd keyboard_ext_ax/harness
xcodegen generate
```

Build the `KeyboardExtAX` scheme in `keyboard_ext_ax/harness/KeyboardExtAX.xcodeproj`. When changing the parser, validate against every claimed Xcode version and preserve raw XCTest descriptions as fixtures where possible.
