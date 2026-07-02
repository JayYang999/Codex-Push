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
    def test_agent_turn_complete_generates_eddy_task_complete_sound(self):
        module = load_module()

        sound = module.SOUNDS["agent-turn-complete"]

        self.assertEqual(sound["voice"], "Eddy")
        self.assertEqual(sound["text"], "Codex task complete")
        self.assertEqual(sound["filename"], "codex_task_complete.wav")

    def test_approval_requested_generates_rocko_needs_approval_sound(self):
        module = load_module()

        sound = module.SOUNDS["approval-requested"]

        self.assertEqual(sound["voice"], "Rocko")
        self.assertEqual(sound["text"], "Codex needs approval")
        self.assertEqual(sound["filename"], "codex_needs_approval.wav")


if __name__ == "__main__":
    unittest.main()
