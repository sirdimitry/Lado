"""macOS input adapter. No clipboard, networking, or input logging."""
from collections import deque
from dataclasses import dataclass
from contextlib import contextmanager
import ctypes as C
import os
import threading
import objc
from time import monotonic

import AppKit as K
import ApplicationServices as A
import CoreFoundation as F
import Foundation as N
import Quartz as Q

from ..engine import Buffer, Detector, DoubleShift, MAX_SELECTION
from ..layout import LayoutConverter

TAG = 0x4C41444F
UTF8 = 0x08000100

# Cross-process Accessibility calls can take far longer than a few milliseconds
# in Electron, WebKit and remote editors. The old 35 ms budget is one
# possible cause of missing focus; the actual AX error must be diagnosed.
AX_TIMEOUT = 0.45
EDIT_TIMEOUT = 0.30
PROBE_INTERVAL = 0.20
PROBE_SLOW_INTERVAL = 0.80
MAX_FOCUS_DEPTH = 4
MAX_SEARCH_NODES = 240
MAX_SEARCH_DEPTH = 12
SEARCH_DEADLINE = 0.65
MAX_VALUE_UNITS = 16384

TEXT_ROLES = {"AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"}
# Containers that can hold the real focused editor without being editors themselves.
CONTAINER_ROLES = {
    "AXApplication", "AXWindow", "AXSheet", "AXDrawer", "AXGroup",
    "AXScrollArea", "AXWebArea", "AXSplitGroup", "AXTabGroup",
    "AXList", "AXOutline", "AXTable", "AXRow", "AXCell", "AXBox",
}
# Never treat these as an editable target even if they expose a selection.
NON_EDITABLE_ROLES = {
    "AXStaticText", "AXButton", "AXMenu", "AXMenuItem", "AXMenuBar",
    "AXLink", "AXImage", "AXHeading", "AXList", "AXTable", "AXRow",
    "AXCell", "AXScrollArea", "AXWindow", "AXSheet", "AXApplication",
}


_ax_context = threading.local()


class AXDeadlineExceeded(RuntimeError):
    pass


@contextmanager
def ax_deadline(deadline):
    previous = getattr(_ax_context, "deadline", None)
    _ax_context.deadline = min(previous, deadline) if previous else deadline
    try:
        yield
    finally:
        _ax_context.deadline = previous


def same_element(left, right):
    if left is right:
        return True
    if left is None or right is None:
        return False
    try:
        return F.CFEqual(left, right) is True
    except (TypeError, ValueError):
        return False


def utf16_slice(text, start, size):
    if start < 0 or size < 0:
        return None
    raw = text.encode("utf-16-le")
    a, z = start * 2, (start + size) * 2
    if z > len(raw):
        return None
    try:
        return raw[:a].decode("utf-16-le"), raw[a:z].decode("utf-16-le"), raw[z:].decode("utf-16-le")
    except UnicodeDecodeError:
        return None  # Never split a surrogate pair.


def utf16_units(text):
    return len(text.encode("utf-16-le")) // 2


def observed_replacement(actual, expected, replacement):
    """Keep WebKit's space representation without relaxing letter matching."""
    if actual == expected:
        return replacement
    if not isinstance(actual, str) or len(actual) != len(expected) or len(replacement) != len(expected):
        return None
    result = list(replacement)
    for i, (found, wanted) in enumerate(zip(actual, expected)):
        if found == wanted:
            continue
        if found != "\u00a0" or wanted != " " or replacement[i] != " ":
            return None
        result[i] = found
    return "".join(result)


def _settable(result):
    """Normalise PyObjC's (error, bool) tuple and tolerate plain booleans."""
    if isinstance(result, tuple):
        error, value = (result + (0, None))[:2]
        return error == 0 and isinstance(value, bool) and value
    return isinstance(result, bool) and result


