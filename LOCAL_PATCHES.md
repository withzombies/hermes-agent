# LOCAL_PATCHES.md - Fork Inventory

This is the withzombies fork of NousResearch/hermes-agent. Origin is our fork;
upstream is read-only. Deployment/persona context lives in CLAUDE.md.

## Current Base

Rebased onto upstream `ee4452991d17534aa561f31ee55596d082aa94e7` on 2026-09-13.
The previous fork history is preserved on `backup/pre-upstream-20260913`.
The 26 local commits were consolidated before rebasing because upstream moved
the gateway methods into mixins and consolidated the email send paths.

Keep fork logic in separate files with small `# fork` call-ins. Prefer native
configuration and retire patches when upstream implements the behavior.

## Hook Inventory

Use `rg -n '# fork' gateway/ plugins/ skills/` to inspect hooks. Counts exclude
fork-owned helper files and include every upstream call site.

| File | Count |
| --- | --- |
| gateway/run.py | 3 |
| gateway/run_busy.py | 1 |
| gateway/run_inbound.py | 1 |
| gateway/run_notifications.py | 1 |
| gateway/run_turn.py | 4 |
| gateway/platforms/bluebubbles.py | 5 |
| gateway/platforms/signal.py | 1 |
| plugins/platforms/whatsapp/adapter.py | 2 |
| plugins/platforms/email/adapter.py | 10 |
| skills/productivity/google-workspace/scripts/google_api.py | 8 |
| Total | 36 |

AGENTS.md also carries a fork pointer. JSON dependency declarations and the
Python future import are inherently inline data/compiler directives.

## Email

`gateway/local_patches/email_outbound.py` supplies:
- `EMAIL_DEFAULT_SUBJECT`: fallback subject.
- `EMAIL_DISPLAY_NAME`: RFC 5322 From display name.
- `EMAIL_SIGNATURE`: deduplicated signature; literal backslash-n is supported.
- `lift_subject`: leading Subject line becomes the standalone send's header.
- Reply All recipient math: sender + original To remain To, original Cc remain
  Cc, own address excluded, addresses deduplicated.

Upstream now shares `EmailAdapter._new_reply` across ordinary and attachment
sends. Apply headers/signature there once. `_parse_fetched_message` captures
To/Cc and `_dispatch_message` stores recipient context. Standalone delivery
retains its separate subject/From/signature hooks. Preserve upstream sender
authentication, TLS configuration, attachment handling, and SMTP cleanup.

## Verified Identity and Conversation Continuity

`gateway/local_patches/principals.py` resolves verified transport handles:
- `HERMES_PRINCIPAL_IDENTIFIERS`: principal handle list.
- `HERMES_PRINCIPAL_NAMES`: Name=handle|handle;Name=handle mapping.
- `HERMES_PRINCIPAL_PRIMARY`: primary sign-off identity.
- `HERMES_ALWAYS_NAME_PREFIX`: retain speaker names in DMs as well as groups.

`apply_event_identity` sets the event's principal/third-party channel banner
and source name. WhatsApp expands verified LID/phone aliases. Signal includes
the sender UUID. Unknown display names cannot impersonate configured names.
Each adapter calls this on its completed event. No base-adapter re-export is
needed after upstream's event/source extraction.

`gateway/local_patches/bluebubbles_gate.py` supplies allowlist gating
(`BLUEBUBBLES_ALLOWED_USERS`, `BLUEBUBBLES_ALLOW_ALL_USERS`), bounded GUID
deduplication, service-independent DM session IDs, and inbound GUID-cache
warming. Group IDs remain unchanged. Preserve these when updating the webhook
handler or SMS/iMessage changes will split conversations again.

Use native `group_sessions_per_user: false` to share group history between
participants. DMs retain their separate session privacy boundaries.

## Quiet Mode and Busy Acknowledgments

