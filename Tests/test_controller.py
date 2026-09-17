import tempfile
import unittest

from keyboard_ext_ax import KeyboardExtAXError
from keyboard_ext_ax.controller import KeyboardExtAXController


class ControllerTests(unittest.TestCase):
    def test_default_project_root_contains_bundled_harness(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            controller = KeyboardExtAXController(cache_dir=cache_dir)

        self.assertEqual(controller.project_root.name, "harness")
        self.assertTrue((controller.project_root / "KeyboardExtAX.xcodeproj").is_dir())
        self.assertTrue((controller.project_root / "UITests" / "PersistentKeyboardExtAXTests.swift").is_file())

    def test_compact_flattens_tree_and_rounds_tap_coordinates(self):
        response = {
            "ok": True,
            "snapshot_id": "snapshot",
            "simulator_udid": "simulator",
            "extension_bundle_id": "example.keyboard",
            "pid": 42,
            "tree": {
                "type": "Application",
                "identifier": None,
                "label": "Keyboard",
                "frame": None,
                "center": None,
                "children": [
                    {
                        "type": "Key",
                        "identifier": "space",
                        "label": "Space",
                        "frame": {"x": 10, "y": 20, "width": 31, "height": 41},
                        "center": {"x": 25.5, "y": 40.5},
                        "children": [],
                    }
                ],
            },
        }

        compact = KeyboardExtAXController._compact(response)

        self.assertEqual([element["ref"] for element in compact["elements"]], ["0", "0.0"])
        self.assertEqual(compact["elements"][1]["tap_x"], 26)
        self.assertEqual(compact["elements"][1]["tap_y"], 41)

    def test_new_session_requests_client_refocus(self):
        controller = KeyboardExtAXController.__new__(KeyboardExtAXController)
        controller._ensure_session = lambda simulator: ({"port": 1234}, False)

        result = controller.snapshot("SIMULATOR", "example.keyboard")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "client_refocus_required")
        self.assertEqual(result["simulator_udid"], "SIMULATOR")

    def test_raw_flag_is_forwarded_to_runner(self):
        controller = KeyboardExtAXController.__new__(KeyboardExtAXController)
        controller._ensure_session = lambda simulator: ({"port": 1234}, True)
        captured = {}

        def send(port, request, timeout):
            captured.update(request)
            return {"ok": False, "error": {"code": "extension_not_active"}}

        controller._send = send
        controller.snapshot("SIMULATOR", "example.keyboard", raw=True)

        self.assertTrue(captured["raw"])

    def test_error_dictionary_is_machine_readable(self):
        error = KeyboardExtAXError("build_failed", "Build failed", {"log": "/tmp/build.log"})

        self.assertEqual(
            error.dictionary(),
            {
                "ok": False,
                "error": {
                    "code": "build_failed",
                    "message": "Build failed",
                    "log": "/tmp/build.log",
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
