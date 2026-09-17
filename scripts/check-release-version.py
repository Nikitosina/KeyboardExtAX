#!/usr/bin/env python3
import json
import re
import sys
import tomllib
from pathlib import Path


root = Path(__file__).resolve().parent.parent
expected = sys.argv[1] if len(sys.argv) > 1 else None
with (root / "pyproject.toml").open("rb") as file:
    package_version = tomllib.load(file)["project"]["version"]
with (root / "server.json").open() as file:
    server = json.load(file)
server_version = server["version"]
package_versions = {package["version"] for package in server["packages"]}
init_source = (root / "keyboard_ext_ax" / "__init__.py").read_text()
module_version = re.search(r'^__version__ = "([^"]+)"$', init_source, re.MULTILINE).group(1)

versions = {package_version, server_version, module_version, *package_versions}
if len(versions) != 1:
    raise SystemExit(f"version mismatch: {sorted(versions)}")
if expected and package_version != expected:
    raise SystemExit(f"tag version {expected} does not match package version {package_version}")
print(package_version)
