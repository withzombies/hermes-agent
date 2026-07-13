# LOCAL_PATCHES.md — our fork's deltas over upstream

This is a fork of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).
This file is the **canonical inventory of every change we carry on top of
upstream**, so we can re-verify (and re-apply) our patches after each upstream
merge/rebase. Keep it in sync when you add, change, or drop a fork patch.

- **Remotes:** `origin` = `withzombies/hermes-agent` (our fork — we push here);
  `upstream` = `NousResearch/hermes-agent` (we pull from here, never push).
- Deployment model, channel wiring, and the *why* behind individual patches
  live in [CLAUDE.md](CLAUDE.md). This file is the **map**; CLAUDE.md is the
  **context**.

## Maintenance model — logic in a package, one-line hooks in upstream files

To keep the rebase-conflict surface near-zero, all fork logic lives in the
fork-owned package **`gateway/local_patches/`**. Upstream-owned files carry only
a **single-line call-in** (one import + one call) marked with a `# fork` comment.
A brand-new file never conflicts; a one-line hook almost never does.

**Discovery — how to find every hook after an upstream merge:**

```bash
# Every hook we inject into upstream-owned files is tagged:
grep -rn "# fork" gateway/ plugins/ scripts/ skills/
# Every upstream file that imports our package:
grep -rln "gateway.local_patches" gateway/ plugins/
```

Prefer these greps over the line numbers in this doc — **line numbers drift on
every upstream merge**; the `# fork` markers and function anchors do not.

One doc hook is upstream-owned and may be clobbered by an upstream merge:
`AGENTS.md` carries a `<!-- fork -->` pointer block near the top (re-add it if a
merge drops it). `CLAUDE.md` is fork-owned and safe.

## Updating to a new upstream

1. `git fetch upstream && git rebase upstream/main` (our historical practice;
   `merge` works too). Files under `gateway/local_patches/**` won't conflict.
2. Resolve conflicts **only at the hook sites**. The pattern is always the same:
   take upstream's structural change, then re-apply our one-line hook on top
   (re-add the `# fork` import/call). See the per-patch tables below for what
   each hook should look like.
3. Re-verify hooks are all present: `grep -rn "# fork" gateway/ plugins/ scripts/ skills/`
   and diff the count against this doc.
4. Import smoke test with the runtime venv (catches missing hooks / new upstream
   deps / import cycles — `principals.py` must **not** import `base`):
   ```bash
   ~/.hermes/hermes-agent/venv/bin/python -c "import gateway.run, \
     gateway.platforms.base, gateway.platforms.bluebubbles, gateway.platforms.signal, \
     plugins.platforms.whatsapp.adapter, plugins.platforms.email.adapter, \
     gateway.local_patches.principals, gateway.local_patches.quiet, \
     gateway.local_patches.status_copy, gateway.local_patches.email_outbound, \
     gateway.local_patches.bluebubbles_gate; print('OK')"
   ```
5. Deploy: `git push origin main`; in `~/.hermes/hermes-agent` fast-forward to
   `local/main`; re-apply the runtime-only config (see §"Runtime-only config");
   `hermes gateway restart`; confirm healthy. (`hermes update` stashes local
   changes — re-verify hooks after it.)

## Fork-owned modules (`gateway/local_patches/`) — never conflict

| Module | Provides | Consumed by (hook site) |
|---|---|---|
| `principals.py` | `sender_is_principal`, `third_party_banner_for`, `principal_channel_banner` (+ private env-parsing & name-templating helpers) | `gateway/platforms/base.py` re-exports; adapters call `principal_channel_banner` |
| `quiet.py` | `is_quiet()` | `gateway/run.py` (aliased as `_gateway_quiet`) |
| `status_copy.py` | `busy_ack_text(...)` — warm busy-ack variants | `gateway/run.py` busy-ack block |
| `email_outbound.py` | `default_subject()`, `lift_subject()`, `from_header()`, `apply_signature()`, Reply All recipient helpers | `plugins/platforms/email/adapter.py` (4 send paths) |
| `bluebubbles_gate.py` | `sender_allowed()`, `seen_or_add()` | `gateway/platforms/bluebubbles.py` webhook handler |

## The patches, by domain

### 1. Email — outbound customization
Upstream sends bare-address `From`, a hardcoded `"Hermes Agent"` subject, and no
signature. Logic: `gateway/local_patches/email_outbound.py`.

