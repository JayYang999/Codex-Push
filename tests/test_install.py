import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "install.py"


def load_module():
    spec = importlib.util.spec_from_file_location("install", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["install"] = module
    spec.loader.exec_module(module)
    return module


class InstallSoundMappingTest(unittest.TestCase):
    def test_agent_turn_complete_generates_guy_task_complete_sound(self):
        module = load_module()

        sound = module.SOUNDS["agent-turn-complete"]

        self.assertEqual(sound["engine"], "edge-tts")
        self.assertEqual(sound["voice"], "en-US-GuyNeural")
        self.assertEqual(sound["text"], "Codex task complete.")
        self.assertEqual(sound["filename"], "codex_task_complete.mp3")

    def test_approval_requested_generates_guy_needs_approval_sound(self):
        module = load_module()

        sound = module.SOUNDS["approval-requested"]

        self.assertEqual(sound["engine"], "edge-tts")
        self.assertEqual(sound["voice"], "en-US-GuyNeural")
        self.assertEqual(sound["text"], "Codex needs your approval.")
        self.assertEqual(sound["rate"], "-5%")
        self.assertEqual(sound["pitch"], "+8Hz")
        self.assertEqual(sound["filename"], "codex_needs_approval.mp3")

    def test_edge_tts_command_prefers_env_override(self):
        module = load_module()

        with unittest.mock.patch.dict("os.environ", {"EDGE_TTS_BIN": "/tmp/edge-tts"}):
            self.assertEqual(module.edge_tts_command(), "/tmp/edge-tts")

    def test_edge_tts_args_use_equals_for_signed_rate_and_pitch(self):
        module = load_module()

        with unittest.mock.patch.dict("os.environ", {"EDGE_TTS_BIN": "/tmp/edge-tts"}):
            args = module.edge_tts_args(
                module.SOUNDS["approval-requested"],
                Path("/tmp/codex_needs_approval.mp3"),
            )

        self.assertIn("--rate=-5%", args)
        self.assertIn("--pitch=+8Hz", args)
        self.assertNotIn("--rate", args)
        self.assertNotIn("--pitch", args)

    def test_hooks_include_tool_used_marker_and_approval_notifier(self):
        module = load_module()

        merged = module.merge_hooks({"hooks": {}})

        post_tool_hook = merged["hooks"]["PostToolUse"][0]["hooks"][0]
        permission_hook = merged["hooks"]["PermissionRequest"][0]["hooks"][0]

        self.assertEqual(merged["hooks"]["PostToolUse"][0]["matcher"], "*")
        self.assertEqual(post_tool_hook["command"], "/usr/bin/python3 /Users/jys/.codex/mac-push/codex_mac_push.py --event tool-used")
        self.assertEqual(merged["hooks"]["PermissionRequest"][0]["matcher"], "*")
        self.assertEqual(permission_hook["command"], "/usr/bin/python3 /Users/jys/.codex/mac-push/codex_mac_push.py --event approval-requested")

    def test_hook_merge_is_idempotent(self):
        module = load_module()

        merged_once = module.merge_hooks({"hooks": {}})
        merged_twice = module.merge_hooks(merged_once)

        self.assertEqual(len(merged_twice["hooks"]["PostToolUse"]), 1)
        self.assertEqual(len(merged_twice["hooks"]["PermissionRequest"]), 1)


if __name__ == "__main__":
    unittest.main()
