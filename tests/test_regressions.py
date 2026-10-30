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
        return b

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