| Env var | Effect |
|---|---|
| `EMAIL_DEFAULT_SUBJECT` | Fallback subject (replaces hardcoded `"Hermes Agent"`) |
| `EMAIL_DISPLAY_NAME` | RFC 5322 name-addr `From` (Gmail won't stamp it server-side) |
| `EMAIL_SIGNATURE` | Appended below an RFC `-- ` delimiter (literal `\n` allowed; dedup-safe) |

**Hooks** (`plugins/platforms/email/adapter.py`, marked `# fork`): the fork
import block near the top; `_send_email` / `_send_email_with_attachments` /
`_send_email_with_attachment` each call `_from_header()`, `_apply_signature()`,
`_default_subject()`, and `_apply_reply_all_headers()`; `_dispatch_message`
stores original To/Cc headers through `_reply_all_context()` so Reply All
preserves roles while excluding Lucy's own address. `_standalone_send` also
calls `_lift_subject()` (the `Subject:` first-line lift, outbound-only). We
also revert upstream's `from email.utils import formataddr, formatdate` back
to `formatdate` only.

### 2. BlueBubbles — inbound gating
BlueBubbles is a **built-in** platform, so it can't use the shared plugin
`allowed_users_env`/`allow_all_env` registration. Logic:
`gateway/local_patches/bluebubbles_gate.py`.

| Env var | Effect |
|---|---|
| `BLUEBUBBLES_ALLOWED_USERS` | Comma-list allowlist (phone digits-only match, email as-is) |
| `BLUEBUBBLES_ALLOW_ALL_USERS` | Truthy (or a `*` list entry) opens inbound to everyone |

**Hooks** (`gateway/platforms/bluebubbles.py`, `# fork`): import of
`sender_allowed, seen_or_add`; webhook handler calls `seen_or_add(...)` (GUID
dedup — every iMessage double-fires `new-message` + `updated-message`) and
`sender_allowed(...)`.

**Inherently inline (can't be extracted):** `_webhook_url()` forces the IPv4
literal `host = "127.0.0.1"` (not `"localhost"`, which resolves to `::1` first on
macOS and drops every inbound POST). One-line data change, documented in-place.

### 3. Gateway — principal / third-party identity banners
Injects an ephemeral `MessageEvent.channel_prompt` per inbound based on the
**verified** sender handle. Logic: `gateway/local_patches/principals.py`.

| Env var | Effect |
|---|---|
| `HERMES_PRINCIPAL_IDENTIFIERS` | Flat list of principal handles (any form) |
| `HERMES_PRINCIPAL_NAMES` | `Name=handle\|…;Name=handle\|…` — names *and* counts as principal |
| `HERMES_PRINCIPAL_PRIMARY` | Optional — the "boss" (binding/financial sign-off). Defaults to the first name in `HERMES_PRINCIPAL_NAMES` |

Unset → no banner (backward-compatible). **Banner names are not hardcoded** — the
outsider/positive banner text is templated from `HERMES_PRINCIPAL_NAMES` (and
`HERMES_PRINCIPAL_PRIMARY` for the financial-authority clause). Non-principal →
the "⚠️ NOT FROM &lt;principals&gt;" warning; principal → positive named banner.
With no names configured the banners read generically ("your principals").

**Hooks:** `gateway/platforms/base.py` re-exports the four names (so adapter
imports stay unchanged). Adapters set `channel_prompt=principal_channel_banner(...)`:
`gateway/platforms/bluebubbles.py`, `gateway/platforms/signal.py` (passes
`sender, sender_uuid`), `plugins/platforms/whatsapp/adapter.py` (expands
LID↔phone aliases via `expand_whatsapp_aliases` into `_wa_candidates` first).

### 4. Gateway — quiet mode
Suppresses gateway system/status chatter in chat (compaction, retries, provider
errors, no-home-channel prompt, credit bands, idle warnings). Interactive
prompts, busy-ack/heartbeat, and real task results are unaffected. Logic:
`gateway/local_patches/quiet.py`.

| Config (`config.yaml`) | Env bridge | Effect |
|---|---|---|
| `gateway.quiet_system_messages: true` | `HERMES_QUIET_SYSTEM_MESSAGES` | Enables suppression |

**Hooks** (`gateway/run.py`, `# fork`): `_gateway_quiet` is an import alias of
`is_quiet`; the config→env bridge sets `HERMES_QUIET_SYSTEM_MESSAGES`; guard
sites `... and not _gateway_quiet()` in `_prepare_gateway_status_message`,
`_deliver_platform_notice`, the compression-failure / aux-fallback sends, and the
inactivity warning.

### 5. Gateway — warm busy-ack copy
Rewords the "you messaged while I'm busy" acks into Lucy's warm voice and keeps
the technical detail (iteration/tool/elapsed) in logs only. Logic:
`gateway/local_patches/status_copy.py::busy_ack_text`. **Hook** (`gateway/run.py`,
`# fork`): the busy-ack `if/elif` chain collapses to one `busy_ack_text(...)` call.

> **Heartbeat copy is NOT a code patch anymore.** Upstream grew a config-driven
> status-phrase catalog (`gateway/status_phrases.py`), so the long-running
> heartbeat copy moved to runtime config — see §"Runtime-only config". The
> `_heartbeat_text` block in `run.py` is upstream-verbatim; do not re-patch it.

### 6. WhatsApp bridge — missing dependency
`scripts/whatsapp-bridge/package.json` adds `"link-preview-js": "^3.2.0"` (+ the
`package-lock.json` entry). Baileys needs it to build outbound link-preview
cards. Inherently inline (a JSON data line — nothing to extract).

### 7. Google Workspace skill — Reply All + calendar routing
`skills/productivity/google-workspace/scripts/google_api.py` is **upstream-owned**,
so it follows the same rule as every other upstream file: fork logic lives in a
**fork-owned sibling module `_gws_fork.py`** (next to it, imported the same way the
script already imports `_hermes_home`), and `google_api.py` carries only
`# fork`-tagged call-ins. `_gws_fork.py` provides:

- `reply_all_recipients(...)` — Reply All recipient math (see below).
- `resolve_calendar(alias)` — maps a friendly `--calendar` alias to a real ID.
- `build_update_patch(...)` — assembles the `events.patch` body for `calendar update`.

**Reply All (pull path).** Upstream `gmail reply` was **sender-only**: it fetched
only `From/Subject/Message-ID`, hardcoded `To = sender`, set no `Cc` — dropping
anyone else on the thread. This is the path external two-way mail rides (the push
adapter drops non-allowlisted senders). `gmail_reply` now reads `To`/`Cc`, resolves
our own address via `getProfile`, and calls `reply_all_recipients()` to Reply All
**by default** (original sender + To → To, Cc → Cc, our address dropped, de-duped);
flags `--to`/`--cc` (additive) and `--no-reply-all` (sender-only). Behavioral
guidance already matched this (`email-recipient-integrity` skill +
`correspondence/references/shared-principal-reply-all.md`) — only the tool couldn't obey.

**Calendar routing.** Lucy kept sending events to Apple/local calendars or her own
`primary` instead of the shared Google calendar. Changes: (a) `--calendar` now
accepts **aliases** via `resolve_calendar()`, read from **`~/.hermes/calendar_aliases.json`**
(NOT in the repo — keeps principal calendar IDs out of pushed code, same policy as
the principal banners); an unknown name falls through to a literal ID. (b) new
`calendar update EVENT_ID …` subcommand (upstream only had list/create/delete) that
patches an event in place. (c) fixed the usage docstring that advertised
`--from/--to` when the real flags are `--start/--end`. Principal-specific routing
("shared events → `--calendar shared`", never Apple/local) lives in the runtime-only
`SOUL.md` and the active bundle `SKILL.md`, not in committed code.

**Multi-copy + aliases-file gotcha:** the skill is deployed to `~/.hermes/skills/`
(**not** this repo). When you change `google_api.py` **or `_gws_fork.py`**, sync all
copies: the active `~/.hermes/skills/productivity/workspace-and-documents/scripts/google-workspace/`
pair (what Lucy runs) + the repo copy under `scripts/`; verify with `md5`. The
`.archive/` copy is inactive; leave it. The aliases file
`~/.hermes/calendar_aliases.json` is deploy-time state — recreate it if lost (maps
`shared`/`ryan`/`lucy` → calendar IDs); without it, alias names simply don't resolve
(real IDs still work).

## Runtime-only config (NOT in this repo)

Lives in `~/.hermes/config.yaml` on the deployment host, applied at deploy time
(not tracked here). Re-apply after any config reset. Backup on last change:
`~/.hermes/config.yaml.bak-b7971c268`.

```yaml
display:
  long_running_notifications: generic     # heartbeat pulls from the catalog below
  generic_status_phrases:
    mode: replace                          # use ONLY our phrases for the "status" surface
    status:
    - Still on it — hang tight!
    - Working through it now, thanks for your patience!
    - On it — won't be long!
    - Almost there, hang in with me!
gateway:
  quiet_system_messages: true              # → HERMES_QUIET_SYSTEM_MESSAGES (patch §4)
```

Env vars for the patches above are set in `~/.hermes/.env` (see CLAUDE.md).

## Commit reference (over upstream base `ee66ff279`)

Feature commits (behavior), then the refactor that moved them under
`gateway/local_patches/`:

```
7dd7cc39f fix(email): honor a Subject: line in outbound emails instead of hardcoding
f52c6ac6f fix(whatsapp-bridge): add missing link-preview-js dependency
a30d35edb fix(email): support a display name on outbound From headers
5d317141f feat(email): append a configurable signature to outbound mail
3814ee750 feat(bluebubbles): sender allowlist via BLUEBUBBLES_ALLOWED_USERS
9e9c5de94 fix(bluebubbles): register webhook on 127.0.0.1, not localhost
216278ca8 fix(bluebubbles): dedupe inbound messages by GUID
14c6c9ebf feat(bluebubbles): BLUEBUBBLES_ALLOW_ALL_USERS to open inbound
1acad99a3 feat(gateway): flag third-party inbound with a NOT-A-PRINCIPAL banner
5827d44a0 feat(gateway): quiet_system_messages flag + warmer busy-ack copy
53d989a63 feat(gateway): positively identify principals on inbound
f1f00acb3 refactor(local-patches): extract principal/banner logic
b63a08894 refactor(local-patches): extract quiet-mode + busy-ack copy
97f72339e refactor(local-patches): extract email-outbound + bluebubbles gating
b7971c268 refactor(gateway): drive heartbeat copy from generic status-phrase config
```

Regenerate the current list any time with:
`git log --oneline --reverse upstream/main..main`
