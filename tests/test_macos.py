"""Native safety ordering and selection tests; no global permissions needed."""
import sys
import unittest
from unittest.mock import Mock, patch

if sys.platform == "darwin":
    import Quartz as Q
    from lado.platforms import macos as M
    from lado.engine import Buffer, Detector, DoubleShift, MAX_SELECTION
    from lado.settings import Settings


@unittest.skipUnless(sys.platform == "darwin", "macOS adapter")
class MacSafetyTests(unittest.TestCase):
    def make_backend(self):
        b = M.MacBackend.__new__(M.MacBackend)
        b.settings = Settings()
        b.detector = Detector(b.settings)
        b.buffer = Buffer(b.detector)
        b.gesture = DoubleShift()
        b.sources = Mock()
        b.sources.secure.return_value = False
        b.sources.current.return_value = b.settings.english_source
        b.selection_undo = None
        b.epoch = 0
        b.disabled = False
        b.defer = Mock()
        b.notify = Mock()
        return b

    def test_blocked_states_never_read_event_characters(self):
        for state in ("secure", "permission", "paused", "excluded", "layout", "unsupported"):
            b = self.make_backend()
            b.refresh = Mock(return_value=M.Focus(state))
            event = Q.CGEventCreateKeyboardEvent(None, 0, True)
            with patch.object(Q, "CGEventKeyboardGetUnicodeString") as read:
                self.assertIs(b._handle(None, Q.kCGEventKeyDown, event), event)
                read.assert_not_called()

    def test_secure_event_input_precedes_accessibility_queries(self):
        b = self.make_backend()
        b.sources.secure.return_value = True
        with patch.object(M.A, "AXIsProcessTrusted") as trust, patch.object(M, "attr") as read:
            self.assertEqual(b.check_focus().state, "secure")
            trust.assert_not_called()
            read.assert_not_called()

    def test_tagged_events_never_reenter_detector(self):
        b = self.make_backend()
        b.refresh = Mock()
        event = Q.CGEventCreateKeyboardEvent(None, 0, True)
        Q.CGEventSetIntegerValueField(event, Q.kCGEventSourceUserData, M.TAG)
        b._handle(None, Q.kCGEventKeyDown, event)
        b.refresh.assert_not_called()

    def test_secure_transition_discards_context_and_undo(self):
        b = self.make_backend()
        b.buffer.feed("synthetic")
        b.buffer.manual()
        b.selection_undo = {"synthetic": True}
        b.focus = M.Focus("active", 123, "example", object(), "en")
        b.check_focus = Mock(return_value=M.Focus("secure"))
        b.last_state, b.tap = None, object()
        b.refresh()
        self.assertEqual(b.buffer.current, "")
        self.assertIsNone(b.buffer.last_edit)
        self.assertIsNone(b.selection_undo)

    def test_oversized_selection_is_not_read(self):
        b = self.make_backend()
        with patch.object(M, "selected_range", return_value=(0, MAX_SELECTION+1)), \
             patch.object(M, "attr") as read, patch.object(M.K, "NSBeep"):
            self.assertTrue(b._selection(None, M.Focus("active", element=object())))
            read.assert_not_called()

    def test_selection_is_reversible_without_clipboard(self):
        b = self.make_backend()
        element = object()
        focus = M.Focus("active", element=element)
        b._type = Mock()
        with patch.object(M, "selected_range", return_value=(0, 6)), \
             patch.object(M, "attr", return_value="ghbdtn"), \
             patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0,False)):
            b._selection(None, focus)
        self.assertEqual(b._type.call_args.args[1], "привет")
        with patch.object(M, "selected_range", return_value=(0, 6)), \
             patch.object(M, "attr", return_value="привет"), \
             patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0,False)):
            b._selection(None, focus)
        self.assertEqual(b._type.call_args.args[1], "ghbdtn")

    def test_native_sources_and_layout_data(self):
        sources = M.InputSources()
        self.assertIsInstance(sources.current(), str)
        available = sources.all()
        en = next((s["id"] for s in available if s["language"] == "en"), None)
        ru = next((s["id"] for s in available if s["language"] == "ru"), None)
        if en and ru:
            converter = sources.converter(en, ru)
            self.assertIsNotNone(converter)
            self.assertEqual(converter.convert("ghbdtn"), "привет")
            self.assertEqual(converter.convert("GHBDTN"), "ПРИВЕТ")

    def test_unicode_payload_is_on_both_key_events(self):
        b = self.make_backend()
        events = list(b._unicode_events("привет😀"))
        self.assertEqual(len(events), 14)
        for i, char in enumerate("привет😀"):
            for event in events[2*i:2*i+2]:
                self.assertEqual(Q.CGEventKeyboardGetUnicodeString(event,8,None,None)[1], char)
                self.assertEqual(Q.CGEventGetFlags(event), 0)

    def test_payload_failure_happens_before_deletion(self):
        from lado.engine import Edit
        b = self.make_backend()
        b._key = Mock()
        b._unicode_events = Mock(side_effect=ValueError("synthetic failure"))
        with self.assertRaises(ValueError):
            b._replace_tail(None, Edit("ghbdtn", "привет", "ru"))
        b._key.assert_not_called()
