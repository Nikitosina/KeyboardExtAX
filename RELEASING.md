# Releasing KeyboardExtAX

## One-time setup

### GitHub

Create the public repository `Nikitosina/KeyboardExtAX`, push the `main` branch, and enable the `pypi` deployment environment under **Settings → Environments**.

### PyPI Trusted Publishing

Create a pending trusted publisher at <https://pypi.org/manage/account/publishing/> with:

| Field | Value |
|---|---|
| PyPI project name | `keyboard-ext-ax` |
| GitHub owner | `Nikitosina` |
| Repository | `KeyboardExtAX` |
| Workflow | `release.yml` |
| Environment | `pypi` |

No PyPI API token is required. The release workflow uses GitHub OIDC.

### Homebrew tap

Create the public repository `Nikitosina/homebrew-tap`. The first formula is added after the PyPI release because it needs the final source archive URL, checksum, and published dependency graph.

## Release checklist

1. Update the version in `pyproject.toml`.
2. Update the top-level and package versions in `server.json`.
3. Update release notes and compatibility claims.
4. Run:

   ```sh
   python3 scripts/check-release-version.py 0.1.0
   python3 -m unittest discover -s Tests -v
   python3 -m build
   python3 -m twine check dist/*
   ```

5. Install the wheel in a clean virtual environment and verify that `keyboard_ext_ax/harness` is present.
6. Commit the release.
7. Create and push the tag:

   ```sh
   git tag v0.1.0
   git push origin main v0.1.0
   ```

The `Release` workflow then:

1. verifies tag, PyPI, and MCP metadata versions;
2. builds and validates wheel and source distribution;
3. publishes to PyPI through Trusted Publishing;
4. publishes `server.json` to the MCP Registry through GitHub OIDC;
5. creates a GitHub release containing the Python distributions.

PyPI and MCP Registry versions are immutable. Never reuse a published version.

## Homebrew source formula

After PyPI publication:

1. Create a formula from the PyPI source distribution in `Nikitosina/homebrew-tap`.
2. Declare the current Homebrew Python as an unconditional dependency.
3. Use `Language::Python::Virtualenv` and `virtualenv_install_with_resources`.
4. Generate recursive Python resources with `brew update-python-resources`.
5. Ensure both `keyboard-ext-ax` and `keyboard-ext-ax-mcp` are linked into `bin`.
6. Test:

   ```sh
   brew install --build-from-source Nikitosina/tap/keyboard-ext-ax
   brew test Nikitosina/tap/keyboard-ext-ax
   keyboard-ext-ax --help
   ```

7. Commit and push the formula.

The initial Homebrew release is source-only. Add bottles only after the formula has been validated on supported macOS architectures.
