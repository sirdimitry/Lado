"""Native safety ordering and selection tests; no global permissions needed."""
import sys
from collections import deque
from time import monotonic
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
        b.test_bundle = None
        b.detector = Detector(b.settings)
        b.buffer = Buffer(b.detector)
        b.gesture = DoubleShift()
        b.sources = Mock()
        b.sources.secure.return_value = False
        b.sources.current.return_value = b.settings.english_source
        b.selection_undo = None
        b.epoch = 0
        b.disabled = False
        b.faulted = False
        b.events = deque(maxlen=16)
        b.drain_pending = False
        b.focus_checked = monotonic()
        b.input_serial = 0
        b.edit_serial = 0
        b.edit_deadline = monotonic() + 1
        b._confirm_target = Mock(return_value=True)
        b.defer = Mock()
        b.notify = Mock()
        b.focus = M.Focus("active", element=object())
        return b

    def test_blocked_states_never_read_event_characters(self):
        for state in ("secure", "permission", "paused", "excluded", "layout", "unsupported"):
            b = self.make_backend()
            b.focus = M.Focus(state)
            b.refresh = Mock(return_value=b.focus)
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

    def test_compatibility_mode_excludes_other_apps_before_field_reads(self):
        b = self.make_backend()
        b.test_bundle = "com.sirdimitry.lado-testpad"
        foreground = Mock()
        foreground.processIdentifier.return_value = 54321
        foreground.bundleIdentifier.return_value = "example.other-app"
        workspace = Mock()
        workspace.frontmostApplication.return_value = foreground
        with patch.object(M.A, "AXIsProcessTrusted", return_value=True), \
             patch.object(Q, "CGPreflightListenEventAccess", return_value=True), \
             patch.object(M.K, "NSWorkspace", Mock(sharedWorkspace=Mock(return_value=workspace))), \
             patch.object(M, "attr") as read:
            self.assertEqual(b.check_focus().state, "excluded")
        read.assert_not_called()

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
             patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0,True)), \
             patch.object(M.A, "AXUIElementSetAttributeValue", return_value=0) as write:
            b._selection(None, focus)
        self.assertEqual(write.call_args.args[2], "привет")
        with patch.object(M, "selected_range", return_value=(0, 6)), \
             patch.object(M, "attr", return_value="привет"), \
             patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0,True)), \
             patch.object(M.A, "AXUIElementSetAttributeValue", return_value=0) as write:
            b._selection(None, focus)
        self.assertEqual(write.call_args.args[2], "ghbdtn")

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

    def test_adapter_contains_only_one_tagged_synthetic_path(self):
        from pathlib import Path
        source = Path(M.__file__).read_text()
        self.assertNotIn("CGEventTapPostEvent", source)
        # The only CGEventPost call site is the Chromium fallback, and every
        # event it builds is tagged with TAG so our own tap ignores it.
        self.assertEqual(source.count("CGEventPost("), 1)
        self.assertIn("Q.CGEventSetIntegerValueField(event, Q.kCGEventSourceUserData, TAG)", source)
        self.assertIn("def _synthetic_replace", source)

    def test_unsupported_replacement_never_deletes(self):
        from lado.engine import Edit
        b = self.make_backend()
        b._post = Mock()
        with patch.object(M, "selected_range", return_value=(6,0)), \
             patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0,False)), \
             patch.object(M.A, "AXUIElementSetAttributeValue") as write:
            self.assertFalse(b._replace_tail(None, Edit("ghbdtn", "привет", "ru")))
        write.assert_not_called()
        b._post.assert_not_called()

    def test_tail_span_is_validated_before_replacement(self):
        from lado.engine import Edit
        b = self.make_backend()
        with patch.object(M, "selected_range", return_value=(6,0)), \
             patch.object(M, "set_range", return_value=True) as select, \
             patch.object(M, "attr", return_value="other!"), \
             patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0,True)), \
             patch.object(M.A, "AXUIElementSetAttributeValue") as write:
            self.assertFalse(b._replace_tail(None, Edit("ghbdtn", "привет", "ru")))
        write.assert_not_called()
        self.assertEqual(select.call_args.args[1], (6,0))

    def test_atomic_word_replacement_includes_pending_separator(self):
        from lado.engine import Edit
        b = self.make_backend()
        b._switch = Mock()
        element = b.focus.element
        with patch.object(M, "selected_range", return_value=(6,0)), \
             patch.object(M, "set_range", return_value=True) as select, \
             patch.object(M, "attr", return_value="ghbdtn"), \
             patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0,True)), \
             patch.object(b, "_write_selected", return_value=True) as write:
            self.assertTrue(b._replace_tail(None, Edit("ghbdtn ", "привет ", "ru"), " "))
        write.assert_called_once_with(element, "привет ", 0, "ghbdtn")
        self.assertEqual(select.call_args.args[1], (7,0))
        b._switch.assert_called_once_with("ru")

    def value_field(self, value):
        """Attribute store that behaves like a writable AXValue editor."""
        store = {"AXValue": value, "AXNumberOfCharacters": len(value)}
        read = lambda element, name: store.get(name)
        write = lambda element, name, new: store.__setitem__(name, new) or 0
        return store, read, write

    def test_legacy_value_fallback_cannot_replace_tail(self):
        from lado.engine import Edit
        b = self.make_backend()
        b.settings.value_fallback = True
        b.focus = M.Focus("active", element=object(), mode="value")
        b._switch = Mock()
        store, read, write = self.value_field("hello ghbdtn")
        with patch.object(M, "selected_range", return_value=(12, 0)), \
             patch.object(M, "attr", side_effect=read), \
             patch.object(M, "set_range") as select, \
             patch.object(M.A, "AXUIElementIsAttributeSettable", side_effect=lambda e,n,_: (0,n == "AXValue")), \
             patch.object(M.A, "AXUIElementSetAttributeValue", side_effect=write) as write_mock:
            self.assertFalse(b._replace_tail(None, Edit("ghbdtn", "привет", "ru"), explicit=True))
        self.assertEqual(store["AXValue"], "hello ghbdtn")
        write_mock.assert_not_called()
        b._switch.assert_not_called()

    def test_value_fallback_reads_nothing_beyond_cap(self):
        from lado.engine import Edit
        b = self.make_backend()
        b.settings.value_fallback = True
        b.focus = M.Focus("active", element=object(), mode="value")
        store = {"AXValue": "x" * (M.MAX_VALUE_UNITS + 1),
                 "AXNumberOfCharacters": M.MAX_VALUE_UNITS + 1}
        with patch.object(M, "selected_range", return_value=(12, 0)), \
             patch.object(M, "attr", side_effect=lambda e, n: store.get(n)) as read, \
             patch.object(M.A, "AXUIElementIsAttributeSettable", side_effect=lambda e,n,_: (0,n == "AXValue")), \
             patch.object(M.A, "AXUIElementSetAttributeValue") as write:
            self.assertFalse(b._replace_tail(None, Edit("x", "y", "ru"), explicit=True))
        write.assert_not_called()
        names = [c.args[1] for c in read.call_args_list]
        self.assertNotIn("AXValue", names)

    def test_value_fallback_refuses_non_tail_word(self):
        from lado.engine import Edit
        b = self.make_backend()
        b.settings.value_fallback = True
        b.focus = M.Focus("active", element=object(), mode="value")
        store, read, write = self.value_field("ghbdtnx and more")
        with patch.object(M, "selected_range", return_value=(12, 0)), \
             patch.object(M, "attr", side_effect=read), \
             patch.object(M.A, "AXUIElementIsAttributeSettable", side_effect=lambda e,n,_: (0,n == "AXValue")), \
             patch.object(M.A, "AXUIElementSetAttributeValue", side_effect=write) as write_mock:
            self.assertFalse(b._replace_tail(None, Edit("ghbdtn", "привет", "ru"), explicit=True))
        write_mock.assert_not_called()
        self.assertEqual(store["AXValue"], "ghbdtnx and more")

    def test_value_fallback_is_skipped_when_disabled(self):
        from lado.engine import Edit
        b = self.make_backend()
        b.settings.value_fallback = False
        b.focus = M.Focus("active", element=object(), mode="value")
        with patch.object(M, "selected_range", return_value=None), \
             patch.object(M, "attr") as read, \
             patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0,True)), \
             patch.object(M.A, "AXUIElementSetAttributeValue") as write:
            self.assertFalse(b._replace_tail(None, Edit("ghbdtn", "привет", "ru")))
        write.assert_not_called()
        read.assert_not_called()

    def test_legacy_value_fallback_cannot_rewrite_selection(self):
        b = self.make_backend()
        b.settings.value_fallback = True
        element = object()
        focus = M.Focus("active", element=element)
        store, read, write = self.value_field("hello ghbdtn world")
        selected = lambda e, n: "ghbdtn" if n == "AXSelectedText" else read(e, n)
        with patch.object(M, "selected_range", return_value=(6, 6)), \
             patch.object(M, "attr", side_effect=selected), \
             patch.object(M.A, "AXUIElementIsAttributeSettable",
                          side_effect=lambda e, n, _: (0, n == "AXValue")), \
             patch.object(M.A, "AXUIElementSetAttributeValue", side_effect=write) as write_mock:
            self.assertTrue(b._selection(None, focus))
        self.assertEqual(store["AXValue"], "hello ghbdtn world")
        write_mock.assert_not_called()
        self.assertIsNone(b.selection_undo)

    def test_value_selection_refuses_mismatched_span(self):
        b = self.make_backend()
        b.settings.value_fallback = True
        element = object()
        store, read, write = self.value_field("hello xxxxxx world")
        selected = lambda e, n: "ghbdtn" if n == "AXSelectedText" else read(e, n)
        with patch.object(M, "selected_range", return_value=(6, 6)), \
             patch.object(M, "attr", side_effect=selected), \
             patch.object(M.A, "AXUIElementIsAttributeSettable",
                          side_effect=lambda e, n, _: (0, n == "AXValue")), \
             patch.object(M.A, "AXUIElementSetAttributeValue", side_effect=write) as write_mock, \
             patch.object(M.K, "NSBeep"):
            self.assertTrue(b._selection(None, M.Focus("active", element=element)))
        write_mock.assert_not_called()
        self.assertEqual(store["AXValue"], "hello xxxxxx world")
