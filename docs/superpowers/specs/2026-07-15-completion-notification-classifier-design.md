# Completion Notification Classifier

## Problem

Codex invokes the external `notify` command when an agent turn ends. A turn can
end because the task was delivered or because Codex asked the user for input.
The current notifier only checks whether the turn used a tool, so tool-assisted
clarification turns incorrectly send `Codex task complete`.

## Scope

Change only the `agent-turn-complete` decision. Approval notifications,
frontmost-app suppression, sounds, existing notifier chaining, and notification
text remain unchanged.

## Decision

Parse the JSON argument that Codex already passes to the notify command and
read `last-assistant-message`. The classifier is local and deterministic; it
does not call a model or consume tokens.

Suppress completion notifications when the final assistant message:

- ends in a question mark;
- contains a direct request for confirmation, selection, missing information,
  approval, or another user response;
- cannot be obtained from a valid Codex notify payload.

Allow completion notifications for ordinary delivery summaries, including
messages that mention completed tests, changed files, and verification results.

The classifier deliberately favors avoiding false completion alerts over
avoiding missed alerts.

## Data Flow

1. Codex invokes the configured notify command with one JSON payload argument.
2. The script chains the pre-existing notifier with the original payload.
3. For `agent-turn-complete`, the script parses `last-assistant-message`.
4. The script consumes the tool-use marker for that turn/project.
5. It sends the notification only when a marker exists and the message does not
   require user input.

Consuming the marker even for suppressed clarification turns prevents that
marker from leaking into a later turn.

## Failure Behavior

Malformed or missing payloads suppress `Codex task complete`. Failures remain
best-effort and must not block Codex. Dry-run behavior remains available and
does not send notifications or play sounds.

## Verification

- The two clarification messages from session
  `019f65ab-9b98-7ab1-8f2e-49479f1bae5f` are suppressed.
- A representative completed-task summary still sends exactly one notification
  and plays the task-complete sound.
- Missing and malformed payloads are suppressed.
- Approval notification tests continue to pass unchanged.
- The installed script matches the tested repository version.