class InputSources:
    """Small ctypes bridge to Apple's Text Input Source Services."""

    def __init__(self):
        self._current_id = ""
        self._secure_input = False
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
        self._require_main_thread()
        return self.carbon.TISGetInputSourceProperty(source, C.c_void_p.in_dll(self.carbon, name))

    @staticmethod
    def _require_main_thread():
        # HIToolbox aborts (not a catchable Python exception) when a changed
        # source list is validated from a worker on recent macOS versions.
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("input-sources-require-main-thread")

    def string(self, value):
        if not value:
            return ""
        buf = C.create_string_buffer(2048)
        return buf.value.decode("utf-8") if self.cf.CFStringGetCString(value, buf, len(buf), UTF8) else ""

    def current(self):
        if threading.current_thread() is not threading.main_thread():
            return self._current_id
        source = self.carbon.TISCopyCurrentKeyboardInputSource()
        if not source:
            self._current_id = ""
            return ""
        try:
            self._current_id = self.string(self.prop(source, "kTISPropertyInputSourceID"))
            return self._current_id
        finally:
            self.cf.CFRelease(source)

    def all(self):
        self._require_main_thread()
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
        self._require_main_thread()
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
        if threading.current_thread() is threading.main_thread():
            self._secure_input = bool(self.carbon.IsSecureEventInputEnabled())
        return self._secure_input


class AccessibilityAccessError(RuntimeError):
    pass


def attr(element, name):
    if element is None:
        return None
    set_timeout(element)
    err, value = A.AXUIElementCopyAttributeValue(element, name, None)
    if err and name in ("AXFocusedUIElement", "AXFocusedWindow"):
        _ax_context.error = (name, int(err))
    if err == A.kAXErrorAPIDisabled:
        raise AccessibilityAccessError()
    return value if err == 0 else None


def set_timeout(element, timeout=AX_TIMEOUT):
    deadline = getattr(_ax_context, "deadline", None)
    if deadline is not None:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise AXDeadlineExceeded()
        timeout = min(timeout, remaining)
    if element is not None:
        try:
            A.AXUIElementSetMessagingTimeout(element, timeout)
        except Exception:
            pass


def selected_range(element):
    value = attr(element, "AXSelectedTextRange")
    if value is None:
        return None
    ok, pair = A.AXValueGetValue(value, A.kAXValueCFRangeType, None)
    return tuple(pair) if ok else None


def children(element, limit=80):
    """Bound the remote array itself, rather than copying every child first."""
    set_timeout(element)
    err, count = A.AXUIElementGetAttributeValueCount(element, "AXChildren", None)
    if err == A.kAXErrorAPIDisabled:
        raise AccessibilityAccessError()
    if err or count <= 0:
        return []
    set_timeout(element)
    err, values = A.AXUIElementCopyAttributeValues(
        element, "AXChildren", 0, min(int(count), limit), None)
    if err == A.kAXErrorAPIDisabled:
        raise AccessibilityAccessError()
    return list(values or [])[:limit] if err == 0 else []


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
    mode: str = "range"


