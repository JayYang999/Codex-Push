# Codex Push

Local macOS notifications and voice cues for Codex.

## What It Does

- Sends a macOS notification when a Codex turn completes.
- Plays a short local voice cue for completed turns.
- Keeps notification text privacy-safe: it only shows the event and project label.
- Avoids false `needs approval` alerts when Codex is using automatic approval review.
- Generates local WAV sounds during install with macOS `say` voices:
  - `Eddy`: `Codex task complete`
  - `Rocko`: `Codex needs approval`

## Current Approval Behavior

Codex `PermissionRequest` hooks fire when an approval request is created, including requests that may be routed to automatic review. Because the hook payload does not currently expose a reliable "waiting for human approval" signal, `approval-requested` is silent unless called with `--human-approval-confirmed`.

That means this project prefers no false approval alerts over noisy approval alerts.

## Install

```bash
python3 install.py
```

The installer writes to `~/.codex/mac-push/`, backs up `~/.codex/config.toml`, generates the two WAV files, and updates the top-level `notify` setting.

## Test

```bash
PYTHONPYCACHEPREFIX=/private/tmp/codex_push_pycache python3 -m unittest tests/test_codex_mac_push.py
```

## Manual Checks

```bash
python3 codex_mac_push.py --event agent-turn-complete --dry-run --cwd /
python3 codex_mac_push.py --event approval-requested --dry-run --cwd /tmp/example-project
```

To test a real sound locally:

```bash
/usr/bin/afplay ~/.codex/mac-push/sounds/codex_task_complete.wav
/usr/bin/afplay ~/.codex/mac-push/sounds/codex_needs_approval.wav
```
