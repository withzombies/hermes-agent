"""Quiet-mode gate (local fork patch).

``is_quiet()`` reports whether the operator has opted out of gateway
system/status chatter in chat. Wired at the two delivery chokepoints in
gateway/run.py (``_prepare_gateway_status_message`` and
``_deliver_platform_notice``) plus the compression-abort / aux-fallback /
inactivity direct sends. Config bridges ``gateway.quiet_system_messages`` →
``HERMES_QUIET_SYSTEM_MESSAGES`` at startup.
"""

import os


def is_quiet() -> bool:
    """True when the operator has opted out of gateway system/status messages.

    Suppresses operational notices and agent status/lifecycle chatter in chat
    (compaction, retries, provider errors, home-channel prompt, credit bands).
    Does NOT touch interactive prompts (approval/clarify), the busy-ack/heartbeat,
    or real task results — those take different delivery paths.
    """
    return os.getenv("HERMES_QUIET_SYSTEM_MESSAGES", "").strip().lower() in {
        "1", "true", "yes", "on",
    }
