#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
CODEX_HOME = Path.home() / ".codex"
INSTALL_DIR = CODEX_HOME / "mac-push"
SOUNDS_DIR = INSTALL_DIR / "sounds"
CONFIG_PATH = CODEX_HOME / "config.toml"

SOURCE_SCRIPT = REPO_ROOT / "codex_mac_push.py"
TARGET_SCRIPT = INSTALL_DIR / "codex_mac_push.py"
SOURCE_SOUNDS = {
    "codex_task_complete.wav": REPO_ROOT / "sounds" / "codex_task_complete.wav",
    "codex_needs_approval.wav": REPO_ROOT / "sounds" / "codex_needs_approval.wav",
}


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def backup(path: Path, label: str) -> Path | None:
    if not path.exists():
        return None
    backup_path = path.with_name(f"{path.name}.{label}-{timestamp()}")
    shutil.copy2(path, backup_path)
    return backup_path


def notify_line() -> str:
    computer_use_notify = (
        CODEX_HOME
        / "computer-use"
        / "Codex Computer Use.app"
        / "Contents"
        / "SharedSupport"
        / "SkyComputerUseClient.app"
        / "Contents"
        / "MacOS"
        / "SkyComputerUseClient"
    )
    mac_push_notify = [
        "/usr/bin/python3",
        str(TARGET_SCRIPT),
        "--event",
        "agent-turn-complete",
    ]

    if computer_use_notify.exists():
        return (
            'notify = ['
            f'{json.dumps(str(computer_use_notify))}, '
            '"turn-ended", '
            '"--previous-notify", '
            f'{json.dumps(json.dumps(mac_push_notify, separators=(",", ":")))}'
            "]\n"
        )

    return "notify = " + json.dumps(mac_push_notify) + "\n"


def replace_top_level_notify(text: str) -> str:
    lines = text.splitlines(keepends=True)
    start = None
    end = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            break
        if stripped.startswith("notify"):
            start = index
            bracket_depth = line.count("[") - line.count("]")
            end = index + 1
            while bracket_depth > 0 and end < len(lines):
                bracket_depth += lines[end].count("[") - lines[end].count("]")
                end += 1
            break

    if start is None:
        return notify_line() + ("\n" if text and not text.startswith("\n") else "") + text
    return "".join(lines[:start]) + notify_line() + "".join(lines[end:])


def install_files() -> None:
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_SCRIPT, TARGET_SCRIPT)
    TARGET_SCRIPT.chmod(0o755)
    for name, source in SOURCE_SOUNDS.items():
        shutil.copy2(source, SOUNDS_DIR / name)


def install_config() -> Path | None:
    CODEX_HOME.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text("")
        backup_path = None
    else:
        backup_path = backup(CONFIG_PATH, "codex-push-backup")
    CONFIG_PATH.write_text(replace_top_level_notify(CONFIG_PATH.read_text()))
    return backup_path


def main() -> int:
    install_files()
    config_backup = install_config()
    print(f"installed_script={TARGET_SCRIPT}")
    print(f"installed_sounds={SOUNDS_DIR}")
    if config_backup:
        print(f"config_backup={config_backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
