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
grep -rn "# fork" gateway/ plugins/ scripts/ skills/ agent/ hermes_state.py
# Every upstream file that imports our package:
grep -rln "gateway.local_patches" gateway/ plugins/ agent/ hermes_state.py
```

Prefer these greps over the line numbers in this doc — **line numbers drift on
every upstream merge**; the `# fork` markers and function anchors do not.

**Expected hook counts** (diff these after every rebase — a count that drops
means a merge silently ate a hook). Every *call site* is tagged, not just the
import block: an import can survive while the call it feeds is dropped, and
Python won't complain about the now-unused import.

| File | `# fork` lines |
|---|---|
| `plugins/platforms/email/adapter.py` | 19 |
| `gateway/run.py` | 11 |
| `gateway/platforms/bluebubbles.py` | 7 |
| `skills/productivity/google-workspace/scripts/google_api.py` | 6 |
| `gateway/platforms/signal.py` | 2 |
| `plugins/platforms/whatsapp/adapter.py` | 2 |
| `gateway/platforms/base.py` | 1 |
| `hermes_state.py` | 2 |
| `agent/thread_scoped_output.py` | 1 |
| **total (excl. fork-owned files)** | **51** |

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
| `principals.py` | `sender_is_principal`, `third_party_banner_for`, `principal_channel_banner`, `display_name_for`, `whatsapp_display_name`, `always_prefix_speaker` (+ private env-parsing & name-templating helpers) | `gateway/platforms/base.py` re-exports; adapters call `principal_channel_banner` / `display_name_for`; `gateway/run.py` calls `always_prefix_speaker` |
| `quiet.py` | `is_quiet()` | `gateway/run.py` (aliased as `_gateway_quiet`) |
| `status_copy.py` | `busy_ack_text(...)` — warm busy-ack variants | `gateway/run.py` busy-ack block |
| `email_outbound.py` | `default_subject()`, `lift_subject()`, `from_header()`, `apply_signature()`, Reply All recipient helpers | `plugins/platforms/email/adapter.py` (4 send paths) |
| `bluebubbles_gate.py` | `sender_allowed()`, `seen_or_add()`, `stable_chat_id()`, `remember_chat_guid()` | `gateway/platforms/bluebubbles.py` webhook handler |
| `fd_hygiene.py` | `reap_dead_reader_conns()`, `shared_devnull_sink()`, `raise_nofile_soft_limit()` | `hermes_state.py` `_get_read_conn`; `agent/thread_scoped_output.py` `_ensure_installed`; `gateway/run.py` `start_gateway` |

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
preserves roles while excluding Lucy's own address (the IMAP fetch loop's
`to_header`/`cc_header` keys are what feed it — both tagged, since they are a
call site independent of `_reply_all_context()` itself). `_standalone_send` also
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
Upstream's `test_bluebubbles.py::TestBlueBubblesWebhookUrl::test_default_host`
asserts `"localhost"`, so it fails by design here — expected, not a regression.
(Upstream has since made `DEFAULT_WEBHOOK_HOST` itself `127.0.0.1`; if it also
stops normalizing back to `localhost`, this patch can be dropped entirely.)

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

> **When upstream adds a new busy-ack branch**, the conflict shows up here as
> upstream re-expanding the `if/elif` chain. Resolution: add the new mode to
> `busy_ack_text` (keyword-only, defaulted, so the hook stays back-compatible)
> and pass it through the single call. `is_redirect_mode` arrived this way.

Upstream's `test_busy_session_ack.py` asserts upstream's literal ack strings, so
those cases fail by design on this fork — an expected divergence, not a regression.
Same for the two copy assertions in
`test_subagent_protection_30170.py::TestBusyHandlerDemotesInterruptForSubagents`
(`test_interrupt_still_fires_when_no_subagents`,
`test_queue_mode_unchanged_with_subagents`): the *behavioral* asserts in those
tests (`parent.interrupt` called / not called) still pass — only the literal
string differs. If a busy-ack test starts failing on anything other than copy,
that IS a regression.

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

