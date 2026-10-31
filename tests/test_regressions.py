"""Regressions from the 2026-10-30 review. Native services are mocked."""
import sys
import threading
from collections import deque
from time import monotonic
import unittest
from unittest.mock import Mock, patch

if sys.platform == "darwin":
    from lado.platforms import macos as M
    from lado.engine import Buffer, Detector, DoubleShift, Edit
    from lado.settings import Settings


@unittest.skipUnless(sys.platform == "darwin", "macOS regressions")
class RegressionTests(unittest.TestCase):
    def backend(self):
        b = M.MacBackend.__new__(M.MacBackend)
        b.settings = Settings()
        b.buffer = Buffer(Detector(b.settings))
        b.gesture = DoubleShift()
        b.events = deque(maxlen=16)
        b.epoch = 0
        b.selection_undo = None
        b.last_state = None
        b.tap = object()
        b.faulted = b.disabled = False
        b.focus_required = 0.0
        b.notify = Mock()
        b._probe_lock = threading.Lock()
        b._probe_at = monotonic()
        b._focus_generation = 0
        b._probe_focus = None
        b._probe_stop = threading.Event()
        b._probe_wake = Mock()
        b._workspace_token = None
        b._can_edit = Mock(return_value=True)
        b._edit_target_is_text = Mock(return_value=True)
        b._confirm_target = Mock(return_value=True)
        b.sources = Mock()
        b.sources.secure.return_value = False
        b.input_serial = 1
        b.drain_pending = False
        b.defer = Mock()
        return b

    def queue_event(self, b, kind):
        event = M.Q.CGEventCreateKeyboardEvent(None, 56, True)
        b.events.append((monotonic(), b.epoch, b.focus, kind, event))
        b._process = Mock()

    def test_webkit_nbsp_keeps_exact_word_and_separator(self):
        self.assertEqual(M.observed_replacement("ghbdtn\u00a0", "ghbdtn ", "привет "), "привет\u00a0")
        self.assertEqual(M.observed_replacement("ghbdtn ", "ghbdtn ", "привет "), "привет ")

    def test_webkit_uses_exact_marker_range_operation(self):
        b = self.backend()
        marker, element = object(), object()
        with patch.object(M, "attr", return_value=marker), patch.object(M, "set_timeout"), \
             patch.object(M.A, "AXUIElementCopyParameterizedAttributeValue", return_value=(0, ["привет"])) as operation, \
             patch.object(M.A, "AXUIElementSetAttributeValue") as setter:
            self.assertTrue(b._write_selected(element, "привет"))
        args = operation.call_args.args
        self.assertEqual(args[1], "AXTextOperation")
        self.assertEqual(args[2]["AXTextOperationMarkerRanges"], [marker])
        self.assertFalse(args[2]["AXTextOperationSmartReplace"])
        setter.assert_not_called()

    def test_ambiguous_marker_write_never_retries_with_other_setter(self):
        b = self.backend()
        with patch.object(M, "attr", return_value=object()), patch.object(M, "set_timeout"), \
             patch.object(M.A, "AXUIElementCopyParameterizedAttributeValue", return_value=(-25204, None)), \
             patch.object(M.A, "AXUIElementSetAttributeValue") as setter:
            self.assertFalse(b._write_selected(object(), "привет"))
        setter.assert_not_called()

    def test_webkit_space_tolerance_does_not_relax_word_validation(self):
        for actual in ("ghbdtm\u00a0", "Ghbdtn\u00a0", "ghbdtn\t", "ghbdtn\u202f", None):
            self.assertIsNone(M.observed_replacement(actual, "ghbdtn ", "привет "))

    def test_nbsp_range_replacement_preserves_webkit_separator(self):
        b = self.backend()
        b._switch = Mock()
        element = object()
        with patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0, True)), \
             patch.object(M, "set_range", return_value=True), \
             patch.object(M, "attr", return_value="ghbdtn\u00a0"), \
             patch.object(M.A, "AXUIElementSetAttributeValue", return_value=0) as write:
            self.assertTrue(b._range_replacement(element, Edit("ghbdtn ", "привет ", "ru"), "ghbdtn ", (7, 0)))
        write.assert_called_once_with(element, "AXSelectedText", "привет\u00a0")

    def test_first_shift_is_not_lost_when_only_layout_changed(self):
        b = self.backend()
        element = object()
        b.focus = M.Focus("active", 123, "example", element, "ru", "AXTextArea")
        b._probe_focus = M.Focus("active", 123, "example", element, "en", "AXTextArea")
        self.queue_event(b, M.Q.kCGEventFlagsChanged)
        b.drain_events()
        b._process.assert_called_once()

    def test_character_from_old_layout_is_still_discarded(self):
        b = self.backend()
        element = object()
        b.focus = M.Focus("active", 123, "example", element, "ru", "AXTextArea")
        b._probe_focus = M.Focus("active", 123, "example", element, "en", "AXTextArea")
        self.queue_event(b, M.Q.kCGEventKeyDown)
        b.drain_events()
        b._process.assert_not_called()

    def test_brief_probe_transition_defers_instead_of_losing_first_event(self):
        b = self.backend()
        b.focus = b._probe_focus = M.Focus("active", 123, "example", object(), "en", "AXTextArea")
        b._probe_at = monotonic() - 0.1
        b.focus_required = monotonic()
        self.queue_event(b, M.Q.kCGEventFlagsChanged)
        b.drain_events()
        b._process.assert_not_called()
        self.assertEqual(len(b.events), 1)
        self.assertTrue(b.drain_pending)
        b._probe_at = monotonic()
        b.drain_events()
        b._process.assert_called_once()

    def test_two_fields_of_same_type_clear_context(self):
        b = self.backend()
        b.focus = M.Focus("active", 123, "example", object(), "en", "AXTextArea")
        b._probe_focus = M.Focus("active", 123, "example", object(), "en", "AXTextArea")
        b.buffer.feed("ghbdtn")
        with patch.object(M.F, "CFEqual", return_value=False):
            b.refresh()
        self.assertEqual(b.buffer.current, "")

    def test_equal_ax_wrappers_keep_context(self):
        b = self.backend()
        b.focus = M.Focus("active", 123, "example", object(), "en", "AXTextArea")
        b._probe_focus = M.Focus("active", 123, "example", object(), "en", "AXTextArea")
        b.buffer.feed("ghbdtn")
        with patch.object(M.F, "CFEqual", return_value=True):
            b.refresh()
        self.assertEqual(b.buffer.current, "ghbdtn")

    def test_old_probe_is_never_active(self):
        b = self.backend()
        b.focus = b._probe_focus = M.Focus("active", 123, "example", object(), "en", "AXTextArea")
        b._probe_at = monotonic() - 2
        self.assertEqual(b.refresh().reason, "probe-stale")

    def test_probe_from_before_focus_invalidation_is_rejected(self):
        b = self.backend()
        b.focus = b._probe_focus = M.Focus("active", 123, "example", object(), "en", "AXTextArea")
        b.focus_required = b._probe_at + 0.1
        self.assertEqual(b.refresh().reason, "probe-stale")

    def test_inflight_probe_cannot_publish_after_focus_change(self):
        b = self.backend()
        def checking():
            b._focus_generation += 1
            return M.Focus("active", 123, "old", object())
        b.check_focus = Mock(side_effect=checking)
        b._probe_wake.wait.side_effect = lambda _: b._probe_stop.set()
        b._probe_loop()
        self.assertIsNone(b._probe_focus)

    def test_probe_timestamp_includes_time_spent_in_rpc(self):
        b = self.backend()
        b.check_focus = Mock(return_value=M.Focus("unsupported"))
        b._probe_wake.wait.side_effect = lambda _: b._probe_stop.set()
        with patch.object(M, "monotonic", side_effect=[100.0, 100.6]):
            b._probe_loop()
        self.assertEqual(b._probe_at, 100.0)

    def test_stopping_slow_probe_does_not_orphan_worker(self):
        b = self.backend()
        worker = Mock()
        worker.is_alive.return_value = True
        b._probe_thread = worker
        b.stop_probe()
        self.assertIs(b._probe_thread, worker)
        self.assertTrue(b._probe_stop.is_set())
        b.start_probe()
        self.assertIs(b._probe_thread, worker)
        self.assertTrue(b._probe_stop.is_set())

    def test_whole_field_read_is_disabled_by_default(self):
        self.assertFalse(Settings().value_fallback)

    def test_automatic_correction_never_uses_whole_field_fallback(self):
        b = self.backend()
        b.settings.value_fallback = True
        b.focus = M.Focus("active", element=object())
        b._range_replacement = Mock(return_value=False)
        b._value_replacement = Mock()
        with patch.object(M, "selected_range", return_value=(6, 0)):
            self.assertFalse(b._replace_tail(None, Edit("ghbdtn", "привет", "ru")))
        b._value_replacement.assert_not_called()

    def selection_case(self, value, span, before="aa", after="яя", changed=None):
        b = self.backend()
        b.settings.value_fallback = True
        store = {"AXValue": value, "AXNumberOfCharacters": M.utf16_units(value)}
        reads = [0]
        def read(_, name):
            if name == "AXValue":
                reads[0] += 1
                if changed and reads[0] > 1:
                    return changed
            return store.get(name)
        def write(_, name, text):
            store[name] = text
            return 0
        with patch.object(M, "attr", side_effect=read), \
             patch.object(M, "selected_range", return_value=span), \
             patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0, True)), \
             patch.object(M.A, "AXUIElementSetAttributeValue", side_effect=write) as setter:
            result = b._value_selection(object(), span, before, after)
        return result, store["AXValue"], setter.call_count

    def test_emoji_before_repeated_selected_letters_uses_utf16_offsets(self):
        result, text, calls = self.selection_case("😀aaa", (2, 2))
        self.assertTrue(result)
        self.assertEqual(text, "😀яяa")
        self.assertEqual(calls, 1)

    def test_range_splitting_surrogate_pair_is_rejected(self):
        result, text, calls = self.selection_case("😀aaa", (1, 2))
        self.assertFalse(result)
        self.assertEqual(text, "😀aaa")
        self.assertEqual(calls, 0)

    def test_concurrent_whole_field_change_cancels_replacement(self):
        result, text, calls = self.selection_case("😀aaa", (2, 2), changed="😀aaa NEW")
        self.assertFalse(result)
        self.assertEqual(calls, 0)

    def test_unknown_caret_never_allows_whole_field_word_replacement(self):
        b = self.backend()
        with patch.object(M, "attr") as read:
            self.assertFalse(b._value_replacement(object(), Edit("a", "ф", "ru"), "a", None))
        read.assert_not_called()

    def test_expired_ax_budget_does_not_query_other_app(self):
        with patch.object(M.A, "AXUIElementCopyAttributeValue") as read:
            with self.assertRaises(M.AXDeadlineExceeded), M.ax_deadline(monotonic() - 1):
                M.attr(object(), "AXFocusedUIElement")
        read.assert_not_called()

    def test_changed_edit_target_is_rejected_even_in_same_app(self):
        b = self.backend()
        old, new = object(), object()
        b.focus = M.Focus("active", 123, "example", old, "en", "AXTextArea")
        b.check_focus = Mock(return_value=M.Focus("active", 123, "example", new, "en", "AXTextArea"))
        with patch.object(M.F, "CFEqual", return_value=False):
            self.assertFalse(M.MacBackend._confirm_target(b, old))
