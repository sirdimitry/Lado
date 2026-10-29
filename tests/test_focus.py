"""Focused-node metadata only: no live app access or event observation."""
import sys
import unittest
from unittest.mock import Mock, patch, call

if sys.platform == "darwin":
    from lado.platforms import macos as M
    from lado.settings import Settings
    REAL_ATTR = M.attr


@unittest.skipUnless(sys.platform == "darwin", "macOS focus resolver")
class FocusTests(unittest.TestCase):
    def setUp(self):
        self.b = M.MacBackend.__new__(M.MacBackend)
        self.b.faulted = self.b.disabled = False
        self.b.settings = Settings()
        self.b.test_bundle = None
        self.b.valid_pair = True
        self.b.sources = Mock()
        self.b.sources.current.return_value = self.b.settings.english_source
        self.b.sources.secure.return_value = False
        self.b.system = object()
        self.app, self.field, self.container = object(), object(), object()
        self.attrs = {(self.app, "AXFocusedUIElement"): self.field,
                      (self.field, "AXRole"): "AXTextArea"}
        self.read = self.enterContext(patch.object(M, "attr", side_effect=lambda e, n: self.attrs.get((e, n))))
        self.ranges = self.enterContext(patch.object(M, "selected_range", return_value=(0, 0)))
        self.a = self.enterContext(patch.object(M, "A", Mock()))
        self.a.AXIsProcessTrusted.return_value = True
        self.a.AXUIElementCreateApplication.return_value = self.app
        self.a.AXUIElementGetPid.return_value = (0, 424242)
        self.enterContext(patch.object(M.Q, "CGPreflightListenEventAccess", return_value=True))
        foreground = Mock()
        foreground.processIdentifier.return_value = 424242
        foreground.bundleIdentifier.return_value = "example.editor"
        workspace = Mock()
        workspace.frontmostApplication.return_value = foreground
        self.enterContext(patch.object(M.K, "NSWorkspace", Mock(sharedWorkspace=Mock(return_value=workspace))))

    def focus(self):
        return self.b.check_focus()

    def test_direct_field_remains_supported(self):
        f = self.focus()
        self.assertEqual((f.state, f.role, f.reason), ("active", "AXTextArea", "ready"))
        self.assertIs(f.element, self.field)

    def test_accessibility_api_denial_is_permission_not_unsupported(self):
        self.read.side_effect = M.AccessibilityAccessError()
        f = self.focus()
        self.assertEqual((f.state, f.reason), ("permission", "accessibility-denied"))

    def test_missing_input_monitoring_has_distinct_reason(self):
        with patch.object(M.Q, "CGPreflightListenEventAccess", return_value=False):
            self.assertEqual(self.focus().reason, "input-monitoring-permission")
        self.read.assert_not_called()

    def test_attribute_permission_error_is_not_hidden_as_missing_field(self):
        self.a.kAXErrorAPIDisabled = -25211
        self.a.AXUIElementCopyAttributeValue.return_value = (-25211, None)
        # Call the real helper, which setUp replaces for other tests.
        with self.assertRaises(M.AccessibilityAccessError):
            REAL_ATTR(self.field, "AXRole")

    def test_container_follows_only_explicit_focused_node(self):
        self.attrs[self.app, "AXFocusedUIElement"] = self.container
        self.attrs[self.container, "AXRole"] = "AXWebArea"
        self.attrs[self.container, "AXFocusedUIElement"] = self.field
        self.assertIs(self.focus().element, self.field)
        self.assertFalse(any(c.args[1] in ("AXChildren", "AXValue", "AXSelectedText") for c in self.read.call_args_list))

    def test_nested_secure_field_stays_blocked_before_range_read(self):
        self.attrs[self.app, "AXFocusedUIElement"] = self.container
        self.attrs[self.container, "AXFocusedUIElement"] = self.field
        self.attrs[self.field, "AXSubrole"] = "AXSecureTextField"
        self.assertEqual(self.focus().state, "secure")
        self.ranges.assert_not_called()

    def test_protected_content_without_secure_subrole_stays_blocked(self):
        self.attrs[self.field, "AXProtectedContent"] = True
        self.assertEqual(self.focus().state, "secure")
        self.ranges.assert_not_called()

    def test_system_focus_can_resolve_same_process_field(self):
        self.attrs[self.app, "AXFocusedUIElement"] = self.container
        self.attrs[self.container, "AXRole"] = "AXGroup"
        self.attrs[self.b.system, "AXFocusedUIElement"] = self.field
        self.assertIs(self.focus().element, self.field)
        self.a.AXUIElementGetPid.assert_called_once_with(self.field, None)

    def test_system_focus_from_other_process_is_never_inspected(self):
        self.attrs[self.app, "AXFocusedUIElement"] = self.container
        self.attrs[self.b.system, "AXFocusedUIElement"] = self.field
        self.a.AXUIElementGetPid.return_value = (0, 999999)
        self.assertEqual(self.focus().state, "unsupported")
        self.assertNotIn(call(self.field, "AXRole"), self.read.call_args_list)
        self.ranges.assert_not_called()

    def test_system_focus_with_unknown_owner_is_rejected(self):
        self.attrs[self.app, "AXFocusedUIElement"] = None
        self.attrs[self.b.system, "AXFocusedUIElement"] = self.field
        self.a.AXUIElementGetPid.return_value = (-25202, 0)
        self.assertEqual(self.focus().state, "unsupported")
        self.ranges.assert_not_called()

    def test_missing_selection_range_explains_unsupported_editor(self):
        self.ranges.return_value = None
        f = self.focus()
        self.assertEqual((f.state, f.role, f.reason),
                         ("unsupported", "AXTextArea", "selection-range-unavailable"))

    def test_menu_focus_is_not_treated_as_editable(self):
        self.attrs[self.field, "AXRole"] = "AXMenu"
        self.assertEqual(self.focus().reason, "not-editable-focus")
        self.ranges.assert_not_called()

    def test_no_focused_element_explains_unsupported_state(self):
        self.attrs[self.app, "AXFocusedUIElement"] = None
        self.assertEqual(self.focus().reason, "no-focused-element")

    def test_focus_cycle_stops_without_recursion(self):
        self.attrs[self.app, "AXFocusedUIElement"] = self.container
        self.attrs[self.container, "AXFocusedUIElement"] = self.container
        self.assertEqual(self.focus().reason, "focus-chain-limit")
        self.assertLess(self.read.call_count, 10)

    def test_focus_chain_has_strict_four_node_budget(self):
        nodes = [object() for _ in range(10)]
        for left, right in zip(nodes, nodes[1:]):
            self.attrs[left, "AXFocusedUIElement"] = right
        f = self.b.resolve_focus(nodes[0], 424242, "example.editor", "en")
        self.assertEqual(f.reason, "focus-chain-limit")
        self.assertEqual(self.a.AXUIElementSetMessagingTimeout.call_count, 4)


if __name__ == "__main__":
    unittest.main()
