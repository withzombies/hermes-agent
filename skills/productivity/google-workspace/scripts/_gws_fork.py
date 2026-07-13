"""Fork-owned helpers for the google-workspace skill.

``google_api.py`` is upstream-owned. Per this fork's single-line-hook rule, all
fork logic lives here and ``google_api.py`` carries only ``# fork``-tagged
call-ins that import from this module. A brand-new sibling never conflicts on an
upstream rebase.

Keep this file free of principal-specific data: calendar aliases are read from
``~/.hermes/calendar_aliases.json`` (which is NOT committed), the same way the
OAuth token lives in HERMES_HOME. That mirrors how the fork keeps principal
identifiers out of pushed code.
"""

import json
import os
from email.utils import getaddresses

from _hermes_home import get_hermes_home


# --- Gmail: Reply All -------------------------------------------------------

def reply_all_recipients(headers, self_address, extra_to="", extra_cc="", reply_all=True):
    """Compute (To, Cc) header strings for a reply.

    Reply All (the default) preserves every recipient of the original message:
    the original sender plus everyone already on To go on To, everyone on Cc
    stays on Cc. Our own address is always dropped so we never reply to
    ourselves, and addresses are de-duplicated case-insensitively (first-seen
    order kept). Any --to/--cc values are added on top. With reply_all=False
    only the original sender (plus explicit --to/--cc) is used.
    """
    self_norm = (self_address or "").strip().lower()
    seen = set()
    to_list = []
    cc_list = []

    def add(target, raw):
        for _name, addr in getaddresses([raw or ""]):
            norm = addr.strip().lower()
            if not norm or norm == self_norm or norm in seen:
                continue
            seen.add(norm)
            target.append(addr.strip())

    add(to_list, headers.get("from", ""))
    if reply_all:
        add(to_list, headers.get("to", ""))
    add(to_list, extra_to)
    if reply_all:
        add(cc_list, headers.get("cc", ""))
    add(cc_list, extra_cc)
    return ", ".join(to_list), ", ".join(cc_list)


# --- Calendar: alias resolution + update patch ------------------------------

def _calendar_aliases():
    """Return {alias: calendarId} from ~/.hermes/calendar_aliases.json.

    Kept out of the repo so no principal calendar IDs are committed. Missing or
    malformed file -> {} (aliases simply don't resolve, real IDs still work).
    """
    try:
        path = os.path.join(str(get_hermes_home()), "calendar_aliases.json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k).strip().lower(): str(v).strip()
                for k, v in data.items() if k and v}
    except (OSError, ValueError):
        return {}


def resolve_calendar(calendar):
    """Map a friendly calendar alias (shared/ryan/lucy/…) to its real ID.

    Anything not an alias (a real calendar ID or 'primary') passes through
    unchanged, so this only ever helps and never blocks a valid ID even when the
    aliases file is absent.
    """
    return _calendar_aliases().get((calendar or "").strip().lower(), calendar)


def build_update_patch(summary="", start="", end="", location="", description=""):
    """Assemble a Calendar events.patch body from only the fields provided.

    Empty dict means the caller passed nothing to change.
    """
    patch = {}
    if summary:
        patch["summary"] = summary
    if start:
        patch["start"] = {"dateTime": start}
    if end:
        patch["end"] = {"dateTime": end}
    if location:
        patch["location"] = location
    if description:
        patch["description"] = description
    return patch
