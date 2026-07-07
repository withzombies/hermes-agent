"""Outbound-email customizations (local fork patch).

Upstream sends bare-address From headers, a hardcoded "Hermes Agent" subject,
and no signature. These helpers add the operator-configurable pieces:

- ``default_subject()``  — EMAIL_DEFAULT_SUBJECT fallback (was hardcoded).
- ``from_header()``      — EMAIL_DISPLAY_NAME as an RFC 5322 name-addr From.
- ``apply_signature()``  — EMAIL_SIGNATURE appended below an RFC "-- " delimiter.
- ``lift_subject()``     — lift a leading "Subject: ..." body line into the
                           real header (outbound/standalone path only).

Called as single lines from plugins/platforms/email/adapter.py so that file
carries no fork logic of its own.
"""

import os
from email.utils import formataddr
from typing import Tuple


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