class MacBackend:
    def __init__(self, settings, notify, defer, test_bundle=None):
        self.settings, self.notify, self.defer = settings, notify, defer
        self.test_bundle = test_bundle
        self.sources = InputSources()
        self._source_id = self.sources.current()
        self.sources.secure()
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
        self.last_ax_error = 0
        self.last_replacement = "none"
        self.faulted = False
        self.events = deque(maxlen=16)
        self.drain_pending = False
        self.focus_checked = 0.0
        self.focus_required = 0.0
        self.input_serial = 0
        self.edit_serial = 0
        self.edit_deadline = 0.0
        self.system = A.AXUIElementCreateSystemWide()
        set_timeout(self.system, AX_TIMEOUT)

        # A background probe keeps all cross-process AX queries off the UI and
        # event-tap threads. The main thread only consumes the latest snapshot.
        self._probe_lock = threading.Lock()
        self._probe_wake = threading.Event()
        self._probe_stop = threading.Event()
        self._probe_focus = None
        self._probe_at = 0.0
        self._probe_thread = None
        self._focus_generation = 0
        self._workspace_token = None
        self._frontmost_app = None
        self._web_attempts = {}
        self._cached_editor = None

    # -- settings / lifecycle -------------------------------------------------

    def reload(self):
        self.valid_pair = False
        converter = self.sources.converter(self.settings.english_source, self.settings.russian_source)
        if converter:
            self.detector.converter = converter
            self.valid_pair = True
        self.gesture.interval = self.settings.double_shift_ms / 1000
        self.clear()
        self._wake_probe()

    def clear(self):
        self.events.clear()
        self.buffer.clear()
        self.gesture.clear()
        self.selection_undo = None
        self.epoch += 1

    def set_frontmost(self, app):
        with self._probe_lock:
            self._frontmost_app = app
            self._focus_generation += 1
            self.focus_required = monotonic()
        self._wake_probe()

    def _wake_probe(self):
        wake = getattr(self, "_probe_wake", None)
        if wake is not None:
            wake.set()

    def start_probe(self):
        lock = getattr(self, "_probe_lock", None)
        if lock is None:
            return
        with lock:
            if self._probe_thread and self._probe_thread.is_alive():
                self._wake_probe()
                return
            self._probe_stop.clear()
            thread = threading.Thread(target=self._probe_loop, name="lado-focus", daemon=True)
            self._probe_thread = thread
        self._install_workspace_observer()
        thread.start()

    def _probe_loop(self):
        while not self._probe_stop.is_set():
            started = monotonic()
            with self._probe_lock:
                generation = getattr(self, "_focus_generation", 0)
            try:
                with objc.autorelease_pool(), ax_deadline(started + 0.8):
                    focus = self.check_focus()
            except Exception:
                focus = Focus("unsupported", reason="focus-probe-failed")
            with self._probe_lock:
                if self._probe_stop.is_set():
                    return
                if generation == getattr(self, "_focus_generation", 0):
                    self._probe_focus = focus
                    # Age includes the entire IPC operation, not just publication.
                    self._probe_at = started
            delay = PROBE_INTERVAL if monotonic() - started < 0.25 else PROBE_SLOW_INTERVAL
            self._probe_wake.wait(delay)
            self._probe_wake.clear()

    def stop_probe(self):
        stop = getattr(self, "_probe_stop", None)
        if stop is None:
            return
        stop.set()
        self._wake_probe()
        thread = self._probe_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        # A slow worker still owns this stop event. Do not clear it or spawn a
        # second worker until the old one has actually exited.
        if not thread or not thread.is_alive():
            self._probe_thread = None
        token = getattr(self, "_workspace_token", None)
        if token:
            try:
                K.NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(token)
            except Exception:
                pass
            self._workspace_token = None

    def _install_workspace_observer(self):
        if getattr(self, "_workspace_token", None):
            return
        try:
            def changed(note):
                try:
                    app = note.userInfo().get(K.NSWorkspaceApplicationKey)
                except Exception:
                    app = None
                self.set_frontmost(app)
            self._workspace_token = (
                K.NSWorkspace.sharedWorkspace().notificationCenter()
                .addObserverForName_object_queue_usingBlock_(
                    K.NSWorkspaceDidActivateApplicationNotification, None,
                    N.NSOperationQueue.mainQueue(), changed)
            )
        except Exception:
            self._workspace_token = None

    def _snapshot(self):
        lock = getattr(self, "_probe_lock", None)
        if lock is None:
            return None, 0.0
        with lock:
            return self._probe_focus, self._probe_at

    # -- focus ----------------------------------------------------------------

    def check_focus(self):
        _ax_context.error = None
        self.last_ax_error = 0
        try:
            result = self._check_focus()
            error = _ax_context.error
            if result.state == "unsupported" and error:
                self.last_ax_error = error[1]
                result.reason += ":" + error[0] + ":" + str(error[1])
            return result
        except AXDeadlineExceeded:
            self.last_ax_error = -25204
            return Focus("unsupported", reason="focus-probe-timeout")
        except AccessibilityAccessError:
            return Focus("permission", reason="accessibility-denied")
        except Exception as error:
            return Focus("unsupported", reason="focus-check-" + type(error).__name__)

    def _frontmost(self):
        app = getattr(self, "_frontmost_app", None)
        try:
            if app is not None and not app.isTerminated():
                return app
        except Exception:
            pass
        return K.NSWorkspace.sharedWorkspace().frontmostApplication()

    def _check_focus(self):
        if self.faulted:
            return Focus("error", reason=self.last_error or "faulted")
        sid = self.sources.current()
        if self.sources.secure():
            return Focus("secure", layout=sid, reason="secure-input")
        if not A.AXIsProcessTrusted():
            return Focus("permission", layout=sid, reason="accessibility-permission")
        if not Q.CGPreflightListenEventAccess():
            return Focus("permission", layout=sid, reason="input-monitoring-permission")
        if self.disabled:
            return Focus("paused", layout=sid)
        app = self._frontmost()
        if app is None:
            return Focus("unsupported", layout=sid, reason="no-frontmost-application")
        pid, bundle = app.processIdentifier(), app.bundleIdentifier() or ""
        if self.test_bundle and bundle != self.test_bundle:
            return Focus("excluded", pid, bundle, layout=sid, reason="compatibility-scope")
        if pid == os.getpid() or bundle in self.settings.excluded_apps:
            return Focus("excluded", pid, bundle, layout=sid, reason="excluded-application")
        if not self.valid_pair or sid not in (self.settings.english_source, self.settings.russian_source):
            return Focus("layout", pid, bundle, layout=sid, reason="layout-outside-pair")
        app_ax = A.AXUIElementCreateApplication(pid)
        set_timeout(app_ax, AX_TIMEOUT)
        element = self._focused_node(app_ax)
        focus = self.resolve_focus(element, pid, bundle, sid)
        if focus.state in ("active", "secure"):
            return focus
        # Some embedded editors expose the true focused node only through the
        # system-wide focus reference. Verify ownership before inspecting it.
        fallback = attr(self.system, "AXFocusedUIElement")
        if fallback is not None and not same_element(fallback, element):
            err, owner = A.AXUIElementGetPid(fallback, None)
            if err == 0 and owner == pid:
                resolved = self.resolve_focus(fallback, pid, bundle, sid)
                if resolved.state in ("active", "secure"):
                    return resolved
                if not focus.role:
                    focus = resolved
        # Chromium/Electron only builds its accessibility tree when asked.
        if focus.role not in ("AXMenu", "AXMenuItem", "AXMenuBar"):
            if self._enable_web_accessibility(app_ax, pid, bundle):
                element = self._focused_node(app_ax)
                retry = self.resolve_focus(element, pid, bundle, sid)
                if retry.state in ("active", "secure"):
                    return retry
                if retry.role in TEXT_ROLES:
                    focus = retry
            cached = getattr(self, "_cached_editor", None)
            if cached and cached[0] == pid and attr(cached[1], "AXFocused") is True:
                resolved = self.resolve_focus(cached[1], pid, bundle, sid)
                if resolved.state in ("active", "secure"):
                    return resolved
            searched = self._search_focused(app_ax, pid, bundle, sid)
            if searched is not None:
                if searched.state in ("active", "secure"):
                    self._cached_editor = (pid, searched.element) if searched.state == "active" else None
                    return searched
                if searched.role in TEXT_ROLES:
                    focus = searched
        return focus

    def _focused_node(self, app_ax):
        element = attr(app_ax, "AXFocusedUIElement")
        if element is not None:
            return element
        window = attr(app_ax, "AXFocusedWindow")
        if window is not None:
            set_timeout(window)
            nested = attr(window, "AXFocusedUIElement")
            if nested is not None:
                return nested
        return None

    def _value_capable(self, element):
        if not getattr(self.settings, "value_fallback", False):
            return False
        return _settable(A.AXUIElementIsAttributeSettable(element, "AXValue", None))

    def _custom_editable(self, element, role):
        if role != "AXWebArea" or role in NON_EDITABLE_ROLES:
            return None
        if selected_range(element) is None:
            return None
        if _settable(A.AXUIElementIsAttributeSettable(element, "AXSelectedText", None)):
            return "range"
        if self._value_capable(element):
            return "value"
        return None

    def resolve_focus(self, element, pid, bundle, sid):
        seen = []
        role = ""
        for _ in range(MAX_FOCUS_DEPTH):
            if element is None:
                return Focus("unsupported", pid, bundle, layout=sid, role=role,
                             reason="no-focused-element")
            if any(same_element(element, previous) for previous in seen):
                break
            seen.append(element)
            set_timeout(element)
            subrole = str(attr(element, "AXSubrole") or "")
            protected = attr(element, "AXProtectedContent")
            if subrole == "AXSecureTextField" or protected:
                return Focus("secure", pid, bundle, layout=sid, role=subrole,
                             reason="protected-field")
            role = str(attr(element, "AXRole") or "")
            if role in TEXT_ROLES:
                # Metadata only: never read the value or walk document children.
                if selected_range(element) is not None:
                    return Focus("active", pid, bundle, element, sid, role, "ready", "range")
                return Focus("unsupported", pid, bundle, layout=sid, role=role,
                             reason="selection-range-unavailable")
            mode = self._custom_editable(element, role)
            if mode:
                return Focus("active", pid, bundle, element, sid, role,
                             "custom-editor", mode)
            nested = attr(element, "AXFocusedUIElement")
            if nested is None:
                return Focus("unsupported", pid, bundle, layout=sid, role=role,
                             reason="not-editable-focus")
            element = nested
        return Focus("unsupported", pid, bundle, layout=sid, role=role,
                     reason="focus-chain-limit")

    def _enable_web_accessibility(self, app_ax, pid, bundle):
        """Ask Chromium/Electron and WebKit to expose the accessibility tree."""
        key = (pid, bundle)
        attempts_map = getattr(self, "_web_attempts", None)
        if attempts_map is None:
            attempts_map = self._web_attempts = {}
        attempts = attempts_map.get(key, 0)
        if attempts >= 2 or len(attempts_map) > 128:
            return False
        attempts_map[key] = attempts + 1
        changed = False
        try:
            if A.AXUIElementSetAttributeValue(app_ax, "AXManualAccessibility", True) == 0:
                changed = True
        except Exception:
            pass
        # Native WebKit hosts may not implement Electron's manual attribute.
        # Ask the standard enhanced-accessibility capability only if the first
        # mechanism was unsupported; never repeatedly toggle a working editor.
        if not changed:
            try:
                if A.AXUIElementSetAttributeValue(app_ax, "AXEnhancedUserInterface", True) == 0:
                    changed = True
            except Exception:
                pass
        return changed

    def _node_key(self, node):
        try:
            return int(F.CFHash(node))
        except Exception:
            return id(node)

    def _search_focused(self, app_ax, pid, bundle, sid):
        """Bounded search for the focused node inside the focused window.

        Only roles and AXChildren are inspected. Values and selections are read
        only after a node reports AXFocused and is about to become the target.
        """
        start = attr(app_ax, "AXFocusedWindow") or app_ax
        set_timeout(start)
        queue = deque([(start, 0)])
        seen = set()
        unsupported = None
        deadline = monotonic() + SEARCH_DEADLINE
        budget = MAX_SEARCH_NODES
        while queue and budget > 0 and monotonic() < deadline:
            node, depth = queue.popleft()
            key = self._node_key(node)
            if key in seen:
                continue
            seen.add(key)
            budget -= 1
            role = str(attr(node, "AXRole") or "")
            if attr(node, "AXFocused") and role not in NON_EDITABLE_ROLES:
                resolved = self.resolve_focus(node, pid, bundle, sid)
                if resolved.state in ("active", "secure"):
                    return resolved
                if resolved.role in TEXT_ROLES:
                    unsupported = resolved
            if role in TEXT_ROLES:
                continue
            if role not in CONTAINER_ROLES or depth >= MAX_SEARCH_DEPTH:
                continue
            for child in children(node):
                set_timeout(child)
                queue.append((child, depth + 1))
        return unsupported

    def refresh(self):
        # Only the main run loop talks to Text Input Source Services. Workers
        # consume its string snapshot; AX RPC remains on the probe thread.
        if hasattr(self, "_source_id"):
            sid = self.sources.current()
            if sid != self._source_id:
                self._source_id = sid
                with self._probe_lock:
                    self._focus_generation += 1
                    self.focus_required = monotonic()
                self._wake_probe()
            self.sources.secure()
        focus, at = self._snapshot()
        if focus is None:
            if getattr(self, "_probe_lock", None) is None:
                focus = self.check_focus()  # Explicit unit-test backend, no worker.
                at = monotonic()
            elif not A.AXIsProcessTrusted():
                focus = Focus("permission", reason="accessibility-permission")
            elif not Q.CGPreflightListenEventAccess():
                focus = Focus("permission", reason="input-monitoring-permission")
            else:
                focus = Focus("unsupported", reason="probe-starting")
        elif (monotonic() - at > 1.0 or at < getattr(self, "focus_required", 0.0)):
            # Keep the old field identity for queued native event copies until
            # the fresh probe arrives. Never decode or edit using this snapshot.
            self.focus_checked = at
            return Focus("unsupported", focus.pid, focus.bundle, layout=focus.layout,
                         role=focus.role, reason="probe-stale")
        self.focus_checked = at
        old = self.focus
        # Compare semantic identity, not object identity: web editors often
        # return a fresh AX wrapper for the same field on every query.
        changed = (focus.state != old.state or focus.pid != old.pid
                   or focus.layout != old.layout or focus.role != old.role
                   or not same_element(focus.element, old.element))
        if focus.state != "active" or changed:
            self.clear()
        self.focus = focus
        if monotonic() - self.buffer.changed > 30:
            self.clear()
        if self.selection_undo and monotonic() > self.selection_undo["expires"]:
            self.selection_undo = None
        state = (focus.state, focus.pid, focus.layout, focus.role, focus.reason,
                 focus.mode, self.settings.automatic, bool(self.tap), self.faulted)
        if state != self.last_state:
            self.last_state = state
            self.notify(focus)
        return focus

    # -- tap ------------------------------------------------------------------

    def start(self):
        if self.faulted:
            return False
        if self.tap or not A.AXIsProcessTrusted():
            self.refresh()
            return bool(self.tap)
        if not Q.CGPreflightListenEventAccess():
            self.refresh()
            return False
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

    def stop_tap(self):
        if self.tap_source:
            F.CFRunLoopRemoveSource(F.CFRunLoopGetMain(), self.tap_source, F.kCFRunLoopCommonModes)
            self.tap_source = None
        if self.tap:
            Q.CGEventTapEnable(self.tap, False)
            F.CFMachPortInvalidate(self.tap)
            self.tap = None
        self.clear()

    def stop(self):
        self.stop_tap()
        self.stop_probe()

    def restart(self):
        """User-requested recovery from a latched observer fault."""
        self.faulted = False
        self.disabled = False
        self.last_error = None
        self.last_ax_error = 0
        self.focus_required = monotonic()
        self.clear()
        self.start_probe()
        self._wake_probe()
        ok = self.start()
        self.refresh()
        return ok

    def _fault(self, reason):
        # Latch until the user explicitly restarts input; the UI timer must
        # never re-arm a failed tap on its own.
        if self.faulted:
            return
        self.faulted = True
        self.disabled = True
        self.last_error = reason
        self.stop_tap()
        self._wake_probe()
        self.defer(lambda: self.notify(Focus("error", reason=reason)), 0)

    # -- editing --------------------------------------------------------------

    def _can_edit(self):
        return (not self.disabled and not self.faulted and self.focus.state == "active"
                and not self.sources.secure() and self.edit_serial == self.input_serial
                and monotonic() <= self.edit_deadline
                and monotonic() - self.focus_checked <= 1.0
                and self.focus_checked + 0.001 >= getattr(self, "focus_required", 0.0))

    def _confirm_target(self, element):
        if not self._can_edit():
            return False
        current = self.check_focus()
        return (self._can_edit() and current.state == "active"
                and current.pid == self.focus.pid
                and current.layout == self.focus.layout
                and same_element(current.element, element))

    def _edit_target_is_text(self, element):
        """Re-check protection immediately before a bounded value read."""
        try:
            if str(attr(element, "AXSubrole") or "") == "AXSecureTextField":
                return False
            if attr(element, "AXProtectedContent"):
                return False
        except AccessibilityAccessError:
            return False
        return True

    def _replace_tail(self, proxy, edit, pending_separator="", explicit=False):
        if not edit or not self._can_edit():
            self.last_replacement = "no-edit-or-stale-input"
            return False
        # Prefer a bounded, validated AX replacement. Never erase a word with a
        # burst of Backspace events and then hope a Unicode insertion succeeds.
        element = self.focus.element
        if element is None or not self._confirm_target(element):
            self.last_replacement = "target-changed"
            self.buffer.clear()
            return False
        observed = edit.before[:-len(pending_separator)] if pending_separator else edit.before
        count = utf16_units(observed)
        if count <= 0:
            return False
        old_range = selected_range(element)
        if self._range_replacement(element, edit, observed, old_range):
            return True
        if explicit and getattr(self.settings, "value_fallback", False):
            if self._value_replacement(element, edit, observed, old_range):
                return True
        self.buffer.clear()
        return False

    def _range_replacement(self, element, edit, observed, old_range):
        count = utf16_units(observed)
        if not old_range or old_range[1] or old_range[0] < count:
            self.last_replacement = "caret-range-unavailable"
            return False
        err, writable = A.AXUIElementIsAttributeSettable(element, "AXSelectedText", None)
        if err or not writable:
            self.last_replacement = "selected-text-not-writable:" + str(int(err))
            return False
        replacement_range = (old_range[0] - count, count)
        if not self._can_edit() or not set_range(element, replacement_range):
            self.last_replacement = "selection-write-failed"
            return False
        # Read only the bounded span we already observed, never the document.
        replacement = observed_replacement(attr(element, "AXSelectedText"), observed, edit.after)
        if replacement is None or not self._can_edit():
            self.last_replacement = "observed-span-mismatch"
            if self._can_edit():
                set_range(element, old_range)
            return False
        if not self._write_selected(element, replacement):
            self.last_replacement = "selected-text-write-failed"
            if self._can_edit():
                set_range(element, old_range)
            return False
        if not self._can_edit():
            self.clear()
            return True  # Replacement succeeded; do not move a now-stale caret.
        self.last_replacement = "range-replaced"
        end = replacement_range[0] + utf16_units(replacement)
        set_range(element, (end, 0))
        self._switch(edit.target)
        return True

    def _write_selected(self, element, text):
        """Use WebKit's range operation when its selected-text setter is a no-op.

        The caller has already validated the bounded selection and protection.
        Opaque markers stay inside AX; no document search or value read is used.
        """
        marker = attr(element, "AXSelectedTextMarkerRange")
        if marker is not None and not isinstance(marker, (str, bytes, int, float, bool)) and self._can_edit():
            set_timeout(element)
            err, result = A.AXUIElementCopyParameterizedAttributeValue(element, "AXTextOperation", {
                "AXTextOperationMarkerRanges": [marker],
                "AXTextOperationType": "AXTextOperationReplace",
                "AXTextOperationReplacementString": text,
                "AXTextOperationSmartReplace": False,
            }, None)
            if err == 0:
                self.last_replacement = "web-range-operation"
                return bool(result)
            # Only an explicitly unsupported operation may use the ordinary
            # setter. An ambiguous error must not trigger a second write.
            if err not in (A.kAXErrorAttributeUnsupported, A.kAXErrorParameterizedAttributeUnsupported):
                return False
        return self._can_edit() and A.AXUIElementSetAttributeValue(element, "AXSelectedText", text) == 0

    def _value_replacement(self, element, edit, observed, old_range):
        """Bounded AXValue fallback for editors that expose no writable selection.

        The field length is checked before reading. The observed word must be the
        exact tail of the current value (or the caret must already be at its end),
        so editing in the middle of a large document is never attempted.
        """
        if not self._can_edit() or old_range is None:
            return False
        if not _settable(A.AXUIElementIsAttributeSettable(element, "AXValue", None)):
            return False
        if not self._edit_target_is_text(element):
            self.buffer.clear()
            return False
        length = attr(element, "AXNumberOfCharacters")
        try:
            length = int(length)
        except (TypeError, ValueError):
            return False
        if length < 0 or length > MAX_VALUE_UNITS:
            return False
        value = attr(element, "AXValue")
        if not isinstance(value, str) or not value:
            return False
        if utf16_units(value) != length or length > MAX_VALUE_UNITS:
            return False
        if old_range is not None:
            # With a caret, only the end of the field is safe without replacing
            # a range the user may be editing inside.
            if old_range[1] != 0 or old_range[0] != length:
                return False
        if not value.endswith(edit.before):
            return False
        new_value = value[:-len(edit.before)] + edit.after
        if (not self._can_edit() or attr(element, "AXValue") != value
                or selected_range(element) != old_range or not self._edit_target_is_text(element)):
            return False
        if not self._can_edit():
            return False
        if A.AXUIElementSetAttributeValue(element, "AXValue", new_value) != 0:
            return False
        check = attr(element, "AXValue")
        if check != new_value:
            self.buffer.clear()
            return False
        if old_range is not None and self._can_edit():
            set_range(element, (utf16_units(new_value), 0))
        self._switch(edit.target)
        return True

    def _selection(self, proxy, focus):
        if not self._can_edit():
            self.clear()
            return True
        element = focus.element
        if element is None or not self._confirm_target(element):
            return True
        r = selected_range(element)
        if not r or r[1] == 0:
            return False
        # Explicitly selected text is read only here, after the password gate.
        if r[1] > MAX_SELECTION:
            K.NSBeep()
            return True
        before = attr(element, "AXSelectedText")
        if not isinstance(before, str) or not before or len(before) > MAX_SELECTION:
            K.NSBeep()
            return True
        undo = self.selection_undo
        if (undo and undo["element"] == element and undo["after"] == before
                and undo["range"] == r and monotonic() < undo["expires"]):
            after = undo["before"]
        else:
            after = self.detector.converter.convert(before)
        if before == after:
            return True
        err, settable = A.AXUIElementIsAttributeSettable(element, "AXSelectedText", None)
        changed = False
        if err == 0 and settable and self._can_edit():
            changed = self._write_selected(element, after)
        if not changed and getattr(self.settings, "value_fallback", False):
            changed = self._value_selection(element, r, before, after)
        if not changed:
            self.clear()
            return True
        length = utf16_units(after)
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
        self.selection_undo = {"element": element, "before": before, "after": after,
                               "range": new_range, "expires": monotonic() + 30}
        # Do not change layout for a selection: a mixed paragraph has no single target.
        return True

    def _value_selection(self, element, r, before, after):
        if not self._can_edit() or not self._edit_target_is_text(element):
            return False
        if not _settable(A.AXUIElementIsAttributeSettable(element, "AXValue", None)):
            return False
        length = attr(element, "AXNumberOfCharacters")
        try:
            length = int(length)
        except (TypeError, ValueError):
            return False
        if length < 0 or length > MAX_VALUE_UNITS:
            return False
        value = attr(element, "AXValue")
        if not isinstance(value, str) or utf16_units(value) > MAX_VALUE_UNITS:
            return False
        span = utf16_slice(value, *r)
        if span is None or span[1] != before or utf16_units(value) != length:
            return False
        new_value = span[0] + after + span[2]
        if (attr(element, "AXValue") != value or selected_range(element) != r
                or not self._edit_target_is_text(element)):
            return False
        if not self._can_edit():
            return False
        if A.AXUIElementSetAttributeValue(element, "AXValue", new_value) != 0:
            return False
        return attr(element, "AXValue") == new_value

    def _switch(self, target):
        if target in ("en", "ru"):
            sid = self.settings.english_source if target == "en" else self.settings.russian_source
            self.sources.select(sid)
            # This source change belongs to our own edit and does not invalidate its undo.
            self.focus.layout = self.sources.current()
            self._source_id = self.focus.layout
            lock = getattr(self, "_probe_lock", None)
            if lock is not None:
                with lock:
                    self._focus_generation += 1
                    self._probe_focus = self.focus
                    self._probe_at = monotonic()
                self._wake_probe()

    # -- event stream ---------------------------------------------------------

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
            # A click can move the caret or change the field. Do not perform an
            # AX edit until a probe taken after this moment has arrived.
            self.focus_required = monotonic()
            lock = getattr(self, "_probe_lock", None)
            if lock is not None:
                with lock:
                    self._focus_generation += 1
            self._wake_probe()
            self.clear()
            return event
        # No AX, permission IPC, layout change, editing, or Unicode reads here.
        # Native event copies live only in a bounded queue until fresh field checks.
        if (self.disabled or self.faulted or self.focus.state != "active"
                or monotonic() - self.focus_checked > 1.0 or self.sources.secure()):
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
            focus = self.refresh()  # Uses the background snapshot; no UI-thread AX IPC.
            if focus.reason in ("probe-stale", "probe-starting"):
                if monotonic() - batch[0][0] <= 0.25:
                    self.events.extendleft(reversed(batch))
                    self.drain_pending = True
                    self._wake_probe()
                    self.defer(self.drain_events, 0.01)
                else:
                    self.clear()
                return
            if focus.state != "active":
                return
            if self.focus_checked + 0.001 < getattr(self, "focus_required", 0.0):
                self.clear()
                return
            for i, (created, epoch, captured, kind, event) in enumerate(batch):
                flags_only = kind == Q.kCGEventFlagsChanged
                if (monotonic() - created > 0.25 or (epoch != self.epoch and not flags_only)
                        or captured.pid != focus.pid or not same_element(captured.element, focus.element)
                        or (captured.layout != focus.layout and not flags_only) or self.sources.secure()):
                    self.clear()
                    return
                self.edit_serial = serial
                self.edit_deadline = created + EDIT_TIMEOUT
                with ax_deadline(self.edit_deadline):
                    self._process(kind, event, focus, i == len(batch) - 1)
                # Processing can clear context or change layout intentionally.
                if i != len(batch) - 1 and self.epoch != epoch and not flags_only:
                    self.clear()
                    return
        except AXDeadlineExceeded:
            self.clear()
            self._wake_probe()
        except AccessibilityAccessError:
            # Permission was revoked mid-session. Keep the observer latched off
            # but do not require a process restart; the menu can re-arm it.
            self._fault("AccessibilityDenied")
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
                        self._replace_tail(proxy, self.buffer.manual(), explicit=True)
            else:
                self.gesture.clear()
            return event
        self.selection_undo = None
        self.gesture.key_used()
        if modifiers:
            self.buffer.clear()
            return event
        # The buffer is already cleared by every action that can create a
        # selection (mouse click, Shift+arrows, Cmd+A, Tab, Return). Avoiding a
        # per-keystroke AX range read keeps the main run loop responsive.
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
