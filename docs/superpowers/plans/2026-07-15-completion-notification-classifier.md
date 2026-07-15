# Completion Notification Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Suppress `Codex task complete` when an agent turn ends by asking the user for input, without adding model calls or changing approval notifications.

**Architecture:** Parse the existing Codex hook and notify JSON payloads, key tool-use markers by session and turn, and classify `last-assistant-message` with a small local rule set. Consume only the matching turn marker and send only when the final message does not request user input.

**Tech Stack:** Python 3 standard library, `unittest`, Codex user-level notify configuration.

---

### Task 1: Reproduce clarification false positives

**Files:**
- Modify: `tests/test_codex_mac_push.py`

- [x] **Step 1: Add a notify payload helper and failing clarification tests**

Add a helper that serializes an `agent-turn-complete` payload with
`last-assistant-message`. Add tests using both real clarification messages from
session `019f65ab-9b98-7ab1-8f2e-49479f1bae5f`. Each test must mark tool use,
invoke turn completion with the payload, and assert that neither a notification
nor sound is produced.

- [x] **Step 2: Add failure-policy and positive tests**

Add tests showing that missing or malformed payloads suppress completion, while
`"Implemented the fix and all 34 tests pass."` still sends one notification and
plays `agent-turn-complete`.

- [x] **Step 3: Run the focused tests and verify RED**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/codex_push_pycache python3 -m unittest tests.test_codex_mac_push
```

Expected: the clarification and missing-payload tests fail because the current
script ignores the notify payload.

### Task 2: Implement local completion classification

**Files:**
- Modify: `codex_mac_push.py`
- Modify: `README.md`
- Test: `tests/test_codex_mac_push.py`

- [x] **Step 1: Parse the Codex payload**

Add a function that scans unknown notify arguments for a JSON object whose
`type` is `agent-turn-complete`, returning `last-assistant-message` only when it
is a non-empty string. Invalid JSON is ignored without raising.

- [x] **Step 2: Classify requests for user input**

Add a deterministic function that suppresses messages ending in `?` or `？`, or
containing explicit Chinese or English input requests such as `需要你确认`,
`请选择`, `请提供`, `下一个关键问题`, `please confirm`, `please choose`, and
`need your input`.

- [x] **Step 3: Apply the classifier after consuming the marker**

For `PostToolUse`, store a marker keyed by `session_id` and `turn_id`. For
`agent-turn-complete`, consume only the marker matching `thread-id` and
`turn-id`. Return without notifying when no valid final message exists or the
message requires user input. Do not change approval, dry-run, frontmost-app,
sound, or notifier-chain behavior.

- [x] **Step 4: Document the completion rule**

Update `README.md` to state that task-complete notifications require tool use and
a valid notify payload whose final assistant message is not waiting for user
input. State that classification is local and consumes no model tokens.

- [x] **Step 5: Run all tests and verify GREEN**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/codex_push_pycache python3 -m unittest tests/test_codex_mac_push.py tests/test_install.py
python3 -m py_compile codex_mac_push.py install.py
```

Expected: all tests pass and compilation produces no output.

### Task 3: Install and verify the tested script

**Files:**
- Copy: `codex_mac_push.py` to `~/.codex/mac-push/codex_mac_push.py`

- [x] **Step 1: Install only the script**

Copy the tested script over the installed script and retain executable mode. Do
not regenerate audio or rewrite `config.toml`/`hooks.json` because their commands
already pass the Codex payload through the existing notifier chain.

- [x] **Step 2: Verify installed behavior without notifications**

Run the installed script against temporary state with representative payloads,
mocking notification effects through unit tests and comparing repository and
installed script hashes.

Expected: clarification payloads produce no send path, completion payloads pass
classification, and both script hashes match.

### Task 4: Publish the fix

**Files:**
- Commit all modified source, tests, README, and plan files.

- [x] **Step 1: Review scope and formatting**

Run `git diff --check`, inspect `git diff`, and confirm no generated audio,
state files, or unrelated changes are included.

- [ ] **Step 2: Commit**

```bash
git add codex_mac_push.py tests/test_codex_mac_push.py README.md docs/superpowers/specs/2026-07-15-completion-notification-classifier-design.md docs/superpowers/plans/2026-07-15-completion-notification-classifier.md
git commit -m "Suppress completion push while awaiting input"
```

- [ ] **Step 3: Push main**

```bash
git push origin main
```

Expected: `origin/main` advances to the new implementation commit.
