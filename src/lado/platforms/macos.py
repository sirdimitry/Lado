"""macOS input adapter. No clipboard, networking, or input logging."""
from collections import deque
from dataclasses import dataclass
import ctypes as C
import os
from time import monotonic

import AppKit as K
import ApplicationServices as A
import CoreFoundation as F
import Quartz as Q

from ..engine import Buffer, Detector, DoubleShift, MAX_SELECTION
from ..layout import LayoutConverter

TAG = 0x4C41444F
UTF8 = 0x08000100


class InputSources:
    """Small ctypes bridge to Apple's Text Input Source Services."""
    def __init__(self):
        self.carbon = C.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
        self.cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        for lib, name, result, args in [
            (self.carbon, "TISCopyCurrentKeyboardInputSource", C.c_void_p, []),
            (self.carbon, "TISCreateInputSourceList", C.c_void_p, [C.c_void_p, C.c_bool]),
            (self.carbon, "TISGetInputSourceProperty", C.c_void_p, [C.c_void_p, C.c_void_p]),
            (self.carbon, "TISSelectInputSource", C.c_int32, [C.c_void_p]),
            (self.carbon, "IsSecureEventInputEnabled", C.c_bool, []),
            (self.cf, "CFArrayGetCount", C.c_long, [C.c_void_p]),
            (self.cf, "CFArrayGetValueAtIndex", C.c_void_p, [C.c_void_p, C.c_long]),
            (self.cf, "CFStringGetCString", C.c_bool, [C.c_void_p, C.c_void_p, C.c_long, C.c_uint32]),
            (self.cf, "CFBooleanGetValue", C.c_bool, [C.c_void_p]),
            (self.cf, "CFRelease", None, [C.c_void_p]),
            (self.cf, "CFDataGetBytePtr", C.c_void_p, [C.c_void_p]),
        ]:
            f = getattr(lib, name)
            f.restype, f.argtypes = result, args
        self.carbon.UCKeyTranslate.restype = C.c_int32
        self.carbon.UCKeyTranslate.argtypes = [C.c_void_p, C.c_uint16, C.c_uint16,
            C.c_uint32, C.c_uint32, C.c_uint32, C.POINTER(C.c_uint32), C.c_uint32,
            C.POINTER(C.c_uint32), C.POINTER(C.c_uint16)]
        self.carbon.LMGetKbdType.restype = C.c_uint8

    def prop(self, source, name):
        return self.carbon.TISGetInputSourceProperty(source, C.c_void_p.in_dll(self.carbon, name))

    def string(self, value):
        if not value:
            return ""
        buf = C.create_string_buffer(2048)
        return buf.value.decode("utf-8") if self.cf.CFStringGetCString(value, buf, len(buf), UTF8) else ""

    def current(self):
        source = self.carbon.TISCopyCurrentKeyboardInputSource()
        if not source:
            return ""
        try:
            return self.string(self.prop(source, "kTISPropertyInputSourceID"))
        finally:
            self.cf.CFRelease(source)

    def all(self):
        sources = self.carbon.TISCreateInputSourceList(None, False)
        result = []
        if not sources:
            return result
        try:
            for i in range(self.cf.CFArrayGetCount(sources)):
                s = self.cf.CFArrayGetValueAtIndex(sources, i)
                sid = self.string(self.prop(s, "kTISPropertyInputSourceID"))
                enabled = self.prop(s, "kTISPropertyInputSourceIsEnabled")
                if not sid.startswith("com.apple.keylayout.") or not enabled or not self.cf.CFBooleanGetValue(enabled):
                    continue
                langs = self.prop(s, "kTISPropertyInputSourceLanguages")
                lang = self.string(self.cf.CFArrayGetValueAtIndex(langs, 0)) if langs and self.cf.CFArrayGetCount(langs) else ""
                if lang in ("en", "ru"):
                    result.append({"id": sid, "name": self.string(self.prop(s, "kTISPropertyLocalizedName")), "language": lang})
            return result
        finally:
            self.cf.CFRelease(sources)

    def _with_source(self, source_id, operation):
        sources = self.carbon.TISCreateInputSourceList(None, False)
        if not sources:
            return None
        try:
            for i in range(self.cf.CFArrayGetCount(sources)):
                source = self.cf.CFArrayGetValueAtIndex(sources, i)
                if self.string(self.prop(source, "kTISPropertyInputSourceID")) == source_id:
                    return operation(source)
            return None
        finally:
            self.cf.CFRelease(sources)

    def select(self, sid):
        return self._with_source(sid, lambda s: self.carbon.TISSelectInputSource(s)) == 0

    def _characters(self, sid):
        def read(source):
            data = self.prop(source, "kTISPropertyUnicodeKeyLayoutData")
            if not data:
                return {}
            layout = self.cf.CFDataGetBytePtr(data)
            out = {}
            for key in range(51):
                # Only letter-row keys, not Return, Tab, Space, digits or Escape.
                if key not in (0,1,2,3,4,5,6,7,8,9,11,12,13,14,15,16,17,
                               31,32,34,35,37,38,40,45,46,18,19,20,21,22,23,
                               24,25,26,27,28,29,30,33,39,41,42,43,44,47,50):
                    continue
                for shift in (0, 2):
                    dead, count = C.c_uint32(0), C.c_uint32(0)
                    chars = (C.c_uint16 * 8)()
                    err = self.carbon.UCKeyTranslate(layout, key, 0, shift,
                        self.carbon.LMGetKbdType(), 1, C.byref(dead), 8, C.byref(count), chars)
                    if err == 0 and count.value == 1:
                        out[(key, shift)] = chr(chars[0])
            return out
        return self._with_source(sid, read) or {}

    def converter(self, english, russian):
        en, ru = self._characters(english), self._characters(russian)
        pairs = {a: ru[key] for key, a in en.items() if key in ru
                 and (a.isalpha() or ru[key].isalpha()) and a != ru[key]}
        # Unsupported/non-QWERTY pairs fail closed instead of using a wrong map.
        if len(pairs) < 52:
            return None
        return LayoutConverter(pairs)

    def secure(self):
        return bool(self.carbon.IsSecureEventInputEnabled())


