import argparse
import json
import sys

from . import __version__
from .controller import KeyboardExtAXController, KeyboardExtAXError


def write_json(value, output=None):
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if output:
        with open(output, "w") as file:
            file.write(text)
    else:
        sys.stdout.write(text)


def make_parser():
    parser = argparse.ArgumentParser(prog="keyboard-ext-ax")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--cache-dir")
    parser.add_argument("--developer-dir")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("mcp", help="Run the stdio MCP server")

    snapshot = commands.add_parser("snapshot", help="Snapshot an active keyboard extension")
    snapshot.add_argument("--simulator", required=True, metavar="UDID")
    snapshot.add_argument(
        "--extension",
        "--extension-bundle-id",
        dest="extension_bundle_id",
        required=True,
        metavar="BUNDLE_ID",
    )
    snapshot.add_argument("--raw", action="store_true", help="Keep the nested tree and XCTest descriptions")
    snapshot.add_argument("--output")

    status = commands.add_parser("status", help="List cached simulator sessions")
    status.add_argument("--simulator", metavar="UDID")

    stop = commands.add_parser("stop", help="Stop cached simulator sessions")
    selection = stop.add_mutually_exclusive_group(required=True)
    selection.add_argument("--simulator", metavar="UDID")
    selection.add_argument("--all", action="store_true")
    return parser


def main():
    args = make_parser().parse_args()
    controller = KeyboardExtAXController(
        cache_dir=args.cache_dir,
        developer_dir=args.developer_dir,
    )
    try:
        if args.command == "mcp":
            from .mcp_server import main as run_mcp_server

            return run_mcp_server()
        if args.command == "snapshot":
            result = controller.snapshot(
                args.simulator,
                args.extension_bundle_id,
                raw=args.raw,
            )
            write_json(result, args.output)
            return 0 if result.get("ok") else 2
        if args.command == "status":
            write_json(controller.status(args.simulator))
            return 0
        if args.command == "stop":
            write_json(controller.stop_all() if args.all else controller.stop(args.simulator))
            return 0
    except KeyboardExtAXError as error:
        write_json(error.dictionary(), getattr(args, "output", None))
        return 1
    return 1
