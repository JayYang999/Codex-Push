import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "codex_mac_push.py"


def notify_payload(
    message: str,
    thread_id: str = "thread-test",
    turn_id: str = "turn-test",
    cwd: str = "/tmp/example-project",
) -> str:
    return json.dumps(
        {
            "type": "agent-turn-complete",
            "thread-id": thread_id,
            "turn-id": turn_id,
            "cwd": cwd,
            "last-assistant-message": message,
        },
        ensure_ascii=False,
    )


def post_tool_hook_payload(
    session_id: str = "thread-test",
    turn_id: str = "turn-test",
    cwd: str = "/tmp/example-project",
) -> str:
    return json.dumps(
        {
            "session_id": session_id,
            "turn_id": turn_id,
            "cwd": cwd,
            "hook_event_name": "PostToolUse",
        }
    )


def mark_tool_used_for_turn(
    module,
    session_id: str = "thread-test",
    turn_id: str = "turn-test",
    cwd: str = "/tmp/example-project",
) -> int:
    with mock.patch("sys.stdin", io.StringIO(post_tool_hook_payload(session_id, turn_id, cwd))):
        return module.main(["--event", "tool-used", "--cwd", cwd])


def create_user_session(sessions_dir: Path, thread_id: str = "thread-test") -> Path:
    session_dir = sessions_dir / "2026" / "07" / "27"
    session_dir.mkdir(parents=True)
    session_file = session_dir / f"rollout-2026-07-27T10-00-00-{thread_id}.jsonl"
    session_file.write_text("{}\n")
    return session_file


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

        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as sessions_dir:
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "SESSIONS_DIR", Path(sessions_dir)),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                create_user_session(Path(sessions_dir))
                mark_tool_used_for_turn(module)
                exit_code = module.main([
                    "--event",
                    "agent-turn-complete",
                    "--cwd",
                    "/tmp/example-project",
                    notify_payload("Implemented the fix and all 34 tests pass."),
                ])

        self.assertEqual(exit_code, 0)
        send.assert_called_once()
        play_sound.assert_called_once_with("agent-turn-complete")

    def test_turn_complete_suppresses_real_clarification_messages(self):
        module = load_module()
        clarification_messages = (
            """先确认最关键的一点：这个“热门榜单”首要优化目标是什么？

A. 发现“正在爆”的内容
B. 找“综合消费最好”的内容
C. 两者兼顾

我倾向 C，但需要你确认，因为它会直接决定热度分权重和更新频率。""",
            """这张图说明需要为不同榜单设置不同目标和权重，而不是共用一个热度分。

下一个关键问题：榜单实际排序和展示的对象是什么？

A. 单条视频
B. 标签/话题
C. 两级榜单

我建议选 C。""",
        )

        for message in clarification_messages:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmpdir:
                with (
                    mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                    mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                    mock.patch.object(module, "send_macos_notification") as send,
                    mock.patch.object(module, "play_event_sound") as play_sound,
                ):
                    mark_tool_used_for_turn(module)
                    marker = module.turn_used_marker_path("thread-test", "turn-test")
                    exit_code = module.main([
                        "--event",
                        "agent-turn-complete",
                        "--cwd",
                        "/tmp/example-project",
                        notify_payload(message),
                    ])

                self.assertEqual(exit_code, 0)
                self.assertFalse(marker.exists())
                send.assert_not_called()
                play_sound.assert_not_called()

    def test_turn_complete_suppresses_missing_or_malformed_notify_payload(self):
        module = load_module()

        for extra_args in ([], ["not-json"]):
            with self.subTest(extra_args=extra_args), tempfile.TemporaryDirectory() as tmpdir:
                with (
                    mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                    mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                    mock.patch.object(module, "send_macos_notification") as send,
                    mock.patch.object(module, "play_event_sound") as play_sound,
                ):
                    module.main(["--event", "tool-used", "--cwd", "/tmp/example-project"])
                    marker = module.tool_used_marker_path(Path("/tmp/example-project"))
                    exit_code = module.main([
                        "--event",
                        "agent-turn-complete",
                        "--cwd",
                        "/tmp/example-project",
                        *extra_args,
                    ])

                self.assertEqual(exit_code, 0)
                self.assertFalse(marker.exists())
                send.assert_not_called()
                play_sound.assert_not_called()

    def test_user_input_classifier_handles_question_endings_and_explicit_requests(self):
        module = load_module()

        for message in (
            "Which option should I use?",
            "请提供目标目录。",
            "方案已经确认，你只需确认目标目录后我就开始修改。",
            "I need your input before I continue.",
        ):
            with self.subTest(message=message):
                self.assertTrue(module.message_requires_user_input(message))

        self.assertFalse(module.message_requires_user_input("Implemented the fix and all tests pass."))

    def test_turn_complete_suppresses_internal_thread_without_user_session(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as state_dir, tempfile.TemporaryDirectory() as sessions_dir:
            with (
                mock.patch.object(module, "STATE_DIR", Path(state_dir)),
                mock.patch.object(module, "SESSIONS_DIR", Path(sessions_dir), create=True),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                mark_tool_used_for_turn(module, "thread-background", "turn-background")
                marker = module.turn_used_marker_path("thread-background", "turn-background")
                exit_code = module.main([
                    "--event",
                    "agent-turn-complete",
                    "--cwd",
                    "/tmp/example-project",
                    notify_payload(
                        "Generated personalized suggestions.",
                        "thread-background",
                        "turn-background",
                    ),
                ])

            self.assertEqual(exit_code, 0)
            self.assertFalse(marker.exists())
            send.assert_not_called()
            play_sound.assert_not_called()

    def test_user_input_classifier_detects_question_before_recommendation(self):
        module = load_module()

        message = "你想用 A 还是 B？\n我建议 A。"

        self.assertTrue(module.message_requires_user_input(message))

    def test_user_input_classifier_allows_optional_follow_up_after_completion(self):
        module = load_module()

        message = "Implemented the fix and all tests pass. Let me know if you want a follow-up."

        self.assertFalse(module.message_requires_user_input(message))

    def test_turn_complete_only_consumes_marker_for_matching_turn(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as sessions_dir:
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "SESSIONS_DIR", Path(sessions_dir)),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                create_user_session(Path(sessions_dir), "thread-a")
                mark_tool_used_for_turn(module, "thread-a", "turn-a")

            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "SESSIONS_DIR", Path(sessions_dir)),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                module.main([
                    "--event",
                    "agent-turn-complete",
                    "--cwd",
                    "/tmp/example-project",
                    notify_payload("Other turn completed.", "thread-b", "turn-b"),
                ])
                send.assert_not_called()
                play_sound.assert_not_called()
                module.main([
                    "--event",
                    "agent-turn-complete",
                    "--cwd",
                    "/tmp/example-project",
                    notify_payload("Matching turn completed.", "thread-a", "turn-a"),
                ])

        send.assert_called_once()
        play_sound.assert_called_once_with("agent-turn-complete")

    def test_turn_complete_is_suppressed_when_no_tool_was_used(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as sessions_dir:
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "SESSIONS_DIR", Path(sessions_dir)),
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

        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as sessions_dir:
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "SESSIONS_DIR", Path(sessions_dir)),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                create_user_session(Path(sessions_dir))
                mark_tool_used_for_turn(module)
                module.main([
                    "--event",
                    "agent-turn-complete",
                    "--cwd",
                    "/tmp/example-project",
                    notify_payload("Implemented the fix and all tests pass."),
                ])
                module.main(["--event", "agent-turn-complete", "--cwd", "/tmp/example-project"])

        self.assertEqual(send.call_count, 1)
        self.assertEqual(play_sound.call_count, 1)

    def test_turn_complete_uses_matching_turn_marker_when_notify_cwd_differs(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as sessions_dir:
            with (
                mock.patch.object(module, "STATE_DIR", Path(tmpdir)),
                mock.patch.object(module, "SESSIONS_DIR", Path(sessions_dir)),
                mock.patch.object(module, "frontmost_app_name", return_value="Finder"),
                mock.patch.object(module, "send_macos_notification") as send,
                mock.patch.object(module, "play_event_sound") as play_sound,
            ):
                create_user_session(Path(sessions_dir))
                mark_tool_used_for_turn(module)
                exit_code = module.main([
                    "--event",
                    "agent-turn-complete",
                    "--cwd",
                    "/",
                    notify_payload("Implemented the fix and all tests pass."),
                ])

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

    def test_turn_complete_consumes_fallback_markers_but_suppresses_payload_without_thread(self):
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
                exit_code = module.main([
                    "--event",
                    "agent-turn-complete",
                    "--cwd",
                    "/",
                    json.dumps({
                        "type": "agent-turn-complete",
                        "last-assistant-message": "Implemented the fix and all tests pass.",
                    }),
                ])

        self.assertEqual(exit_code, 0)
        self.assertFalse(legacy_marker.exists())
        self.assertFalse(valid_marker.exists())
        send.assert_not_called()

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
