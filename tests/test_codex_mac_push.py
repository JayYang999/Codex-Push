import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "codex_mac_push.py"


def load_module():
    spec = importlib.util.spec_from_file_location("codex_mac_push", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["codex_mac_push"] = module
    spec.loader.exec_module(module)
    return module


class CodexMacPushTest(unittest.TestCase):
    def test_resolves_agent_turn_complete_notification(self):
        module = load_module()

        notification = module.resolve_notification("agent-turn-complete", Path("/tmp/example-project"))

        self.assertEqual(notification.title, "Codex task complete")
        self.assertEqual(notification.body, "Project: example-project")

    def test_resolves_approval_requested_notification(self):
        module = load_module()

        notification = module.resolve_notification("approval-requested", Path("/tmp/example-project"))

        self.assertEqual(notification.title, "Codex needs approval")
        self.assertEqual(notification.body, "Project: example-project")

    def test_root_directory_uses_codex_project_label(self):
        module = load_module()

        notification = module.resolve_notification("agent-turn-complete", Path("/"))

        self.assertEqual(notification.body, "Project: Codex")

    def test_events_have_different_sound_files(self):
        module = load_module()

        complete_sound = module.sound_path_for_event("agent-turn-complete")
        approval_sound = module.sound_path_for_event("approval-requested")

        self.assertEqual(complete_sound.name, "codex_task_complete.mp3")
        self.assertEqual(approval_sound.name, "codex_needs_approval.mp3")
        self.assertNotEqual(complete_sound, approval_sound)

    def test_approval_notification_is_suppressed_when_human_approval_is_not_confirmed(self):
        module = load_module()

        stdout = io.StringIO()
        with (
            redirect_stdout(stdout),
            mock.patch.object(module, "send_macos_notification") as send,
            mock.patch.object(module, "play_event_sound") as play_sound,
        ):
            exit_code = module.main(["--event", "approval-requested", "--cwd", "/tmp/example-project"])

        self.assertEqual(exit_code, 0)
        send.assert_not_called()
        play_sound.assert_not_called()

    def test_approval_notification_can_be_sent_when_hook_confirms_human_review(self):
        module = load_module()

        with (
            mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
            mock.patch.object(module, "send_macos_notification") as send,
            mock.patch.object(module, "play_event_sound") as play_sound,
        ):
            exit_code = module.main([
                "--event",
                "approval-requested",
                "--human-approval-confirmed",
                "--cwd",
                "/tmp/example-project",
            ])

        self.assertEqual(exit_code, 0)
        send.assert_called_once()
        play_sound.assert_called_once_with("approval-requested")

    def test_suppresses_when_codex_or_terminal_is_frontmost(self):
        module = load_module()

        for app_name in ("Codex", "Terminal", "iTerm2", "Warp"):
            with self.subTest(app_name=app_name):
                self.assertFalse(module.should_send_notification(app_name))

    def test_notifies_when_frontmost_app_cannot_be_detected(self):
        module = load_module()

        self.assertTrue(module.should_send_notification(None))

    def test_chain_existing_notify_is_best_effort(self):
        module = load_module()

        with mock.patch.object(module.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["old"])):
            module.chain_existing_notify(["old", "notify"])

    def test_chain_existing_notify_suppresses_old_notifier_output(self):
        module = load_module()

        with mock.patch.object(module.subprocess, "run") as run:
            module.chain_existing_notify(["old", "notify"])

        run.assert_called_once_with(
            ["old", "notify"],
            check=True,
            timeout=10,
            stdout=module.subprocess.DEVNULL,
            stderr=module.subprocess.DEVNULL,
        )

    def test_dry_run_prints_notification_without_sending(self):
        module = load_module()

        stdout = io.StringIO()
        with (
            redirect_stdout(stdout),
            mock.patch.object(module, "send_macos_notification") as send,
            mock.patch.object(module, "play_event_sound") as play_sound,
        ):
            exit_code = module.main(["--event", "approval-requested", "--dry-run", "--cwd", "/tmp/example-project"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "Codex needs approval\nProject: example-project")
        send.assert_not_called()
        play_sound.assert_not_called()

    def test_sends_notification_and_plays_matching_sound(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                module.main(["--event", "tool-used", "--cwd", "/tmp/example-project"])
                exit_code = module.main(["--event", "agent-turn-complete", "--cwd", "/tmp/example-project"])

        self.assertEqual(exit_code, 0)
        send.assert_called_once()
        play_sound.assert_called_once_with("agent-turn-complete")

    def test_turn_complete_is_suppressed_when_no_tool_was_used(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                exit_code = module.main(["--event", "agent-turn-complete", "--cwd", "/tmp/example-project"])

        self.assertEqual(exit_code, 0)
        send.assert_not_called()
        play_sound.assert_not_called()

    def test_tool_used_event_only_marks_state(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                exit_code = module.main(["--event", "tool-used", "--cwd", "/tmp/example-project"])

        self.assertEqual(exit_code, 0)
        send.assert_not_called()
        play_sound.assert_not_called()

    def test_turn_complete_consumes_tool_used_marker(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                module.main(["--event", "tool-used", "--cwd", "/tmp/example-project"])
                module.main(["--event", "agent-turn-complete", "--cwd", "/tmp/example-project"])
                module.main(["--event", "agent-turn-complete", "--cwd", "/tmp/example-project"])

        self.assertEqual(send.call_count, 1)
        self.assertEqual(play_sound.call_count, 1)

    def test_turn_complete_consumes_recent_marker_when_notify_cwd_differs(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                module.main(["--event", "tool-used", "--cwd", "/tmp/example-project"])
                exit_code = module.main(["--event", "agent-turn-complete", "--cwd", "/"])

        self.assertEqual(exit_code, 0)
        send.assert_called_once()
        notification = send.call_args.args[0]
        self.assertEqual(notification.title, "Codex task complete")
        self.assertEqual(notification.body, "Project: example-project")
        play_sound.assert_called_once_with("agent-turn-complete")

    def test_turn_complete_ignores_stale_fallback_markers(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            marker = Path(tmpdir) / "tool-used-old.marker"
            marker.write_text("/tmp/example-project\n")
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "marker_age_seconds", return_value=module.TOOL_USED_MARKER_MAX_AGE_SECONDS + 1),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                exit_code = module.main(["--event", "agent-turn-complete", "--cwd", "/"])

        self.assertEqual(exit_code, 0)
        send.assert_not_called()
        play_sound.assert_not_called()

    def test_turn_complete_ignores_legacy_fallback_markers_without_cwd(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            marker = Path(tmpdir) / "tool-used-legacy.marker"
            marker.write_text("1\n")
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                exit_code = module.main(["--event", "agent-turn-complete", "--cwd", "/"])

        self.assertEqual(exit_code, 0)
        self.assertFalse(marker.exists())
        send.assert_not_called()
        play_sound.assert_not_called()

    def test_turn_complete_ignores_legacy_exact_marker_without_cwd(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(module, "STATE_DIR", Path(tmpdir)):
                marker = module.tool_used_marker_path(Path("/tmp/example-project"))
            marker.write_text("1\n")
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                exit_code = module.main(["--event", "agent-turn-complete", "--cwd", "/tmp/example-project"])

        self.assertEqual(exit_code, 0)
        self.assertFalse(marker.exists())
        send.assert_not_called()
        play_sound.assert_not_called()

    def test_turn_complete_skips_legacy_fallback_marker_and_consumes_valid_marker(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_marker = Path(tmpdir) / "tool-used-legacy.marker"
            valid_marker = Path(tmpdir) / "tool-used-valid.marker"
            legacy_marker.write_text("1\n")
            valid_marker.write_text("/tmp/example-project\n")
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound"),
            ):
                exit_code = module.main(["--event", "agent-turn-complete", "--cwd", "/"])

        self.assertEqual(exit_code, 0)
        self.assertFalse(legacy_marker.exists())
        self.assertFalse(valid_marker.exists())
        notification = send.call_args.args[0]
        self.assertEqual(notification.body, "Project: example-project")

    def test_play_event_sound_uses_afplay_when_file_exists(self):
        module = load_module()
        fake_sound = Path("/tmp/codex_needs_approval.wav")

        with (
            mock.patch.object(module, "sound_path_for_event", return_value=fake_sound),
            mock.patch.object(module.Path, "exists", return_value=True),
            mock.patch.object(module.subprocess, "run") as run,
        ):
            module.play_event_sound("approval-requested")

        run.assert_called_once_with(
            ["/usr/bin/afplay", str(fake_sound)],
            check=False,
            timeout=5,
            stdout=module.subprocess.DEVNULL,
            stderr=module.subprocess.DEVNULL,
        )

    def test_play_event_sound_skips_missing_file(self):
        module = load_module()
        fake_sound = Path("/tmp/missing.wav")

        with (
            mock.patch.object(module, "sound_path_for_event", return_value=fake_sound),
            mock.patch.object(module.Path, "exists", return_value=False),
            mock.patch.object(module.subprocess, "run") as run,
        ):
            module.play_event_sound("agent-turn-complete")

        run.assert_not_called()

    def test_ignores_extra_codex_notify_arguments(self):
        module = load_module()

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = module.main([
                "--event",
                "agent-turn-complete",
                "--dry-run",
                "--cwd",
                "/tmp/example-project",
                '{"extra":"from-codex"}',
            ])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "Codex task complete\nProject: example-project")

    def test_passes_extra_codex_notify_arguments_to_existing_notifier(self):
        module = load_module()

        stdout = io.StringIO()
        with redirect_stdout(stdout), mock.patch.object(module, "chain_existing_notify") as chain:
            exit_code = module.main([
                "--event",
                "agent-turn-complete",
                "--dry-run",
                "--chain-existing-notify",
                "codex-payload",
            ])

        self.assertEqual(exit_code, 0)
        chain.assert_called_once_with(module.EXISTING_NOTIFY + ["codex-payload"])

    def test_skips_existing_notifier_when_no_codex_payload_is_available(self):
        module = load_module()

        stdout = io.StringIO()
        with redirect_stdout(stdout), mock.patch.object(module, "chain_existing_notify") as chain:
            exit_code = module.main([
                "--event",
                "agent-turn-complete",
                "--dry-run",
                "--chain-existing-notify",
            ])

        self.assertEqual(exit_code, 0)
        chain.assert_not_called()


if __name__ == "__main__":
    unittest.main()
