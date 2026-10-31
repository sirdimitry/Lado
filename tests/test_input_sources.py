"""TIS invalidation must never enter HIToolbox from the background probe."""
import sys
import threading
import unittest
from unittest.mock import Mock, patch

if sys.platform == 'darwin':
    from lado.platforms import macos as M


@unittest.skipUnless(sys.platform == 'darwin', 'macOS input sources')
class InputSourceThreadTests(unittest.TestCase):
    def source(self):
        source = M.InputSources.__new__(M.InputSources)
        source.carbon = Mock()
        source.cf = Mock()
        source._current_id = 'com.apple.keylayout.ABC'
        source._secure_input = True
        return source

    def worker(self, fn):
        result = []
        def run():
            try:
                result.append(fn())
            except Exception as error:
                result.append(error)
        thread = threading.Thread(target=run)
        thread.start()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        return result[0]

    def test_probe_reads_source_snapshot_without_entering_carbon(self):
        source = self.source()
        for _ in range(20):
            self.assertEqual(self.worker(source.current), 'com.apple.keylayout.ABC')
        self.assertEqual(source.carbon.mock_calls, [])
        self.assertEqual(source.cf.mock_calls, [])

    def test_probe_reads_secure_snapshot_without_entering_carbon(self):
        source = self.source()
        self.assertTrue(self.worker(source.secure))
        self.assertEqual(source.carbon.mock_calls, [])

    def test_source_enumeration_and_selection_reject_worker(self):
        source = self.source()
        for operation in (source.all, lambda: source.select('ru'), lambda: source.prop(1, 'id')):
            self.assertIsInstance(self.worker(operation), RuntimeError)
        self.assertEqual(source.carbon.mock_calls, [])

    def test_main_thread_publishes_new_source_and_releases_reference(self):
        source = self.source()
        source.carbon.TISCopyCurrentKeyboardInputSource.return_value = 123
        source.prop = Mock(return_value=456)
        source.string = Mock(return_value='com.apple.keylayout.Russian')
        self.assertEqual(source.current(), 'com.apple.keylayout.Russian')
        self.assertEqual(self.worker(source.current), 'com.apple.keylayout.Russian')
        source.cf.CFRelease.assert_called_once_with(123)

    def test_remote_children_array_is_bounded_before_copy(self):
        node = object()
        with patch.object(M.A, 'AXUIElementSetMessagingTimeout'), \
             patch.object(M.A, 'AXUIElementGetAttributeValueCount', return_value=(0, 50000)), \
             patch.object(M.A, 'AXUIElementCopyAttributeValues', return_value=(0, [node])) as copy, \
             patch.object(M.A, 'AXUIElementCopyAttributeValue') as unbounded:
            self.assertEqual(M.children(node), [node])
        copy.assert_called_once_with(node, 'AXChildren', 0, 80, None)
        unbounded.assert_not_called()

    def test_children_permission_denial_is_not_hidden(self):
        with patch.object(M.A, 'AXUIElementSetMessagingTimeout'), \
             patch.object(M.A, 'AXUIElementGetAttributeValueCount', return_value=(M.A.kAXErrorAPIDisabled, 0)):
            with self.assertRaises(M.AccessibilityAccessError):
                M.children(object())


if __name__ == '__main__':
    unittest.main()
