import unittest

try:
    from mcp import Client
except ImportError:
    Client = None

from keyboard_ext_ax.mcp_server import create_server


class FakeController:
    def snapshot(self, simulator_id, extension_bundle_id, raw=False):
        return {
            "ok": True,
            "simulator_udid": simulator_id,
            "extension_bundle_id": extension_bundle_id,
            "raw": raw,
            "elements": [],
        }


@unittest.skipUnless(Client, "MCP optional dependency is not installed")
class MCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_exposes_one_structured_snapshot_tool(self):
        async with Client(create_server(FakeController())) as client:
            tools = await client.list_tools()
            result = await client.call_tool(
                "keyboard_snapshot",
                {
                    "simulator_id": "SIMULATOR",
                    "extension_bundle_id": "example.keyboard",
                },
            )

        self.assertEqual([tool.name for tool in tools.tools], ["keyboard_snapshot"])
        self.assertEqual(result.meta["io.modelcontextprotocol/serverInfo"]["version"], "0.1.0")
        self.assertEqual(
            result.structured_content,
            {
                "ok": True,
                "simulator_udid": "SIMULATOR",
                "extension_bundle_id": "example.keyboard",
                "raw": False,
                "elements": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
