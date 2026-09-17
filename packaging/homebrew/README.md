# Homebrew formula staging

`keyboard-ext-ax.rb.template` is the source formula staged for the first PyPI release.

After PyPI publishes `0.1.0`:

1. Copy the exact source-distribution URL from PyPI.
2. Compute its SHA-256 checksum.
3. Replace `@SOURCE_URL@` and `@SOURCE_SHA256@`.
4. Refresh Python resources against the released package:

   ```sh
   brew update-python-resources Nikitosina/tap/keyboard-ext-ax
   ```

5. Audit, install, and test the formula before pushing it to `Nikitosina/homebrew-tap`.

The generated resources are intentionally pinned. Refresh them for every release rather than resolving dependencies during installation.
