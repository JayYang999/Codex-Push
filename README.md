# Codex Push

Local macOS notifications and voice cues for Codex.

## What It Does

- Sends a macOS notification when a Codex turn completes after using a tool.
- Plays a short local voice cue for completed tool-using turns.
- Keeps notification text privacy-safe: it only shows the event and project label.
- Avoids false `needs approval` alerts when Codex is using automatic approval review.
- Generates local MP3 sounds during install with Edge TTS:
  - `en-US-GuyNeural`: `Codex task complete.`
  - `en-US-GuyNeural`, `rate=-5%`, `pitch=+8Hz`: `Codex needs your approval.`

## Current Approval Behavior

Codex `PermissionRequest` hooks fire when an approval request is created, including requests that may be routed to automatic review. Because the hook payload does not currently expose a reliable "waiting for human approval" signal, `approval-requested` is silent unless called with `--human-approval-confirmed`.

That means this project prefers no false approval alerts over noisy approval alerts.

## Install

```bash
pipx install edge-tts
python3 install.py
```

The installer writes to `~/.codex/mac-push/`, backs up `~/.codex/config.toml` and `~/.codex/hooks.json`, generates the two MP3 files, updates the top-level `notify` setting, and adds a `PostToolUse` hook that marks real tool activity.

After installing or updating hooks, run `/hooks` in Codex and trust the new hook if Codex marks it for review.

## Test

```bash
PYTHONPYCACHEPREFIX=/private/tmp/codex_push_pycache python3 -m unittest tests/test_codex_mac_push.py tests/test_install.py
```

## Manual Checks

```bash
python3 codex_mac_push.py --event agent-turn-complete --dry-run --cwd /
python3 codex_mac_push.py --event approval-requested --dry-run --cwd /tmp/example-project
```

To test a real sound locally:

```bash
/usr/bin/afplay ~/.codex/mac-push/sounds/codex_task_complete.mp3
/usr/bin/afplay ~/.codex/mac-push/sounds/codex_needs_approval.mp3
```
