"""Fork patches for shared-chat context (see LOCAL_PATCHES.md §3, §8).

Covers the two halves of the "Lucy loses the thread" bug:
  - group chats: participants were keyed into separate sessions, so a follow-up
    from Ryan couldn't see Valerie's exchange;
  - 1:1 chats: a BlueBubbles service flip (iMessage -> SMS) changed chat_id and
    silently started a new session mid-conversation.
"""

import os
import unittest
from collections import OrderedDict
from unittest.mock import patch

from gateway.local_patches.bluebubbles_gate import (
    remember_chat_guid,
    stable_chat_id,
)
from gateway.local_patches.principals import (
    always_prefix_speaker,
    display_name_for,
    whatsapp_display_name,
)

PRINCIPALS = "Ryan=+15173166753;Valerie=+19292569847|16759012753523@lid"


class TestStableChatId(unittest.TestCase):
    """DM sessions must survive an iMessage<->SMS service flip."""

    def test_imessage_and_sms_dm_collapse_to_one_session(self):
        imsg = stable_chat_id("iMessage;-;+15173166753", "+15173166753", "+15173166753", False)
        sms = stable_chat_id("SMS;-;+15173166753", "+15173166753", "+15173166753", False)
        self.assertEqual(imsg, sms)
        self.assertEqual(imsg, "+15173166753")

    def test_group_keeps_guid(self):
        """An MMS group and an iMessage group are genuinely different chats."""
        guid = "iMessage;+;chat9876543210"
        self.assertEqual(stable_chat_id(guid, "chat9876543210", "+15173166753", True), guid)

    def test_group_detected_from_guid_without_flag(self):
        guid = "iMessage;+;chat9876543210"
        self.assertEqual(stable_chat_id(guid, "chat9876543210", "+15173166753", False), guid)

    def test_dm_falls_back_to_sender_then_guid(self):
        self.assertEqual(stable_chat_id("iMessage;-;x", "", "+15551112222", False), "+15551112222")
        self.assertEqual(stable_chat_id("iMessage;-;x", "", "", False), "iMessage;-;x")

    def test_email_handle_dm(self):
        self.assertEqual(
            stable_chat_id("iMessage;-;a@b.com", "a@b.com", "a@b.com", False), "a@b.com"
        )


class TestRememberChatGuid(unittest.TestCase):
    """Inbound must warm the GUID cache so replies never need the 100-chat query."""

    def test_records_identifier_to_guid(self):
        cache: "OrderedDict[str, str]" = OrderedDict()
        remember_chat_guid(cache, "+15173166753", "iMessage;-;+15173166753", 10)
        self.assertEqual(cache["+15173166753"], "iMessage;-;+15173166753")

    def test_service_flip_updates_mapping(self):
        """After a flip, replies must target the CURRENT service's chat."""
        cache: "OrderedDict[str, str]" = OrderedDict()
        remember_chat_guid(cache, "+15173166753", "iMessage;-;+15173166753", 10)
        remember_chat_guid(cache, "+15173166753", "SMS;-;+15173166753", 10)
        self.assertEqual(cache["+15173166753"], "SMS;-;+15173166753")

    def test_ignores_blank_and_guid_shaped_identifiers(self):
        cache: "OrderedDict[str, str]" = OrderedDict()
        remember_chat_guid(cache, "", "iMessage;-;x", 10)
        remember_chat_guid(cache, "+1555", "", 10)
        remember_chat_guid(cache, "iMessage;-;+1555", "iMessage;-;+1555", 10)
        self.assertEqual(len(cache), 0)

    def test_evicts_oldest_past_cap(self):
        cache: "OrderedDict[str, str]" = OrderedDict()
        for i in range(5):
            remember_chat_guid(cache, f"+1555000000{i}", f"iMessage;-;{i}", 3)
        self.assertEqual(len(cache), 3)
        self.assertNotIn("+15550000000", cache)
        self.assertIn("+15550000004", cache)


class TestDisplayName(unittest.TestCase):
    """Shared sessions prefix each message with [user_name] — make it a real name."""

    def test_principal_handles_resolve_to_names(self):
        with patch.dict(os.environ, {"HERMES_PRINCIPAL_NAMES": PRINCIPALS}):
            self.assertEqual(display_name_for("+15173166753", fallback="+15173166753"), "Ryan")
            self.assertEqual(display_name_for("+19292569847", fallback="+19292569847"), "Valerie")

    def test_whatsapp_lid_resolves_via_alias_expansion(self):
        with patch.dict(os.environ, {"HERMES_PRINCIPAL_NAMES": PRINCIPALS}):
            self.assertEqual(whatsapp_display_name("16759012753523@lid", fallback="V"), "Valerie")

    def test_third_party_keeps_own_name(self):
        with patch.dict(os.environ, {"HERMES_PRINCIPAL_NAMES": PRINCIPALS}):
            self.assertEqual(display_name_for("+12125550000", fallback="Dana"), "Dana")

    def test_third_party_cannot_borrow_a_principal_name(self):
        """A self-chosen display name must not let an outsider render as [Ryan]."""
        with patch.dict(os.environ, {"HERMES_PRINCIPAL_NAMES": PRINCIPALS}):
            self.assertEqual(display_name_for("+12125550000", fallback="Ryan"), "+12125550000")
            self.assertEqual(display_name_for("+12125550000", fallback="  rYaN "), "+12125550000")

    def test_real_principal_wins_over_spoofed_fallback(self):
        with patch.dict(os.environ, {"HERMES_PRINCIPAL_NAMES": PRINCIPALS}):
            self.assertEqual(display_name_for("+19292569847", fallback="Ryan"), "Valerie")

    def test_no_principals_configured_is_passthrough(self):
        with patch.dict(os.environ, {"HERMES_PRINCIPAL_NAMES": "", "HERMES_PRINCIPAL_IDENTIFIERS": ""}):
            self.assertEqual(display_name_for("+12125550000", fallback="Dana"), "Dana")

    def test_falls_back_to_handle_without_fallback(self):
        with patch.dict(os.environ, {"HERMES_PRINCIPAL_NAMES": PRINCIPALS}):
            self.assertEqual(display_name_for("+12125550000"), "+12125550000")


class TestAlwaysPrefixSpeaker(unittest.TestCase):
    def test_defaults_off(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HERMES_ALWAYS_NAME_PREFIX", None)
            self.assertFalse(always_prefix_speaker())

    def test_truthy_values(self):
        for val in ("true", "1", "yes", "on", "TRUE"):
            with patch.dict(os.environ, {"HERMES_ALWAYS_NAME_PREFIX": val}):
                self.assertTrue(always_prefix_speaker(), val)

    def test_falsy_values(self):
        for val in ("false", "0", "no", ""):
            with patch.dict(os.environ, {"HERMES_ALWAYS_NAME_PREFIX": val}):
                self.assertFalse(always_prefix_speaker(), val)


if __name__ == "__main__":
    unittest.main()