`gateway/local_patches/quiet.py` reads the internal env bridge from
`gateway.quiet_system_messages`. The bridge lives in gateway/run.py.
Suppress routine operational notices in:
- gateway/run.py: `_prepare_gateway_status_message`.
- gateway/run_notifications.py: `_deliver_platform_notice`.
- gateway/run_turn.py: compression failure/fallback and inactivity notices.

`gateway/local_patches/status_copy.py` formats warm acknowledgments through
`gateway/run_busy.py::_compose_busy_ack_message`. Preserve queue, redirect,
steer, compression, and subagent semantics. Upstream literal-copy tests may
differ; behavioral failures are regressions.

Heartbeat phrases use upstream configuration, not code hooks.

## Google Workspace

Fork helpers are sibling modules because the skill scripts run standalone:
- `_gws_fork.py`: Gmail Reply All, calendar aliases, calendar update patches.
- `_gws_docs.py`: recursive table text reads, raw document reads, native row
  insertion, and revision-checked batch updates over either gws or Python SDK.

Calendar aliases come from runtime-only `~/.hermes/calendar_aliases.json`.
Gmail Reply All is the default; `--no-reply-all` restores sender-only behavior.
Calendar updates patch events in place and preserve IDs/attendee state.

Docs already supported create/append before this update. Missing native edit
commands and a reader that omitted table cells made structured edits awkward.
`docs get --raw` now exposes indices, tabs, styles, links, and revisionId.
`docs insert-row` inserts an empty row. `docs batch-update` accepts a JSON
request array and requires the revision read from the Doc. Read again between
structural changes and filling cells. Each batch is atomic; separate commands
are not. See `references/docs-editing.md`.

Keep the correct `from __future__ import annotations` directive in the wrapper
for older Python launchers. The supported deployed interpreter is the runtime
venv Python 3.11; the future import alone does not install dependencies.

Deploy scripts to BOTH the runtime checkout and active bundle:
`~/.hermes/skills/productivity/workspace-and-documents/scripts/google-workspace/`.
Sync google_api.py, _gws_fork.py, _gws_docs.py, _hermes_home.py, gws_bridge.py,
and setup.py. Update the active bundle's Docs reference and interpreter guidance.
Archived skill copies remain inactive.

## WhatsApp Dependency

scripts/whatsapp-bridge/package.json and package-lock.json carry
`link-preview-js`. Run npm install in the runtime bridge after an update.

## Retired Patches

All three fd-hygiene hooks are retired in this rebase:
- SessionDB now has a bounded reader connection pool with cross-thread cleanup.
- thread_scoped_output reuses sinks and routing state.
- start_gateway calls hermes_cli.resource_limits.apply_nofile_soft_limit.

The obsolete fd_hygiene module and tests tied to the old reader internals were
removed. Validate upstream pool/output/resource-limit tests instead.

The BlueBubbles IPv4 override is retired: upstream now keeps 127.0.0.1 itself.

## Runtime Configuration

Preserve ~/.hermes/config.yaml, .env, SOUL.md, OAuth files, calendar aliases,
sessions, and active skill customizations. No credentials belong in git.

Required native settings:
- group_sessions_per_user: false
- gateway.quiet_system_messages: true
- display.long_running_notifications: generic
- display.generic_status_phrases.mode: replace
- display.generic_status_phrases.status: operator's existing phrase list

Keep heartbeat and busy acknowledgments enabled; per-platform restart notices
are disabled. Behavioral/personal routing details remain in runtime skills.

## Validation and Deployment

Run focused Google Workspace, channel, local identity, email, reader pool,
thread output, and resource-limit tests. Import the gateway and live adapters.
`tests/skills/google_docs_live_check.py SCRIPT_PATH` exercises real Docs writes
in a newly created temporary document and moves it to trash in finally.

Push our rebased branch using an explicit force-with-lease against the expected
old origin/main. Preserve a backup branch in both checkouts before switching
the runtime to the new release. Install the locked dependencies, sync active
skill copies/references, restart with `hermes gateway restart`, and verify the
new gateway PID, running revision, and channel connections. Do not reset chats
or mutate their cached conversation history to announce the update.
