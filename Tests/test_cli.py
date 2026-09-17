import io
import unittest
from contextlib import redirect_stdout

from keyboard_ext_ax.cli import make_parser


class CLITests(unittest.TestCase):
    def test_version_is_available(self):
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exit_context:
            make_parser().parse_args(["--version"])

        self.assertEqual(exit_context.exception.code, 0)

    def test_mcp_subcommand_is_available(self):
        arguments = make_parser().parse_args(["mcp"])

        self.assertEqual(arguments.command, "mcp")


if __name__ == "__main__":
    unittest.main()
