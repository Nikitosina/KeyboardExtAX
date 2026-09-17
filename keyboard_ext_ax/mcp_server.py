import sys

from . import __version__
from .controller import KeyboardExtAXController, KeyboardExtAXError


def create_server(controller=None):
    try:
        from mcp.server import MCPServer
    except ImportError as error:
        raise RuntimeError(
            "MCP support is not installed; run `python3 -m pip install keyboard-ext-ax`"
        ) from error

    controller = controller or KeyboardExtAXController()
    server = MCPServer(
        name="KeyboardExtAX",
        title="KeyboardExtAX",
        description="Accessibility snapshots of active iOS keyboard extensions in Simulator.",
        website_url="https://github.com/Nikitosina/KeyboardExtAX",
        version=__version__,
        instructions=(
            "Snapshot an iOS keyboard extension that is already visible in Simulator. "
            "Use the returned integer tap_x and tap_y with a gesture tool on the same simulator."
        ),
    )

    @server.tool()
    def keyboard_snapshot(
        simulator_id: str,
        extension_bundle_id: str,
        raw: bool = False,
    ) -> dict[str, object]:
        """Return the active keyboard extension accessibility tree and tap coordinates.

        The client app must already be foreground with a focused text field presenting
        the requested extension. The first call builds and starts cached XCTest support;
        later calls reuse the simulator session.
        """
        try:
            return controller.snapshot(
                simulator_id,
                extension_bundle_id,
                raw=raw,
            )
        except KeyboardExtAXError as error:
            return error.dictionary()

    return server


def main():
    try:
        create_server().run()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0
