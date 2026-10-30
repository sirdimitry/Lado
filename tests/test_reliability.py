"""Focus probe, wrapper churn, and recovery behaviour; no live AX access."""
import sys
import threading
import time
from collections import deque
from time import monotonic
import unittest
from unittest.mock import Mock, patch

if sys.platform == "darwin":
    from lado.engine import Buffer, Detector, DoubleShift
    from lado.platforms import macos as M
    from lado.settings import Settings


@unittest.skipUnless(sys.platform == "darwin", "macOS adapter")
class ReliabilityTests(unittest.TestCase):
    def probe_backend(self):
        b = M.MacBackend.__new__(M.MacBackend)
        b._probe_lock = threading.Lock()
        b._probe_wake = threading.Event()
        b._probe_stop = threading.Event()
        b._probe_focus = None
        b._probe_at = 0.0
        b._probe_thread = None
        b._workspace_token = None
        return b

    def refresh_backend(self):
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
        b.focus_checked = 0.0
        b.notify = Mock()
        b._probe_lock = threading.Lock()
        b._probe_at = monotonic()
        return b

    def test_probe_publishes_snapshot_and_stops_cleanly(self):
        b = self.probe_backend()
        expected = M.Focus("active", 4242, "example.editor", object(), "en",
                           "AXTextArea", "ready", "range")
        b.check_focus = Mock(return_value=expected)
        with patch.object(M.MacBackend, "_install_workspace_observer"):
            b.start_probe()
            self.assertIsNotNone(b._probe_thread)
            deadline = monotonic() + 2
            published, _ = b._snapshot()
            while published is None and monotonic() < deadline:
                time.sleep(0.01)
                published, _ = b._snapshot()
            b.stop_probe()
        self.assertIs(published, expected)
        self.assertIsNone(b._probe_thread)
        self.assertTrue(b._probe_stop.is_set())

    def test_refresh_consumes_snapshot_without_live_ax_query(self):
        b = self.refresh_backend()
        b.focus = M.Focus("active", 4242, "example.editor", object(), "en",
                          "AXTextArea", "ready", "range")
        b._probe_focus = M.Focus("active", 4242, "example.editor", object(), "en",
                                 "AXTextArea", "ready", "range")
        b.check_focus = Mock(side_effect=AssertionError("live AX query"))
        focus = b.refresh()
        self.assertEqual(focus.state, "active")
        b.check_focus.assert_not_called()

    def test_new_wrapper_for_same_field_preserves_typed_word(self):
        b = self.refresh_backend()
        b.focus = M.Focus("active", 4242, "example.editor", object(), "en",
                          "AXTextArea", "ready", "range")
        b.buffer.feed("ghbdtn")
        b._probe_focus = M.Focus("active", 4242, "example.editor", object(), "en",
                                 "AXTextArea", "ready", "range")
        with patch.object(M.F, "CFEqual", return_value=True):
            b.refresh()
        self.assertEqual(b.buffer.current, "ghbdtn")
        self.assertIs(b.focus.element, b._probe_focus.element)

    def test_focus_change_clears_typed_word(self):
        b = self.refresh_backend()
        b.focus = M.Focus("active", 4242, "example.editor", object(), "en",
                          "AXTextArea", "ready", "range")
        b.buffer.feed("ghbdtn")
        b._probe_focus = M.Focus("active", 4242, "example.editor", object(), "en",
                                 "AXTextField", "ready", "range")
        b.refresh()
        self.assertEqual(b.buffer.current, "")

    def test_fault_latches_once_until_restart(self):
        b = M.MacBackend.__new__(M.MacBackend)
        b.faulted = b.disabled = False
        b.last_error = None
        b.last_ax_error = 0
        b.stop_tap = Mock()
        b._wake_probe = Mock()
        b.notify = Mock()
        b.defer = Mock()
        b._fault("EventTapStopped")
        b._fault("EventTapStopped")
        self.assertTrue(b.faulted)
        self.assertTrue(b.disabled)
        self.assertEqual(b.last_error, "EventTapStopped")
        b.stop_tap.assert_called_once()
        b.defer.assert_called_once()
        b.defer.call_args.args[0]()
        self.assertEqual(b.notify.call_args.args[0].state, "error")

    def test_restart_clears_latch_and_rearms_observer(self):
        b = M.MacBackend.__new__(M.MacBackend)
        b.faulted = b.disabled = True
        b.last_error = "EventTapStopped"
        b.last_ax_error = -25204
        b.focus_required = 0.0
        b.clear = Mock()
        b.start_probe = Mock()
        b.start = Mock(return_value=True)
        b.refresh = Mock()
        b._wake_probe = Mock()
        self.assertTrue(b.restart())
        self.assertFalse(b.faulted)
        self.assertFalse(b.disabled)
        self.assertIsNone(b.last_error)
        self.assertEqual(b.last_ax_error, 0)
        b.clear.assert_called_once()
        b.start_probe.assert_called_once()
        b.start.assert_called_once()
        b.refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main()