### 8. Shared-chat context — group + 1:1 continuity
Lucy kept losing the thread. Two independent causes, one symptom ("no idea what
you're referring to"):

**(a) Group chats — one session per *participant*.** `build_session_key` appends
`user_id` for non-thread group chats when `group_sessions_per_user` is true
(upstream default), so Valerie's exchange and Ryan's follow-up in the *same*
iMessage group landed in two unrelated sessions. **Fixed in upstream config, not
code** — `group_sessions_per_user: false` (see §"Runtime-only config"). That flag
also flips `is_shared_multi_user_session`, which makes upstream prefix every
stored message with `[user_name]`; that prefix is what preserves who-said-what,
because the principal banner lives only in the *current turn's* ephemeral system
prompt and is absent from history. **DMs are unaffected** — `build_session_key`
returns from its `chat_type == "dm"` branch before any of this, so the
Ryan/Valerie 1:1 privacy wall is intact.

**(b) 1:1 chats — iMessage↔SMS split the session.** A BlueBubbles chat GUID
embeds the service, so one conversation is `iMessage;-;+1555…` until it
green-bubbles and becomes `SMS;-;+1555…`. Since DM sessions key on `chat_id`,
a service flip silently started a fresh session mid-conversation. Logic:
`gateway/local_patches/bluebubbles_gate.py`.

| Helper | Effect |
|---|---|
| `stable_chat_id(...)` | DMs key on the service-independent `chatIdentifier`; groups keep the GUID (an MMS group really is a different chat) |
| `remember_chat_guid(...)` | Warms `_guid_cache` from every inbound webhook |

`remember_chat_guid` is a prerequisite, not a nicety: outbound `send()` resolves
a handle via `_resolve_chat_guid`, whose `/api/v1/chat/query` is a **single
un-paginated page capped at 100 chats**. Past that cap a reply addressed by
handle misses and falls through to `_create_chat_for_handle`, starting a *new*
iMessage thread instead of replying in the existing one. Warming the cache from
inbound (which carries identifier + GUID authoritatively) makes resolution exact
and free, and re-points replies at the current service after a flip.

**Speaker naming.** Adapters set `user_name` to the raw handle, so the new
prefixes would read `[+15173166753]`. `principals.display_name_for()` maps a
**verified transport handle** to its configured principal name; unknown handles
keep their raw fallback. A self-chosen display name that collides with a
principal name is refused in favor of the handle, so a third party in a shared
group cannot have their messages stored as `[Ryan]`.

| Env var | Effect |
|---|---|
| `HERMES_ALWAYS_NAME_PREFIX` | Prefix `[Name]` in **1:1s** too, not just shared sessions (upstream prefixes only shared ones) |

**Hooks** (all `# fork`): `gateway/platforms/bluebubbles.py` — `remember_chat_guid`
+ `stable_chat_id` at `session_chat_id`, and `user_name=display_name_for(...)`;
`gateway/platforms/signal.py` and `plugins/platforms/whatsapp/adapter.py` —
`user_name=` (WhatsApp via `whatsapp_display_name`, which expands LID↔phone);
`gateway/run.py` — `or always_prefix_speaker()` on the sender-prefix guard.
Tests: `tests/gateway/test_local_patches_group_context.py`.

> **Deploy note:** (b) changes DM session keys, so existing BlueBubbles DM
> history does not carry over — each 1:1 starts one fresh session at rollout.

### 9. Fd hygiene — stop the gateway starving itself of file descriptors

On 2026-08-14 the five-day-old gateway sat at 254 of launchd's 256 soft
`RLIMIT_NOFILE` and everything that needed a new fd failed with `EMFILE` —
Exa web search (DNS `NameResolutionError`), IMAP polling, `search_files`,
`execute_code`, cron reads. Two independent slow leaks, both upstream bugs;
logic in `gateway/local_patches/fd_hygiene.py`:

**(a) Dead reader-thread SQLite connections** (~2 fds each; 67 leaked =
~137 fds). `SessionDB._get_read_conn` opens a per-thread read-only connection
and holds it *strongly* in `_read_conns` (deliberate upstream design: a
GC'd-without-`close()` connection would permanently leak its
`sqlite_safe_read` byte-probe tracking entry). Nothing closed a connection
whose owning thread exited, and `gateway/run.py` churns short-lived threads
constantly. `reap_dead_reader_conns(db, conn)` records each reader's owning
thread and, on every new registration, closes (via the tracked `close()`, so
the probe registry stays honest) the connections of exited threads.

The second hook, `check_same_thread=False` on the reader connect, is what
makes any cross-thread `close()` legal — including the drain in
`SessionDB.close()`, which previously raised `ProgrammingError` into a
swallowing `except` on every reader conn (silent upstream bug #2). Safe:
reader conns are only ever *used* by their owning thread (`threading.local`).

**(b) Re-installed devnull sinks** (76 leaked fds).
`agent/thread_scoped_output._ensure_installed` opened a fresh `/dev/null`
sink every time an outside `redirect_stdout` (e.g. the memory curator's) had
rebound `sys.stdout`/`sys.stderr`, and superseded proxies kept their sinks
referenced. `shared_devnull_sink()` is one process-lifetime handle shared by
every proxy (write-only devnull → thread-safe to share).

**(c) Belt-and-suspenders:** `raise_nofile_soft_limit()` at `start_gateway`
lifts the soft limit 256 → 4096 (never lowers; respects the hard limit).

**Hooks** (all `# fork`): `hermes_state.py` — reaper call after
`_read_conns.add(conn)` + `check_same_thread=False` kwarg;
`agent/thread_scoped_output.py` — `sink = shared_devnull_sink()`;
`gateway/run.py` — `raise_nofile_soft_limit()` in `start_gateway`.
Tests: `tests/gateway/test_local_patches_fd_hygiene.py`.
Upstream-worthy: yes, all three (a+b are real upstream leaks).

## Runtime-only config (NOT in this repo)

Lives in `~/.hermes/config.yaml` on the deployment host, applied at deploy time
(not tracked here). Re-apply after any config reset. Backup on last change:
`~/.hermes/config.yaml.bak-b7971c268`.

```yaml
group_sessions_per_user: false           # shared group sessions + [Name] prefixes (patch §8)
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

## Commit reference (over upstream base `2446c8bb6`, rebased 2026-08-09)

Feature commits (behavior), then the refactors that moved them under
`gateway/local_patches/`. **Hashes change on every rebase** — regenerate rather
than trusting the list below.

```
6cc2c12c2 fix(email): honor a Subject: line in outbound emails instead of hardcoding
cab1e06dd fix(whatsapp-bridge): add missing link-preview-js dependency
2e823d7f8 fix(email): support a display name on outbound From headers
ea4eca23e feat(email): append a configurable signature to outbound mail
749f04300 feat(bluebubbles): sender allowlist via BLUEBUBBLES_ALLOWED_USERS
945b49f65 fix(bluebubbles): register webhook on 127.0.0.1, not localhost
eef47c721 fix(bluebubbles): dedupe inbound messages by GUID
784a17cb5 feat(bluebubbles): BLUEBUBBLES_ALLOW_ALL_USERS to open inbound
65b86a76e feat(gateway): flag third-party inbound with a NOT-A-PRINCIPAL banner
c15d15b32 feat(gateway): quiet_system_messages flag + warmer busy-ack copy
7d176e558 feat(gateway): positively identify principals on inbound
8db869fa4 refactor(local-patches): extract principal/banner logic
36cd62715 refactor(local-patches): extract quiet-mode + busy-ack copy
a80b0acb5 refactor(local-patches): extract email-outbound + bluebubbles gating
252bec612 refactor(gateway): drive heartbeat copy from generic status-phrase config
bb26830cc docs(local-patches): add LOCAL_PATCHES.md fork inventory
74a042d36 feat(local-patches): make principal banner names configurable
c2cfa38a0 docs: state the 'fork patches in separate files' rule in AGENTS.md
11878647f fix(email): Reply All by default so principals aren't dropped from replies
504701a37 refactor(google-workspace): fork logic to _gws_fork.py; add calendar routing
423c31a02 docs(local-patches): refresh inventory after rebase onto upstream 0a62610f1
a6c22c00a chore(local-patches): tag every hook call site so the discovery grep is honest
a902e151a fix(gateway): keep conversation context across participants and services
```

Regenerate the current list any time with:
`git log --oneline --reverse upstream/main..main`