class AccessibilityAccessError(RuntimeError):
    pass


def attr(element, name):
    if element is None:
        return None
    err, value = A.AXUIElementCopyAttributeValue(element, name, None)
    if err == A.kAXErrorAPIDisabled:
        raise AccessibilityAccessError()
    return value if err == 0 else None


def selected_range(element):
    value = attr(element, "AXSelectedTextRange")
    if value is None:
        return None
    ok, pair = A.AXValueGetValue(value, A.kAXValueCFRangeType, None)
    return tuple(pair) if ok else None


def set_range(element, pair):
    value = A.AXValueCreate(A.kAXValueCFRangeType, pair)
    return A.AXUIElementSetAttributeValue(element, "AXSelectedTextRange", value) == 0


@dataclass
class Focus:
    state: str
    pid: int = 0
    bundle: str = ""
    element: object = None
    layout: str = ""
    role: str = ""
    reason: str = ""


class MacBackend:
    def __init__(self, settings, notify, defer, test_bundle=None):
        self.settings, self.notify, self.defer = settings, notify, defer
        self.test_bundle = test_bundle
        self.sources = InputSources()
        installed = self.sources.all()
        ids = {s["id"] for s in installed}
        for field, lang in (("english_source", "en"), ("russian_source", "ru")):
            if getattr(settings, field) not in ids:
                match = next((s["id"] for s in installed if s["language"] == lang), "")
                setattr(settings, field, match)
        converter = self.sources.converter(settings.english_source, settings.russian_source)
        self.valid_pair = converter is not None
        self.detector = Detector(settings, converter=converter)
        self.buffer = Buffer(self.detector)
        self.gesture = DoubleShift(settings.double_shift_ms / 1000)
        self.focus = Focus("permission")
        self.last_pointer_focus = None
        self.tap = None
        self.tap_source = None
        self.selection_undo = None
        self.epoch = 0
        self.last_state = None
        self.disabled = False
        self.last_error = None
        self.faulted = False
        self.events = deque(maxlen=16)
        self.drain_pending = False
        self.focus_checked = 0.0
        self.input_serial = 0
        self.edit_serial = 0
        self.edit_deadline = 0.0
        self.system = A.AXUIElementCreateSystemWide()
        A.AXUIElementSetMessagingTimeout(self.system, 0.035)

    def reload(self):
        self.valid_pair = False
        converter = self.sources.converter(self.settings.english_source, self.settings.russian_source)
        if converter:
            self.detector.converter = converter
            self.valid_pair = True
        self.gesture.interval = self.settings.double_shift_ms / 1000
        self.clear()

    def clear(self):
        self.events.clear()
        self.buffer.clear()
        self.gesture.clear()
        self.selection_undo = None
        self.epoch += 1

    def check_focus(self):
        try:
            return self._check_focus()
        except AccessibilityAccessError:
            return Focus("permission", reason="accessibility-denied")

    def _check_focus(self):
        if self.faulted:
            return Focus("error")
        sid = self.sources.current()
        if self.sources.secure():
            return Focus("secure", layout=sid)
        if not A.AXIsProcessTrusted():
            return Focus("permission", layout=sid, reason="accessibility-permission")
        if not Q.CGPreflightListenEventAccess():
            return Focus("permission", layout=sid, reason="input-monitoring-permission")
        if self.disabled:
            return Focus("paused", layout=sid)
        app = K.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return Focus("unsupported", layout=sid)
        pid, bundle = app.processIdentifier(), app.bundleIdentifier() or ""
        if self.test_bundle and bundle != self.test_bundle:
            return Focus("excluded", pid, bundle, layout=sid)
        if pid == os.getpid() or bundle in self.settings.excluded_apps:
            return Focus("excluded", pid, bundle, layout=sid)
        if not self.valid_pair or sid not in (self.settings.english_source, self.settings.russian_source):
            return Focus("layout", pid, bundle, layout=sid)
        app_ax = A.AXUIElementCreateApplication(pid)
        A.AXUIElementSetMessagingTimeout(app_ax, 0.035)
        element = attr(app_ax, "AXFocusedUIElement")
        focus = self.resolve_focus(element, pid, bundle, sid)
        if focus.state in ("active", "secure"):
            return focus
        # Some embedded editors expose the true focused node only through the
        # system-wide focus reference. Verify ownership before inspecting it.
        fallback = attr(self.system, "AXFocusedUIElement")
        if fallback is not None and fallback != element:
            err, owner = A.AXUIElementGetPid(fallback, None)
            if err == 0 and owner == pid:
                resolved = self.resolve_focus(fallback, pid, bundle, sid)
                if resolved.state in ("active", "secure"):
                    return resolved
                if not focus.role:
                    focus = resolved
        return focus

    def resolve_focus(self, element, pid, bundle, sid):
        seen = []
        role = ""
        for _ in range(4):
            if element is None:
                return Focus("unsupported", pid, bundle, layout=sid,
                             role=role, reason="no-focused-element")
            if any(element == previous for previous in seen):
                break
            seen.append(element)
            A.AXUIElementSetMessagingTimeout(element, 0.035)
            subrole = str(attr(element, "AXSubrole") or "")
            protected = attr(element, "AXProtectedContent")
            if subrole == "AXSecureTextField" or protected:
                return Focus("secure", pid, bundle, layout=sid, reason="protected-field")
            role = str(attr(element, "AXRole") or "")
            if role in ("AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"):
                # Metadata only: never read the value or walk document children.
                if selected_range(element) is None:
                    return Focus("unsupported", pid, bundle, layout=sid,
                                 role=role, reason="selection-range-unavailable")
                return Focus("active", pid, bundle, element, sid, role, "ready")
            nested = attr(element, "AXFocusedUIElement")
            if nested is None:
                return Focus("unsupported", pid, bundle, layout=sid,
                             role=role, reason="not-editable-focus")
            element = nested
        return Focus("unsupported", pid, bundle, layout=sid,
                     role=role, reason="focus-chain-limit")

    def refresh(self):
        focus = self.check_focus()
        self.focus_checked = monotonic()
        old = self.focus
        if (focus.state != "active" or focus.pid != old.pid or focus.element != old.element
                or focus.layout != old.layout):
            self.clear()
        self.focus = focus
        if monotonic() - self.buffer.changed > 30:
            self.clear()
        if self.selection_undo and monotonic() > self.selection_undo["expires"]:
            self.selection_undo = None
        state = (focus.state, focus.layout, focus.role, focus.reason, self.settings.automatic, bool(self.tap))
        if state != self.last_state:
            self.last_state = state
            self.notify(focus)
        return focus

    def start(self):
        if self.faulted:
            return False
        if self.tap or not A.AXIsProcessTrusted():
            self.refresh()
            return bool(self.tap)
        mask = sum(Q.CGEventMaskBit(x) for x in (Q.kCGEventKeyDown, Q.kCGEventFlagsChanged,
            Q.kCGEventLeftMouseDown, Q.kCGEventRightMouseDown, Q.kCGEventOtherMouseDown))
        self._callback = self.callback
        self.tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
            Q.kCGEventTapOptionListenOnly, mask, self._callback, None)
        if self.tap:
            self.tap_source = F.CFMachPortCreateRunLoopSource(None, self.tap, 0)
            F.CFRunLoopAddSource(F.CFRunLoopGetMain(), self.tap_source, F.kCFRunLoopCommonModes)
            Q.CGEventTapEnable(self.tap, True)
        self.refresh()
        return bool(self.tap)

    def stop(self):
        if self.tap_source:
            F.CFRunLoopRemoveSource(F.CFRunLoopGetMain(), self.tap_source, F.kCFRunLoopCommonModes)
            self.tap_source = None
        if self.tap:
            Q.CGEventTapEnable(self.tap, False)
            F.CFMachPortInvalidate(self.tap)
            self.tap = None
        self.clear()

    def _fault(self, reason):
        # Latch until process restart; the UI timer must never re-arm a failed tap.
        self.faulted = True
        self.disabled = True
        self.last_error = reason
        self.stop()
        self.defer(lambda: self.notify(Focus("error")), 0)

    def _switch(self, target):
        if target in ("en", "ru"):
            sid = self.settings.english_source if target == "en" else self.settings.russian_source
            self.sources.select(sid)
            # This source change belongs to our own edit and does not invalidate its undo.
            self.focus.layout = self.sources.current()

    def _can_edit(self):
        return (not self.disabled and not self.faulted and not self.sources.secure()
                and self.edit_serial == self.input_serial and monotonic() <= self.edit_deadline)

    def _replace_tail(self, proxy, edit, pending_separator=""):
        if not edit or not self._can_edit():
            return False
        # Prefer a bounded, validated AX replacement. Never erase a word with a
        # burst of Backspace events and then hope a Unicode insertion succeeds.
        element = self.focus.element
        old_range = selected_range(element)
        observed = edit.before[:-len(pending_separator)] if pending_separator else edit.before
        count = len(observed.encode("utf-16-le")) // 2
        err, writable = A.AXUIElementIsAttributeSettable(element, "AXSelectedText", None)
        if err or not writable or not old_range or old_range[1] or old_range[0] < count:
            self.buffer.clear()
            return False
        replacement_range = (old_range[0] - count, count)
        if not self._can_edit() or not set_range(element, replacement_range):
            self.buffer.clear()
            return False
        # Read only the bounded span we already observed, never the document.
        if attr(element, "AXSelectedText") != observed or not self._can_edit():
            if self._can_edit():
                set_range(element, old_range)
            self.buffer.clear()
            return False
        if A.AXUIElementSetAttributeValue(element, "AXSelectedText", edit.after) != 0:
            if self._can_edit():
                set_range(element, old_range)
            self.buffer.clear()
            return False
        if not self._can_edit():
            self.clear()
            return True  # Replacement succeeded; do not move a now-stale caret.
        end = replacement_range[0] + len(edit.after.encode("utf-16-le")) // 2
        set_range(element, (end, 0))
        self._switch(edit.target)
        return True

    def _selection(self, proxy, focus):
        if not self._can_edit():
            self.clear()
            return True
        r = selected_range(focus.element)
        if not r or r[1] == 0:
            return False
        # Explicitly selected text is read only here, after the password gate.
        if r[1] > MAX_SELECTION:
            K.NSBeep()
            return True
        before = attr(focus.element, "AXSelectedText")
        if not isinstance(before, str) or not before or len(before) > MAX_SELECTION:
            K.NSBeep()
            return True
        undo = self.selection_undo
        if (undo and undo["element"] == focus.element and undo["after"] == before
                and undo["range"] == r and monotonic() < undo["expires"]):
            after = undo["before"]
        else:
            after = self.detector.converter.convert(before)
        if before == after:
            return True
        # Unsupported editors are skipped. Never inject a fallback key stream.
        err, settable = A.AXUIElementIsAttributeSettable(focus.element, "AXSelectedText", None)
        changed = err == 0 and settable and self._can_edit() and A.AXUIElementSetAttributeValue(focus.element, "AXSelectedText", after) == 0
        if not changed:
            self.clear()
            return True
        length = len(after.encode("utf-16-le")) // 2
        new_range = (r[0], length)
        epoch, serial = self.epoch, self.input_serial
        def preserve():
            if self.epoch != epoch or self.input_serial != serial:
                return
            current = self.check_focus()
            if self.epoch == epoch and self.input_serial == serial and current.state == "active" and current.element == focus.element:
                value = A.AXValueCreate(A.kAXValueCFRangeType, new_range)
                A.AXUIElementSetAttributeValue(focus.element, "AXSelectedTextRange", value)
        self.defer(preserve, 0.08)
        self.buffer.clear()
        self.selection_undo = {"element": focus.element, "before": before, "after": after,
                               "range": new_range, "expires": monotonic() + 30}
        # Do not change layout for a selection: a mixed paragraph has no single target.
        return True

    def callback(self, proxy, event_type, event, _):
        try:
            self._handle(proxy, event_type, event)
        except Exception as error:
            self._fault(type(error).__name__)
        # A listen-only observer cannot suppress or replace system input.
        return event

    def _handle(self, proxy, event_type, event):
        if event_type in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            self._fault("EventTapStopped")
            return event
        if Q.CGEventGetIntegerValueField(event, Q.kCGEventSourceUserData) == TAG:
            return event
        self.input_serial += 1
        if event_type in (Q.kCGEventLeftMouseDown, Q.kCGEventRightMouseDown, Q.kCGEventOtherMouseDown):
            f = self.focus
            self.last_pointer_focus = Focus(f.state, f.pid, f.bundle, layout=f.layout,
                                            role=f.role, reason=f.reason)
            self.clear()
            return event
        # No AX, permission IPC, layout change, editing, or Unicode reads here.
        # Native event copies live only in a bounded queue until fresh field checks.
        if (self.disabled or self.faulted or self.focus.state != "active"
                or monotonic() - self.focus_checked > 0.75 or self.sources.secure()):
            self.clear()
            return event
        if len(self.events) == self.events.maxlen:
            self.clear()
            return event
        self.events.append((monotonic(), self.epoch, self.focus,
                            event_type, Q.CGEventCreateCopy(event)))
        if not self.drain_pending:
            self.drain_pending = True
            self.defer(self.drain_events, 0.01)
        return event

    def drain_events(self):
        self.drain_pending = False
        batch = list(self.events)
        serial = self.input_serial
        self.events.clear()
        if not batch or self.disabled or self.faulted:
            return
        try:
            focus = self.refresh()  # IPC occurs after the event callback returned.
            if focus.state != "active":
                return
            for i, (created, epoch, captured, kind, event) in enumerate(batch):
                if (monotonic() - created > 0.25 or epoch != self.epoch
                        or captured.pid != focus.pid or captured.element != focus.element
                        or captured.layout != focus.layout or self.sources.secure()):
                    self.clear()
                    return
                self.edit_serial = serial
                self.edit_deadline = created + 0.25
                self._process(kind, event, focus, i == len(batch) - 1)
                # Processing can clear context or change layout intentionally.
                if i != len(batch) - 1 and self.epoch != epoch:
                    self.clear()
                    return
        except Exception as error:
            self._fault(type(error).__name__)

    def _process(self, event_type, event, focus, allow_edit=True):
        proxy = None  # Compatibility with atomic edit helpers; never an event proxy.
        flags = Q.CGEventGetFlags(event)
        modifiers = flags & (Q.kCGEventFlagMaskCommand | Q.kCGEventFlagMaskControl | Q.kCGEventFlagMaskAlternate)
        code = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
        if event_type == Q.kCGEventFlagsChanged:
            if code in (56, 60):
                if self.gesture.update(bool(flags & Q.kCGEventFlagMaskShift), monotonic(), bool(modifiers)) and allow_edit:
                    if not self._selection(proxy, focus):
                        self._replace_tail(proxy, self.buffer.manual())
            else:
                self.gesture.clear()
            return event
        self.selection_undo = None
        self.gesture.key_used()
        if modifiers:
            self.buffer.clear()
            return event
        # If there is a selection, the following key replaces it; no old buffer is valid.
        selection = selected_range(focus.element)
        if selection and selection[1]:
            self.buffer.clear()
        if code == 51:
            self.buffer.backspace()
            return event
        if code in (36, 48, 76):
            # Return/Tab may submit or move focus. They always pass unchanged.
            self.buffer.clear()
            return event
        if code in (53, 115, 116, 117, 119, 121, 123, 124, 125, 126):
            self.buffer.clear()
            return event
        length, text = Q.CGEventKeyboardGetUnicodeString(event, 8, None, None)
        if not length or not text:
            self.buffer.clear()
            return event
        if text == " ":
            edit = self.buffer.finish(text, self.settings.automatic and allow_edit)
            if edit and self._replace_tail(proxy, edit):
                return None
            return event
        if any(ord(c) < 32 or ord(c) > 0x052F for c in text):
            self.buffer.clear()
            return event
        self.buffer.feed(text)
        return event
