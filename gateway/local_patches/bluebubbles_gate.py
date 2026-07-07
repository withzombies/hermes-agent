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
