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
        element, marker = object(), object()
        b.focus = M.Focus("active", element=element)
        with patch.object(M, "attr", side_effect=lambda e, n: marker if n == "AXSelectedTextMarkerRange" else "привет"), \
             patch.object(M, "set_timeout"), \
             patch.object(M, "set_range", return_value=True), \
             patch.object(M.A, "AXUIElementCopyParameterizedAttributeValue", return_value=(0, ["привет"])) as operation, \
             patch.object(M.A, "AXUIElementSetAttributeValue") as setter:
            self.assertTrue(b._write_selected(element, "привет", 0))
        args = operation.call_args.args
        self.assertEqual(args[1], "AXTextOperation")
        self.assertEqual(args[2]["AXTextOperationMarkerRanges"], [marker])
        self.assertEqual(args[2]["AXTextOperationType"], M.TEXT_OPERATION_REPLACE_PRESERVE_CASE)
        self.assertEqual(args[2]["AXTextOperationReplacementString"], "привет")
        self.assertFalse(args[2]["AXTextOperationSmartReplace"])
        setter.assert_not_called()

    def test_ax_success_without_a_real_change_is_rejected(self):
        # Reproduces the rc.6 report: AX returns success and the replacement
        # string, but the field still contains the old word.
        b = self.backend()
        element, marker = object(), object()
        b.focus = M.Focus("active", element=element)
        with patch.object(M, "attr", side_effect=lambda e, n: marker if n == "AXSelectedTextMarkerRange" else "ghbdtn"), \
             patch.object(M, "set_timeout"), \
             patch.object(M, "set_range", return_value=True), \
             patch.object(M.A, "AXUIElementCopyParameterizedAttributeValue", return_value=(0, ["привет"])), \
             patch.object(M.A, "AXUIElementSetAttributeValue") as setter:
            self.assertFalse(b._write_selected(element, "привет", 0))
        self.assertEqual(b.last_replacement, "text-operation-unverified")
        setter.assert_not_called()

    def test_ignored_operation_type_never_retries_a_second_edit(self):
        # On an engine that does not know the strict type, AXTextOperation
        # degrades to select and returns the old text. Do not run another
        # operation type blindly; the ordinary setter is tried once and the
        # span is read back.
        b = self.backend()
        element, marker = object(), object()
        b.focus = M.Focus("active", element=element)
        with patch.object(M, "attr", side_effect=lambda e, n: marker if n == "AXSelectedTextMarkerRange" else "ghbdtn"), \
             patch.object(M, "set_timeout"), \
             patch.object(M, "set_range", return_value=True), \
             patch.object(M.A, "AXUIElementCopyParameterizedAttributeValue", return_value=(0, ["ghbdtn"])) as operation, \
             patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0, True)), \
             patch.object(M.A, "AXUIElementSetAttributeValue", return_value=0) as setter:
            self.assertFalse(b._write_selected(element, "привет", 0))
        self.assertEqual(operation.call_count, 1)
        self.assertEqual([c.args[1] for c in setter.call_args_list], ["AXSelectedText"])
        self.assertEqual(b.last_replacement, "text-operation-ignored/selected-text-unverified")

    def test_ambiguous_marker_write_never_retries_with_other_setter(self):
        b = self.backend()
        with patch.object(M, "attr", return_value=object()), patch.object(M, "set_timeout"), \
             patch.object(M.A, "AXUIElementCopyParameterizedAttributeValue", return_value=(-25204, None)), \
             patch.object(M.A, "AXUIElementSetAttributeValue") as setter:
            self.assertFalse(b._write_selected(object(), "привет"))
        setter.assert_not_called()

    def test_chromium_async_selection_is_settled(self):
        # Chromium returns success for AXSelectedTextRange but an immediate
        # AXSelectedText read still describes the previous caret.
        b = self.backend()
        element = object()
        b.focus = M.Focus("active", element=element)
        with patch.object(M, "attr", side_effect=["", "ghbdtn "]), patch.object(M, "sleep"):
            self.assertEqual(b._settle_selected(element, "ghbdtn "), "ghbdtn ")

    def test_chromium_no_value_falls_back_to_selected_text(self):
        # Chromium's AXTextOperation is behind a disabled feature and returns
        # kAXErrorNoValue; its AXSelectedText setter still works for native
        # text controls. The fallback must be verified by a read-back.
        b = self.backend()
        element, marker = object(), object()
        b.focus = M.Focus("active", element=element)
        state = {"selected": "ghbdtn "}

        def read(_element, name):
            return marker if name == "AXSelectedTextMarkerRange" else state["selected"]

        def write(_element, name, value):
            if name == "AXSelectedText":
                state["selected"] = value
            return 0

        with patch.object(M, "attr", side_effect=read), patch.object(M, "set_timeout"), \
             patch.object(M, "set_range", return_value=True), \
             patch.object(M.A, "AXUIElementCopyParameterizedAttributeValue", return_value=(-25212, None)), \
             patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0, True)), \
             patch.object(M.A, "AXUIElementSetAttributeValue", side_effect=write) as setter:
            self.assertTrue(b._write_selected(element, "привет", 0))
        self.assertEqual([c.args[1] for c in setter.call_args_list], ["AXSelectedText"])
        self.assertEqual(b.last_replacement, "range-replaced/ax-selected-text")

    def synthetic_backend(self):
        b = self.backend()
        element = object()
        b.focus = M.Focus("active", 123, "com.openai.codex", element, "en", "AXTextArea")
        b._chromium_like = Mock(return_value=True)
        b._synthetic_focus_current = Mock(return_value=True)
        b.sources.secure.return_value = False
        return b, element

    def test_synthetic_other_chromium_is_not_enabled_implicitly(self):
        b, element = self.synthetic_backend()
        b.focus.bundle = "com.google.Chrome"
        self.assertFalse(b._synthetic_allowed("ghbdtn ", "привет "))

    def test_synthetic_aborts_when_fresh_focus_changes(self):
        b, element = self.synthetic_backend()
        b._synthetic_focus_current.return_value = False
        b._synthetic_events = Mock(return_value=[object()])
        with patch.object(M.Q, "CGEventPost") as post:
            self.assertFalse(b._synthetic_replace(element, "ghbdtn ", "привет ", 0))
        post.assert_not_called()
        self.assertEqual(b.last_replacement, "synthetic-aborted")

    def test_synthetic_fresh_check_rejects_other_foreground_pid(self):
        b, element = self.synthetic_backend()
        app = Mock()
        app.processIdentifier.return_value = 999
        with patch.object(M.K, "NSWorkspace") as workspace:
            workspace.sharedWorkspace.return_value.frontmostApplication.return_value = app
            self.assertFalse(M.MacBackend._synthetic_focus_current(b, element))

    def test_chromium_synthetic_batch_is_tagged_and_verified(self):
        b, element = self.synthetic_backend()
        with patch.object(M.Q, "CGEventSourceCreate", return_value=object()), \
             patch.object(M.Q, "CGEventCreateKeyboardEvent", side_effect=lambda *a: Mock()), \
             patch.object(M.Q, "CGEventSetFlags") as event_flags, \
             patch.object(M.Q, "CGEventSetIntegerValueField") as tag, \
             patch.object(M.Q, "CGEventKeyboardSetUnicodeString") as unicode, \
             patch.object(M.Q, "CGEventPost") as post, \
             patch.object(M, "sleep"), \
             patch.object(b, "_read_span", return_value=True):
            self.assertTrue(b._synthetic_replace(element, "ghbdtn ", "привет ", 0))
        # 7 Backspace down/up + one 7-unit Unicode chunk down/up.
        self.assertEqual(post.call_count, 16)
        self.assertEqual(tag.call_count, 16)
        self.assertTrue(all(c.args[2] == M.TAG for c in tag.call_args_list))
        self.assertEqual(event_flags.call_count, 16)
        self.assertTrue(all(c.args[1] == 0 for c in event_flags.call_args_list))
        self.assertEqual(unicode.call_count, 2)
        self.assertEqual(b.last_replacement, "range-replaced/synthetic-unicode")

    def test_synthetic_is_not_used_outside_chromium(self):
        b, element = self.synthetic_backend()
        b._chromium_like = Mock(return_value=False)
        with patch.object(b, "_synthetic_events") as build, \
             patch.object(M.Q, "CGEventPost") as post:
            self.assertFalse(b._synthetic_replace(element, "ghbdtn ", "привет ", 0))
        build.assert_not_called()
        post.assert_not_called()
        self.assertEqual(b.last_replacement, "synthetic-not-allowed")

    def test_synthetic_never_posts_in_secure_input(self):
        b, element = self.synthetic_backend()
        b.sources.secure.return_value = True
        with patch.object(M.Q, "CGEventPost") as post:
            self.assertFalse(b._synthetic_replace(element, "ghbdtn ", "привет ", 0))
        post.assert_not_called()
        self.assertEqual(b.last_replacement, "synthetic-blocked")

    def test_synthetic_failure_is_reported_not_retried(self):
        b, element = self.synthetic_backend()
        with patch.object(M.Q, "CGEventSourceCreate", return_value=object()), \
             patch.object(M.Q, "CGEventCreateKeyboardEvent", side_effect=lambda *a: Mock()), \
             patch.object(M.Q, "CGEventSetIntegerValueField"), \
             patch.object(M.Q, "CGEventKeyboardSetUnicodeString"), \
             patch.object(M.Q, "CGEventPost") as post, \
             patch.object(M, "sleep"), \
             patch.object(b, "_read_span", return_value=False):
            self.assertFalse(b._synthetic_replace(element, "ghbdtn ", "привет ", 0))
        self.assertEqual(post.call_count, 16)
        self.assertEqual(b.last_replacement, "synthetic-unverified")

    def test_read_span_uses_axstringforrange_without_selection(self):
        b, element = self.synthetic_backend()
        with patch.object(M.A, "AXValueCreate", return_value=object()), \
             patch.object(M.A, "AXUIElementCopyParameterizedAttributeValue", return_value=(0, "привет")) as read, \
             patch.object(M, "set_range") as select:
            self.assertTrue(b._read_span(element, 0, "привет"))
        self.assertEqual(read.call_args.args[1], "AXStringForRange")
        select.assert_not_called()

    def test_read_span_reports_unsupported_attribute_as_none(self):
        b, element = self.synthetic_backend()
        with patch.object(M.A, "AXValueCreate", return_value=object()), \
             patch.object(M.A, "AXUIElementCopyParameterizedAttributeValue", return_value=(-25205, None)):
            self.assertIsNone(b._read_span(element, 0, "привет"))

    def test_synthetic_delete_is_bounded(self):
        b, element = self.synthetic_backend()
        self.assertFalse(b._synthetic_allowed("x" * (M.SYNTHETIC_DELETE_LIMIT + 1), "y"))
        self.assertFalse(b._synthetic_allowed("x", "y" * (M.SYNTHETIC_DELETE_LIMIT * 2 + 1)))
        self.assertTrue(b._synthetic_allowed("ghbdtn ", "привет "))

    def test_write_selected_uses_synthetic_after_ax_unverified(self):
        b, element = self.synthetic_backend()
        marker = object()
        with patch.object(M, "attr", side_effect=lambda e, n: marker if n == "AXSelectedTextMarkerRange" else "ghbdtn"), \
             patch.object(M, "set_timeout"), \
             patch.object(M, "set_range", return_value=True), \
             patch.object(M.A, "AXUIElementCopyParameterizedAttributeValue", return_value=(-25212, None)), \
             patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0, True)), \
             patch.object(M.A, "AXUIElementSetAttributeValue", return_value=0), \
             patch.object(b, "_verify_span", return_value=False), \
             patch.object(b, "_synthetic_replace", return_value=True) as synthetic:
            self.assertTrue(b._write_selected(element, "привет", 0, "ghbdtn "))
        synthetic.assert_called_once_with(element, "ghbdtn ", "привет", 0)

    def test_webkit_space_tolerance_does_not_relax_word_validation(self):
        for actual in ("ghbdtm\u00a0", "Ghbdtn\u00a0", "ghbdtn\t", "ghbdtn\u202f", None):
            self.assertIsNone(M.observed_replacement(actual, "ghbdtn ", "привет "))

    def test_nbsp_range_replacement_preserves_webkit_separator(self):
        b = self.backend()
        b._switch = Mock()
        element, marker = object(), object()
        b.focus = M.Focus("active", element=element)
        state = {"selected": "ghbdtn\u00a0"}

        def read(_element, name):
            return marker if name == "AXSelectedTextMarkerRange" else state["selected"]

        def operation(*_args):
            state["selected"] = "привет\u00a0"
            return (0, ["привет\u00a0"])

        with patch.object(M.A, "AXUIElementIsAttributeSettable", return_value=(0, True)), \
             patch.object(M, "set_range", return_value=True), \
             patch.object(M, "attr", side_effect=read), \
             patch.object(M.A, "AXUIElementCopyParameterizedAttributeValue", side_effect=operation) as call, \
             patch.object(M.A, "AXUIElementSetAttributeValue") as write:
            self.assertTrue(b._range_replacement(element, Edit("ghbdtn ", "привет ", "ru"), "ghbdtn ", (7, 0)))
        self.assertEqual(call.call_args.args[2]["AXTextOperationReplacementString"], "привет\u00a0")
        self.assertEqual(b.last_replacement, "range-replaced/ax-text-operation")
        write.assert_not_called()
        b._switch.assert_called_once_with("ru")

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
