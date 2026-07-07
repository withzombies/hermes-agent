"""Warm busy-ack copy (local fork patch).

Rewords the gateway's "you messaged me while I'm busy" acknowledgements into
Lucy's warm, jargon-free voice. The technical status detail (iteration/tool/
elapsed) is computed by the caller and kept in logs only — it is passed in here
solely so the compression branch can surface it, matching prior behavior.
"""

from typing import Optional


def busy_ack_text(
    *,
    is_steer_mode: bool,
    is_queue_mode: bool,
    demoted_for_subagents: bool,
    demoted_for_compression: bool,
    status_detail: str = "",
) -> str:
    """Return the warm busy-ack message for the given queue/steer state."""
    if is_steer_mode:
        return (
            "⏩ Slipping that into the current run — it'll land right after "
            "the next step."
        )
    if is_queue_mode and demoted_for_subagents:
        # #30170 — explain the demotion so the user knows their follow-up didn't
        # accidentally kill the subagent and discovers `/stop` as the escape hatch.
        return (
            "⏳ Still working on something — your message is queued for when "
            "it finishes (use /stop to cancel everything)."
        )
    if is_queue_mode and demoted_for_compression:
        return (
            f"⏳ Compressing context{status_detail} — your message is queued for "
            f"when it finishes (use /stop to cancel everything)."
        )
    if is_queue_mode:
        return "⏳ Got your message — I'll reply as soon as I wrap up what I'm on."
    return "⚡ One sec — folding that into what I'm doing now."
