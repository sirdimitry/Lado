"""Opt-in live checks restricted to the project's disposable native test pad.

This module is never loaded in normal operation. It generates only public,
synthetic examples, never reads secure-field contents, and reports case outcomes
without recording text. It always closes Lado when finished, including on failure.
"""
import json
import os
from pathlib import Path
import sys
from time import monotonic

import AppKit as K
import ApplicationServices as A
import Quartz as Q

from .platforms.macos import attr, selected_range, set_range, same_element

FIXTURE = "com.sirdimitry.lado-testpad"


class CompatibilityRunner:
    def __init__(self, delegate):
        self.ui = delegate
        self.backend = delegate.backend
        self.defer = delegate.defer
        self.results = []
        self.finished = False
        self.fixture = None
        self.plain = None
        self.secure = None
        self.second = None
        self.original_source = self.backend.sources.current()
        self.original_automatic = self.backend.settings.automatic
        self.original_exceptions = list(self.backend.settings.exceptions)
        if "--fixture-root" in sys.argv:
            self.root = Path(sys.argv[sys.argv.index("--fixture-root") + 1]).resolve()
        elif getattr(sys, "frozen", False):
            self.root = Path(sys.executable).parents[4]
        else:
            self.root = Path(__file__).resolve().parents[2]
        self.report = self.root / "build/compatibility-results.json"
        self.jobs = []

    def later(self, delay, fn):
        def guarded():
            if self.finished:
                return
            try:
                fn()
            except Exception as error:
                self.results.append({"case": "runner", "passed": False,
                                     "error": type(error).__name__})
                self.finish()
        self.defer(guarded, delay)

    def record(self, case, condition):
        result = {"case": case, "passed": bool(condition)}
        if not condition:
            result["diagnostic"] = {
                "guard": self.backend.focus.state,
                "tap_connected": bool(self.backend.tap),
                "fixture_foreground": self.active(),
                "has_current_word": bool(self.backend.buffer.current),
                "completed_words": len(self.backend.buffer.words),
                "has_last_edit": self.backend.buffer.last_edit is not None,
                "error_type": getattr(self.backend, "last_error", None),
                "focus_reason": self.backend.focus.reason,
                "replacement_result": getattr(self.backend, "last_replacement", "none"),
                "shift_down": self.backend.gesture.down is not None,
                "has_shift_tap": self.backend.gesture.last_tap is not None,
                "queued_events": len(self.backend.events),
                "has_selection_undo": self.backend.selection_undo is not None,
            }
        self.results.append(result)
        if not condition:
            self.finish()
            return False
        return True

    def begin(self):
        if self.backend.test_bundle != FIXTURE:
            self.record("test_scope_required", False)
            return
        candidates = K.NSRunningApplication.runningApplicationsWithBundleIdentifier_(FIXTURE)
        expected = (self.root / "build/LadoTestPad.app").resolve()
        self.fixture = next((x for x in candidates if x.bundleURL()
                             and Path(str(x.bundleURL().path())).resolve() == expected), None)
        if not self.record("owned_fixture_running", self.fixture is not None):
            return
        if not self.record("permissions", bool(A.AXIsProcessTrusted() and Q.CGPreflightPostEventAccess())):
            return
        if not self.record("event_tap_connected", bool(self.backend.tap)):
            return
        self.fixture.activateWithOptions_(K.NSApplicationActivateIgnoringOtherApps)
        self.later(.4, self.prepare)

    def active(self):
        current = K.NSWorkspace.sharedWorkspace().frontmostApplication()
        return bool(current and self.fixture and
                    current.processIdentifier() == self.fixture.processIdentifier() and
                    str(current.bundleIdentifier() or "") == FIXTURE)

    def require_active(self):
        if not self.active():
            self.record("fixture_must_stay_foreground", False)
            return False
        return True

    def find(self, node, identifier, remaining=400):
        if remaining <= 0:
            return None
        if (str(attr(node, "AXIdentifier") or "") == identifier
                or str(attr(node, "AXDOMIdentifier") or "") == identifier):
            return node
        for child in list(attr(node, "AXChildren") or [])[:100]:
            found = self.find(child, identifier, remaining - 1)
            if found is not None:
                return found
        return None

    def prepare(self):
        if not self.record("fixture_foreground", self.active()):
            return
        app = A.AXUIElementCreateApplication(self.fixture.processIdentifier())
        A.AXUIElementSetMessagingTimeout(app, .1)
        self.plain = self.find(app, "plain-test-field")
        self.secure = self.find(app, "secure-test-field")
        self.second = self.find(app, "second-test-field")
        if not self.record("native_test_controls", self.plain is not None and self.secure is not None):
            return
        indicator = self.ui.item.button()
        if not self.record("single_language_indicator", indicator.title() == "" and indicator.imagePosition() == K.NSImageOnly):
            return
        self.backend.settings.exceptions = []
        self.backend.settings.automatic = True
        self.jobs = [
            ("auto_wrong_layout", self.auto_word),
            ("manual_word_reverse", self.reverse_word),
            ("manual_word_repeat", self.repeat_word),
            ("uppercase_untouched", self.uppercase),
            ("uppercase_manual", self.uppercase_manual),
            ("explicit_exception", self.exception),
            ("exception_manual_override", self.exception_manual),
            ("selected_paragraph", self.paragraph),
            ("selected_paragraph_reverse", self.paragraph_reverse),
            ("one_letter_manual", self.one_letter),
            ("one_letter_reverse", self.one_letter_reverse),
            ("emoji_selection", self.emoji_selection),
            ("emoji_selection_reverse", self.emoji_reverse),
            ("same_role_field_transition", self.field_transition),
            ("continuous_typing_after_source_switch", self.continuous),
            ("secure_field_blocks_processing", self.password),
        ]
        # WebKit exposes the AX tree before its editable selection is stable.
        # Give the first bounded probe cycle time to settle.
        self.later(.6, self.next_job)

    def next_job(self):
        if self.finished:
            return
        if not self.jobs:
            self.finish()
            return
        if not self.require_active():
            return
        self.current_case, action = self.jobs.pop(0)
        action()

    def check_text(self, expected):
        if not self.require_active():
            return
        # contenteditable represents trailing typed spaces as NBSP. Compare
        # visible text while keeping letter and paragraph checks exact.
        actual = str(attr(self.plain, "AXValue") or "").replace("\u00a0", " ")
        if self.record(self.current_case, actual == expected):
            self.later(.1, self.next_job)

    def reset(self, initial=""):
        if not self.require_active():
            return False
        self.backend.clear()
        A.AXUIElementSetAttributeValue(self.plain, "AXFocused", True)
        if A.AXUIElementSetAttributeValue(self.plain, "AXValue", initial) != 0:
            self.record("fixture_reset_supported", False)
            return False
        set_range(self.plain, (len(initial.encode("utf-16-le")) // 2, 0))
        self.backend.sources.select(self.backend.settings.english_source)
        self.backend.set_frontmost(self.fixture)
        self.backend.clear()
        self.backend.refresh()
        return True

    def key(self, keycode, flags=0):
        if not self.require_active():
            return False
        source = self.backend.sources.current()
        chars = self.backend.sources._characters(source)
        char = " " if keycode == 49 else chars.get((keycode, 2 if flags & Q.kCGEventFlagMaskShift else 0))
        for down in (True, False):
            event = Q.CGEventCreateKeyboardEvent(None, keycode, down)
            Q.CGEventSetFlags(event, flags)
            if char:
                # CGEventSetFlags does not recompute an event's Unicode payload.
                # Match real hardware: keycode, modifiers and character agree.
                Q.CGEventKeyboardSetUnicodeString(event, len(char.encode("utf-16-le")) // 2, char)
            # Deliberately not tagged as Lado replacement events: this is the
            # physical-input path under test, restricted to the fixture above.
            Q.CGEventPost(Q.kCGHIDEventTap, event)
        return True

    def type_keys(self, text, done):
        chars = self.backend.sources._characters(self.backend.settings.english_source)
        keys = {char: key for key, char in chars.items()}
        index = [0]
        waiting_since = monotonic()
        def one():
            if not self.require_active():
                return
            if index[0] == 0:
                f = self.backend.refresh()
                if f.state != "active" or not same_element(f.element, self.plain) or f.layout != self.backend.sources.current():
                    if monotonic() - waiting_since > 3:
                        self.record("field_ready_for_typing", False)
                        return
                    self.later(.05, one)
                    return
            if index[0] >= len(text):
                self.later(.15, done)
                return
            char = text[index[0]]
            index[0] += 1
            if char == " ":
                self.key(49)
            else:
                code, shift = keys[char]
                self.key(code, Q.kCGEventFlagMaskShift if shift else 0)
            self.later(.07, one)
        one()

    def double_shift(self, done):
        def phase(index):
            if not self.require_active():
                return
            if index == 4:
                self.later(.2, done)
                return
            down = index % 2 == 0
            event = Q.CGEventCreateKeyboardEvent(None, 56, down)
            Q.CGEventSetType(event, Q.kCGEventFlagsChanged)
            Q.CGEventSetFlags(event, Q.kCGEventFlagMaskShift if down else 0)
            Q.CGEventPost(Q.kCGHIDEventTap, event)
            self.later(.07, lambda: phase(index + 1))
        phase(0)

    def auto_word(self):
        if self.reset():
            self.later(.15, lambda: self.type_keys("ghbdtn ", lambda: self.check_text("привет ")))

    def reverse_word(self):
        self.double_shift(lambda: self.check_text("ghbdtn "))

    def repeat_word(self):
        self.double_shift(lambda: self.check_text("привет "))

    def uppercase(self):
        if self.reset():
            self.later(.15, lambda: self.type_keys("GHBDTN ", lambda: self.check_text("GHBDTN ")))

    def uppercase_manual(self):
        self.double_shift(lambda: self.check_text("ПРИВЕТ "))

    def exception(self):
        self.backend.settings.exceptions = ["ghbdtn"]
        if self.reset():
            self.later(.15, lambda: self.type_keys("ghbdtn ", lambda: self.check_text("ghbdtn ")))

    def exception_manual(self):
        self.double_shift(lambda: self.check_text("привет "))

    def paragraph(self):
        self.backend.settings.exceptions = []
        text = "ghbdtn\nvbh"
        if self.reset(text):
            set_range(self.plain, (0, len(text)))
            self.double_shift(lambda: self.check_text("привет\nмир"))

    def paragraph_reverse(self):
        self.double_shift(lambda: self.check_text("ghbdtn\nvbh"))

    def one_letter(self):
        if self.reset():
            self.later(.15, lambda: self.type_keys("d", lambda: self.double_shift(lambda: self.check_text("в"))))

    def one_letter_reverse(self):
        self.double_shift(lambda: self.check_text("d"))

    def emoji_selection(self):
        if self.reset("😀 ghbdtn world"):
            set_range(self.plain, (3, 6))
            self.later(.25, lambda: self.double_shift(lambda: self.check_text("😀 привет world")))

    def emoji_reverse(self):
        self.double_shift(lambda: self.check_text("😀 ghbdtn world"))

    def field_transition(self):
        if self.second is None:
            self.record("second_native_field", False)
            return
        if self.reset():
            def change():
                # WebKit discards an AXValue write made before the field has
                # focus. Focus first, then seed the field and Double Shift.
                A.AXUIElementSetAttributeValue(self.second, "AXFocused", True)
                def fill():
                    A.AXUIElementSetAttributeValue(self.second, "AXValue", "ghbdtn")
                    set_range(self.second, (6, 0))
                    self.later(.5, lambda: self.double_shift(check))
                self.later(.3, fill)
            def check():
                if not self.require_active():
                    return
                condition = (str(attr(self.second, "AXValue") or "") == "ghbdtn"
                             and not self.backend.buffer.current
                             and same_element(self.backend.focus.element, self.second))
                if self.record(self.current_case, condition):
                    self.later(.1, self.next_job)
            self.later(.15, lambda: self.type_keys("ghbdtn", change))

    def continuous(self):
        if self.reset():
            self.later(.15, lambda: self.type_keys("ghbdtn vbh ", lambda: self.check_text("привет мир ")))

    def password(self):
        if not self.require_active():
            return
        self.backend.clear()
        A.AXUIElementSetAttributeValue(self.secure, "AXFocused", True)
        self.later(.2, self.check_password)

    def check_password(self, tries=12):
        if not self.require_active():
            return
        state = self.backend.refresh()
        # WebKit can take one probe cycle to replace the previous field with
        # the secure one; wait for the bounded poll instead of sampling once.
        if state.state != "secure" and tries > 0:
            self.later(.1, lambda: self.check_password(tries - 1))
            return
        # Do not read AXValue, AXSelectedText or event characters in a secure field.
        condition = (state.state == "secure" and not self.backend.buffer.current
                     and not self.backend.buffer.words and self.backend.buffer.last_edit is None
                     and self.ui.item.button().appearsDisabled())
        if self.record(self.current_case, condition):
            self.double_shift(self.check_password_after_shift)

    def check_password_after_shift(self):
        state = self.backend.refresh()
        condition = state.state == "secure" and self.backend.buffer.last_edit is None
        if self.record("secure_double_shift_ignored", condition):
            self.finish()

    def finish(self):
        if self.finished:
            return
        self.finished = True
        self.backend.settings.automatic = self.original_automatic
        self.backend.settings.exceptions = self.original_exceptions
        self.backend.clear()
        self.backend.sources.select(self.original_source)
        data = {"format": "lado-compatibility-v1", "scope": FIXTURE,
                "passed": bool(self.results) and all(x["passed"] for x in self.results),
                "cases": self.results, "contains_typed_text": False}
        self.report.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.chmod(self.report, 0o600)
        self.backend.stop()
        if self.fixture:
            self.fixture.terminate()
        K.NSApp.terminate_(None)
