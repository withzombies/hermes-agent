"""BlueBubbles inbound gating (local fork patch).

BlueBubbles is a *built-in* platform (not a plugin), so it can't use the shared
``allowed_users_env`` / ``allow_all_env`` registration that plugins get. These
helpers provide the equivalent for it:

- ``sender_allowed()`` — BLUEBUBBLES_ALLOWED_USERS allowlist (digits-only phone
  match, email as-is), with BLUEBUBBLES_ALLOW_ALL_USERS / a ``*`` entry opening
  inbound to everyone.
- ``seen_or_add()`` — GUID dedup: every iMessage fires both ``new-message`` and
  ``updated-message`` (and is sometimes re-fired), which would otherwise make
  the agent reply twice. Backed by the adapter's bounded LRU.
"""

import os
from collections import OrderedDict


def _norm_handle(value: str) -> str:
    """Normalize an iMessage handle for allowlist matching: emails lowercased
    as-is, phone numbers reduced to digits only."""
    v = (value or "").strip().lower()
    if "@" in v:
        return v
    return "".join(ch for ch in v if ch.isdigit())


def sender_allowed(sender: str) -> bool:
    """True when *sender* may reach the agent.

    Allowlist not in effect (unset), BLUEBUBBLES_ALLOW_ALL_USERS truthy, or a
    ``*`` entry → everyone allowed. Otherwise the normalized handle must be in
    BLUEBUBBLES_ALLOWED_USERS. The gateway authz layer + persona still apply.
    """
    allow_all = os.getenv("BLUEBUBBLES_ALLOW_ALL_USERS", "").strip().lower() in {
        "true", "1", "yes", "on",
    }
    allowed_raw = os.getenv("BLUEBUBBLES_ALLOWED_USERS", "").strip()
    if not allowed_raw or allow_all or "*" in allowed_raw.split(","):
        return True
    allowed = {_norm_handle(a) for a in allowed_raw.split(",") if a.strip()}
    return _norm_handle(sender) in allowed


def stable_chat_id(
    chat_guid: str,
    chat_identifier: str,
    sender: str,
    is_group_flag: object = False,
) -> str:
    """Session-stable chat id for an inbound BlueBubbles message.

    A BlueBubbles chat GUID embeds the *service*: the same 1:1 conversation is
    ``iMessage;-;+15551234567`` while iMessage is up and ``SMS;-;+15551234567``
    when it green-bubbles. Since the gateway keys DM sessions on chat_id, a
    service flip silently starts a brand-new session and Lucy loses the whole
    thread mid-conversation.

    For DMs, key on the service-independent ``chatIdentifier`` (the bare handle)
    so both services resolve to one session. Groups keep the GUID: an MMS group
    and an iMessage group really are different conversations, and group
    identifiers are far less reliable than the GUID.

    Outbound is unaffected — ``_resolve_chat_guid`` accepts a bare handle and
    maps it back to the exact GUID (see ``remember_chat_guid``, which makes that
    lookup a cache hit instead of a chat-list query).

    Residual: if the two services report *differently formatted* handles
    (``+15551234567`` vs ``5551234567``) the sessions still split. Not
    normalized on purpose — this value must match ``chatIdentifier`` exactly for
    GUID resolution to work.
    """
    guid = (chat_guid or "").strip()
    identifier = (chat_identifier or "").strip()
    if bool(is_group_flag) or ";+;" in guid:
        return guid or identifier
    return identifier or (sender or "").strip() or guid


def remember_chat_guid(
    cache: "OrderedDict[str, str]", chat_identifier: str, chat_guid: str, cap: int
) -> None:
    """Record an inbound ``chatIdentifier -> chatGuid`` mapping for outbound use.

    Upstream only ever populates this cache from ``_resolve_chat_guid``'s
    ``/api/v1/chat/query`` call, which is a single un-paginated page capped at
    100 chats. Past that cap an outbound reply addressed by handle can miss and
    fall through to ``_create_chat_for_handle`` — starting a *new* iMessage
    thread instead of replying in the existing one.

    Every inbound webhook already carries both fields authoritatively, so
    recording them here makes handle→GUID resolution exact and free for any
    conversation we've heard from, regardless of how many chats exist.
    """
    identifier = (chat_identifier or "").strip()
    guid = (chat_guid or "").strip()
    if not identifier or not guid or ";" in identifier:
        return
    cache[identifier] = guid
    cache.move_to_end(identifier)
    while len(cache) > cap:
        cache.popitem(last=False)


def seen_or_add(store: "OrderedDict[str, bool]", guid: str, cap: int) -> bool:
    """Return True if *guid* was already seen (caller should drop the message).

    Otherwise record it in the bounded-LRU *store* (evicting oldest past *cap*)
    and return False. An empty guid is never deduped (returns False).
    """
    if not guid:
        return False
    if guid in store:
        return True
    store[guid] = True
    while len(store) > cap:
        store.popitem(last=False)
    return False
