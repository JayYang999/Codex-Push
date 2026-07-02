#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUPPRESSED_FRONTMOST_APPS = {"Codex", "Terminal", "iTerm", "iTerm2", "Warp"}
SOUND_DIR = Path.home() / ".codex" / "mac-push" / "sounds"
EVENT_SOUND_FILES = {
    "agent-turn-complete": "codex_task_complete.wav",
    "approval-requested": "codex_needs_approval.wav",
}
EXISTING_NOTIFY = [
    str(
        Path.home()
        / ".codex"
        / "computer-use"
        / "Codex Computer Use.app"
        / "Contents"
        / "SharedSupport"
        / "SkyComputerUseClient.app"
        / "Contents"
        / "MacOS"
        / "SkyComputerUseClient"
    ),
    "turn-ended",
]


@dataclass(frozen=True)
class Notification:
    title: str
    body: str


def resolve_notification(event: str, cwd: Path) -> Notification:
    titles = {
        "agent-turn-complete": "Codex task complete",
        "approval-requested": "Codex needs approval",
    }
    if event not in titles:
        raise ValueError(f"Unsupported event: {event}")

    project_label = cwd.name or "Codex"
    return Notification(title=titles[event], body=f"Project: {project_label}")


def sound_path_for_event(event: str) -> Path:
    return SOUND_DIR / EVENT_SOUND_FILES[event]


def should_send_notification(frontmost_app: str | None) -> bool:
    if frontmost_app is None:
        return True
    return frontmost_app not in SUPPRESSED_FRONTMOST_APPS


def frontmost_app_name() -> str | None:
    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    name = result.stdout.strip()
    return name or None


def applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def send_macos_notification(notification: Notification) -> None:
    script = (
        f'display notification "{applescript_string(notification.body)}" '
        f'with title "{applescript_string(notification.title)}"'
    )
    subprocess.run(["/usr/bin/osascript", "-e", script], check=False, timeout=5)


def play_event_sound(event: str) -> None:
    sound_path = sound_path_for_event(event)
    if not sound_path.exists():
        return
    try:
        subprocess.run(
            ["/usr/bin/afplay", str(sound_path)],
            check=False,
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return


def chain_existing_notify(command: Iterable[str]) -> None:
    command = list(command)
    if not command:
        return
    try:
        subprocess.run(
            command,
            check=True,
            timeout=10,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send status-only Codex notifications on macOS.")
    parser.add_argument("--event", choices=("agent-turn-complete", "approval-requested"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--chain-existing-notify", action="store_true")
    parser.add_argument("--human-approval-confirmed", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    args.codex_notify_args = unknown
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.chain_existing_notify and args.codex_notify_args:
        chain_existing_notify(EXISTING_NOTIFY + args.codex_notify_args)

    notification = resolve_notification(args.event, Path(args.cwd))
    if args.dry_run:
        print(notification.title)
        print(notification.body)
        return 0

    if args.event == "approval-requested" and not args.human_approval_confirmed:
        return 0

    if should_send_notification(frontmost_app_name()):
        send_macos_notification(notification)
        play_event_sound(args.event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
