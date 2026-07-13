"""Outbound-email customizations (local fork patch).

Upstream sends bare-address From headers, a hardcoded "Hermes Agent" subject,
and no signature. These helpers add the operator-configurable pieces:

- ``default_subject()``  — EMAIL_DEFAULT_SUBJECT fallback (was hardcoded).
- ``from_header()``      — EMAIL_DISPLAY_NAME as an RFC 5322 name-addr From.
- ``apply_signature()``  — EMAIL_SIGNATURE appended below an RFC "-- " delimiter.
- ``lift_subject()``     — lift a leading "Subject: ..." body line into the
  real header (outbound/standalone path only).
- ``reply_all_context()`` / ``apply_reply_all_headers()`` — preserve an
  inbound email's To/Cc recipients on a true Reply All, excluding the agent.

Called as single lines from plugins/platforms/email/adapter.py so that file
carries no fork logic of its own.
"""

import os
from email.utils import formataddr, getaddresses
from typing import Dict, Tuple


def reply_all_context(
    to_header: str,
    cc_header: str,
    sender_address: str,
    agent_address: str,
) -> Dict[str, str]:
    """Build safe Reply All headers from an inbound message's To/Cc fields.

    The direct sender remains the primary recipient. Existing To recipients
    remain To, existing Cc recipients remain Cc, and the agent's own address
    is removed. Addresses are deduplicated case-insensitively while retaining
    first-seen order.
    """
    agent = agent_address.strip().lower()
    sender = sender_address.strip().lower()
    to_addresses = []
    cc_addresses = []
    seen = set()

    def add(target, address):
        normalized = address.strip().lower()
        if not normalized or normalized in {agent} or normalized in seen:
            return
        seen.add(normalized)
        target.append(address.strip())

    add(to_addresses, sender_address)
    for _name, address in getaddresses([to_header or ""]):
        add(to_addresses, address)
    for _name, address in getaddresses([cc_header or ""]):
        add(cc_addresses, address)

    # A sender that was also listed in Cc belongs in To for the reply.
    return {
        "to": ", ".join(to_addresses) or sender_address,
        "cc": ", ".join(cc_addresses),
    }


def apply_reply_all_headers(message, context: Dict[str, str], fallback_to: str) -> None:
    """Replace an outbound message's recipients with stored Reply All headers."""
    reply_to = context.get("to") or fallback_to
    if message.get("To"):
        message.replace_header("To", reply_to)
    else:
        message["To"] = reply_to

    cc = context.get("cc", "")
    if cc:
        if message.get("Cc"):
            message.replace_header("Cc", cc)
        else:
            message["Cc"] = cc


def default_subject() -> str:
    """Configurable fallback subject (was the hardcoded ``"Hermes Agent"``)."""
    return os.getenv("EMAIL_DEFAULT_SUBJECT", "Hermes Agent")


def from_header(address: str) -> str:
    """From header with an optional friendly display name (EMAIL_DISPLAY_NAME).

    Gmail and most providers do not stamp the account display name on SMTP
    sends — the client must supply the RFC 5322 name-addr itself. Unset →
    the bare address, unchanged behavior.
    """
    display_name = os.getenv("EMAIL_DISPLAY_NAME", "").strip()
    return formataddr((display_name, address)) if display_name else address


def apply_signature(body: str) -> str:
    """Append EMAIL_SIGNATURE to an outbound body, RFC-style.

    The env value may contain literal ``\\n`` escapes for multi-line
    signatures. The "-- " delimiter is added here so clients can fold the
    block. No-op when unset or when the signature already appears in the
    body (e.g. the model copied it in).
    """
    sig = os.getenv("EMAIL_SIGNATURE", "")
    if not sig:
        return body
    sig = sig.replace("\\n", "\n").strip()
    if not sig or sig in body:
        return body
    return body.rstrip() + "\n\n-- \n" + sig + "\n"


def lift_subject(message: str) -> Tuple[str, str]:
    """Split a leading ``Subject: ...`` line off an outbound message.

    Models naturally write "Subject: ..." as the first body line; lift it into
    the real header and return ``(subject, body)``. Without one, the subject is
    ``default_subject()`` and the body is the message unchanged.
    """
    subject = default_subject()
    body = message
    if message.lstrip().lower().startswith("subject:"):
        first_line, _, rest = message.lstrip().partition("\n")
        candidate = first_line.split(":", 1)[1].strip()
        if candidate:
            subject = candidate
            body = rest.lstrip("\n")
    return subject, body
