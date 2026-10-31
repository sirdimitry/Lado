"""Release gates for the 2026-10-29 input freeze investigation.

These assert REQUIRED safe behaviour, not the behaviour of the faulty release.
Failures are deliberate evidence of missing safeguards; do not mark expectedFailure.
All native service objects are replaced before invoking any backend operation.
No event tap, event posting, AX access, application launch, or real sleep is used.
"""
import sys
from collections import deque
from time import monotonic
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

if sys.platform == "darwin":
    from lado.platforms import macos as M
    from lado.engine import Buffer, Detector, DoubleShift, MAX_SELECTION
    from lado.settings import Settings


@unittest.skipUnless(sys.platform == "darwin", "macOS adapter")
class IncidentSafetyTests(unittest.TestCase):
    def setUp(self):
        # Copy numeric constants only. There is no path to real native functions.
        constants = {name: getattr(M.Q, name) for name in (
            "kCGEventKeyDown", "kCGEventFlagsChanged", "kCGEventLeftMouseDown",
            "kCGEventRightMouseDown", "kCGEventOtherMouseDown",
            "kCGEventTapDisabledByTimeout", "kCGEventTapDisabledByUserInput",
            "kCGEventSourceUserData", "kCGKeyboardEventKeycode",
            "kCGEventFlagMaskCommand", "kCGEventFlagMaskControl",
            "kCGEventFlagMaskAlternate", "kCGEventFlagMaskShift")}
        self.q = SimpleNamespace(**constants)
        self.q.CGEventGetIntegerValueField = Mock(side_effect=lambda e, f: e.get(f, 0))
        self.q.CGEventGetFlags = Mock(return_value=0)
        self.q.CGEventKeyboardGetUnicodeString = Mock(return_value=(1, "a"))
        self.q.CGEventSetIntegerValueField = Mock()
        self.q.CGEventTapPostEvent = Mock()
        self.q.CGEventTapEnable = Mock()
        self.q.CGEventCreateCopy = Mock(side_effect=lambda e: dict(e))
        self.q.CGPreflightPostEventAccess = Mock(return_value=True)
        self.q.CGPreflightListenEventAccess = Mock(return_value=True)
        self.a, self.f, self.k = Mock(), Mock(), Mock()
        self.a.AXUIElementIsAttributeSettable.return_value = (0, True)
        self.a.AXUIElementSetAttributeValue.return_value = 0
        self.a.AXUIElementCopyAttributeValue.return_value = (0, None)
        for name, obj in (("Q", self.q), ("A", self.a), ("F", self.f), ("K", self.k)):
            self.enterContext(patch.object(M, name, obj))
        self.b = M.MacBackend.__new__(M.MacBackend)
        b = self.b
        b.settings = Settings()
        b.test_bundle = None
        b.detector = Detector(b.settings)
        b.buffer = Buffer(b.detector)
        b.gesture = DoubleShift()
        b.sources = Mock()
        b.sources.secure.return_value = False
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
        b.last_error = None
        b.last_state = None
        b.tap, b.tap_source = object(), object()
        b._confirm_target = Mock(return_value=True)
        b.defer, b.notify = Mock(), Mock()
        b.focus = M.Focus("active", 123, "test.synthetic", object(), "en")
        b.refresh = Mock(return_value=b.focus)
        self.event = {self.q.kCGKeyboardEventKeycode: 0}

    def assert_no_reenable(self):
        self.assertFalse(any(c.args[1] for c in self.q.CGEventTapEnable.call_args_list),
                         "Unsafe tap was enabled again after a system stop")

    def test_timeout_remains_disarmed(self):
        self.b.callback(None, self.q.kCGEventTapDisabledByTimeout, self.event, None)
        self.assert_no_reenable()

    def test_user_requested_disable_is_respected(self):
        self.b.callback(None, self.q.kCGEventTapDisabledByUserInput, self.event, None)
        self.assert_no_reenable()

    def test_repeated_timeouts_do_not_create_restart_loop(self):
        for _ in range(1000):
            self.b.callback(None, self.q.kCGEventTapDisabledByTimeout, self.event, None)
        self.assert_no_reenable()

    def test_next_key_after_timeout_passes_without_reading_text(self):
        self.b.callback(None, self.q.kCGEventTapDisabledByTimeout, self.event, None)
        self.assertIs(self.b.callback(None, self.q.kCGEventKeyDown, self.event, None), self.event)
        self.q.CGEventKeyboardGetUnicodeString.assert_not_called()

    def test_key_callback_never_waits_for_editor_focus_rpc(self):
        # This is the synchronous entry point that performs editor AX IPC.
        # A hung editor is represented by a trap, with no actual blocking call.
        self.b.check_focus = Mock(side_effect=TimeoutError("synthetic editor timeout"))
        del self.b.refresh  # exercise the actual refresh -> check_focus path
        self.b.callback(None, self.q.kCGEventKeyDown, self.event, None)
        self.b.check_focus.assert_not_called()

    def test_callback_exception_disarms_tap_immediately(self):
        self.b._handle = Mock(side_effect=RuntimeError("synthetic failure"))
        self.assertIs(self.b.callback(None, self.q.kCGEventKeyDown, self.event, None), self.event)
        self.assertTrue(self.b.disabled)
        self.assertTrue(self.b.tap is None or any(
            not c.args[1] for c in self.q.CGEventTapEnable.call_args_list),
            "A disabled flag alone leaves the active global filter connected")

    def test_only_one_tagged_chromium_posting_path(self):
        # The adapter has exactly one synthetic POST site, gated by the Chromium
        # check and the chromium_synthetic preference. Every event it builds is
        # tagged so our own listen-only tap cannot re-enter the detector.
        from pathlib import Path
        source = Path(M.__file__).read_text()
        self.assertNotIn("CGEventTapPostEvent", source)
        self.assertEqual(source.count("CGEventPost("), 1)
        self.assertIn("chromium_synthetic", source)
        self.assertIn("def _synthetic_replace", source)
        self.assertIn("Q.CGEventSetIntegerValueField(event, Q.kCGEventSourceUserData, TAG)", source)

    def test_revoked_observation_permission_precedes_field_reads(self):
        self.q.CGPreflightListenEventAccess.return_value = False
        self.assertEqual(self.b.check_focus().state, "permission")
        self.a.AXUIElementCopyAttributeValue.assert_not_called()

    def test_word_edit_runs_only_after_callback_returns(self):
        self.b.buffer.feed("ghbdtn")
        self.b._replace_tail = Mock(return_value=True)
        self.q.CGEventKeyboardGetUnicodeString.return_value = (1, " ")
        with patch.object(M, "selected_range", return_value=(7, 0)):
            self.assertIs(self.b.callback(None, self.q.kCGEventKeyDown, self.event, None), self.event)
            self.b._replace_tail.assert_not_called()
            self.q.CGEventKeyboardGetUnicodeString.assert_not_called()
            self.b.drain_events()
        edit = self.b._replace_tail.call_args.args[1]
        self.assertEqual(edit.before, "ghbdtn ")
        self.assertEqual(edit.after, "привет ")

    def test_secure_transition_before_drain_discards_event_without_decoding(self):
        self.b.callback(None, self.q.kCGEventKeyDown, self.event, None)
        self.b.refresh.return_value = M.Focus("secure")
        self.b.drain_events()
        self.q.CGEventKeyboardGetUnicodeString.assert_not_called()
        self.assertEqual(len(self.b.events), 0)

    def test_expired_event_never_reads_text(self):
        self.b.callback(None, self.q.kCGEventKeyDown, self.event, None)
        item = self.b.events.pop()
        self.b.events.append((monotonic() - 1, *item[1:]))
        self.b.drain_events()
        self.q.CGEventKeyboardGetUnicodeString.assert_not_called()

    def test_new_focus_never_receives_old_event(self):
        self.b.callback(None, self.q.kCGEventKeyDown, self.event, None)
        self.b.refresh.return_value = M.Focus("active", 456, "other", object(), "en")
        self.b.drain_events()
        self.q.CGEventKeyboardGetUnicodeString.assert_not_called()

    def test_queue_overflow_clears_all_pending_context(self):
        for _ in range(17):
            self.b.callback(None, self.q.kCGEventKeyDown, self.event, None)
        self.assertEqual(len(self.b.events), 0)
        self.assertEqual(self.b.defer.call_count, 1)
        self.assertEqual(self.b.buffer.current, "")

    def test_deferred_editor_failure_disarms_observation(self):
        self.b.callback(None, self.q.kCGEventKeyDown, self.event, None)
        self.b.refresh.side_effect = TimeoutError("synthetic stalled editor")
        self.b.drain_events()
        self.assertTrue(self.b.faulted)
        self.assertIsNone(self.b.tap)
        self.q.CGEventKeyboardGetUnicodeString.assert_not_called()

    def test_timer_cannot_restart_faulted_observer(self):
        self.b.callback(None, self.q.kCGEventTapDisabledByTimeout, self.event, None)
        self.assertFalse(self.b.start())
        self.assert_no_reenable()

    def test_start_uses_passive_observation_only(self):
        self.b.tap = None
        self.q.kCGSessionEventTap = 1
        self.q.kCGHeadInsertEventTap = 0
        self.q.kCGEventTapOptionListenOnly = 1
        self.q.CGEventMaskBit = Mock(side_effect=lambda n: 1 << n)
        self.q.CGEventTapCreate = Mock(return_value=object())
        self.assertTrue(self.b.start())
        self.assertEqual(self.q.CGEventTapCreate.call_args.args[2],
                         self.q.kCGEventTapOptionListenOnly)

    def test_new_input_during_editor_read_cancels_selection_write(self):
        with patch.object(M, "selected_range", return_value=(0, 6)), \
             patch.object(M, "attr", side_effect=self.changed_during_read):
            self.b._selection(None, self.b.focus)
        self.a.AXUIElementSetAttributeValue.assert_not_called()

    def changed_during_read(self, *args):
        self.b.input_serial += 1
        return "ghbdtn"

    def test_expired_edit_never_changes_editor_selection(self):
        self.b.edit_deadline = monotonic() - 1
        self.selection()
        self.a.AXUIElementSetAttributeValue.assert_not_called()

    def test_newer_key_in_batch_prevents_edit_of_previous_word(self):
        self.b.buffer.feed("ghbdtn")
        self.b._replace_tail = Mock()
        self.q.CGEventKeyboardGetUnicodeString.side_effect = [(1, " "), (1, "x")]
        with patch.object(M, "selected_range", return_value=(8, 0)):
            for _ in range(2):
                self.b.callback(None, self.q.kCGEventKeyDown, self.event, None)
            self.b.drain_events()
        self.b._replace_tail.assert_not_called()
        self.assertEqual(self.b.buffer.current, "x")

    def selection(self, text="ghbdtn", settable=True, write_error=0):
        self.b._type = Mock()
        state = {"selected": text}
        self.a.AXUIElementIsAttributeSettable.return_value = (0, settable)

        def write(_element, name, value):
            if write_error:
                return write_error
            if name == "AXSelectedText":
                state["selected"] = value
            return 0

        self.a.AXUIElementSetAttributeValue.side_effect = write
        self.enterContext(patch.object(M, "selected_range", return_value=(0, len(text))))
        read = self.enterContext(patch.object(
            M, "attr", side_effect=lambda e, n: state["selected"] if n == "AXSelectedText" else None))
        self.b._selection(None, self.b.focus)
        return read

    def test_unsupported_editor_never_falls_back_to_key_flood(self):
        self.selection(settable=False)
        self.assertEqual(self.b._type.call_count, 0, "Unsupported editor triggered synthetic typing")

    def test_failed_atomic_write_never_falls_back_to_key_flood(self):
        self.selection(write_error=-25204)
        self.assertEqual(self.b._type.call_count, 0, "Failed AX write triggered synthetic typing")

    def test_large_selection_never_uses_synthetic_key_flood(self):
        self.selection(text="a" * MAX_SELECTION, settable=False)
        self.assertEqual(self.b._type.call_count, 0, "Large selection triggered synthetic typing")

    def test_stop_removes_run_loop_source(self):
        self.b.stop()
        self.assertIsNone(self.b.tap)
        self.f.CFRunLoopRemoveSource.assert_called_once()

    # Passing controls prove that the gates above exercise the real adapter,
    # not just a blanket failure or incorrectly configured fake native API.
    def test_secure_field_never_reads_key_text(self):
        self.b.refresh.return_value = M.Focus("secure")
        self.assertIs(self.b.callback(None, self.q.kCGEventKeyDown, self.event, None), self.event)
        self.q.CGEventKeyboardGetUnicodeString.assert_not_called()

    def test_own_synthetic_event_never_reenters_focus_queries(self):
        self.event[self.q.kCGEventSourceUserData] = M.TAG
        self.b.callback(None, self.q.kCGEventKeyDown, self.event, None)
        self.b.refresh.assert_not_called()

    def test_mouse_click_passes_through_and_clears_context(self):
        self.b.buffer.feed("synthetic")
        self.assertIs(self.b.callback(None, self.q.kCGEventLeftMouseDown, self.event, None), self.event)
        self.assertEqual(self.b.buffer.current, "")
        self.b.refresh.assert_not_called()

    def test_supported_atomic_selection_does_not_post_keys(self):
        self.selection()
        selected_writes = [c.args for c in self.a.AXUIElementSetAttributeValue.call_args_list
                           if c.args[1] == "AXSelectedText"]
        self.assertEqual(selected_writes,
                         [(self.b.focus.element, "AXSelectedText", "привет")])
        self.b._type.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
