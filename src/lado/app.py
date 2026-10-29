"""A native, intentionally small menu-bar interface."""
import os
from pathlib import Path
import plistlib
import sys

import AppKit as K
import ApplicationServices as A
import Foundation as N
import Quartz as Q
import objc

from . import __version__
from .settings import load, save
from .platforms.macos import MacBackend
from .updates import UpdateService, trusted_download

RUSSIAN = str(N.NSLocale.preferredLanguages()[0]).startswith("ru")


def t(ru, en):
    return ru if RUSSIAN else en


def resource(name):
    return str(Path(__file__).parent / "resources" / name)


def label(text, frame, size=13, color=None, bold=False):
    view = K.NSTextField.labelWithString_(text)
    view.setFrame_(frame)
    view.setFont_(K.NSFont.boldSystemFontOfSize_(size) if bold else K.NSFont.systemFontOfSize_(size))
    if color:
        view.setTextColor_(color)
    view.setLineBreakMode_(K.NSLineBreakByWordWrapping)
    view.setMaximumNumberOfLines_(0)
    return view


def button(text, frame, target, action):
    b = K.NSButton.alloc().initWithFrame_(frame)
    b.setTitle_(text)
    b.setBezelStyle_(K.NSBezelStyleRounded)
    b.setTarget_(target)
    b.setAction_(action)
    return b


def status_image(code, locked=False):
    """One compact indicator; the lock is part of the same image."""
    image = K.NSImage.alloc().initWithSize_((24, 18))
    image.lockFocus()
    attributes = {K.NSFontAttributeName: K.NSFont.monospacedSystemFontOfSize_weight_(12, K.NSFontWeightSemibold),
                  K.NSForegroundColorAttributeName: K.NSColor.blackColor()}
    text = N.NSAttributedString.alloc().initWithString_attributes_(code, attributes)
    text.drawAtPoint_((1, 2))
    if locked:
        lock = K.NSImage.imageWithSystemSymbolName_accessibilityDescription_("lock.fill", "Secure input")
        if lock:
            lock.drawInRect_fromRect_operation_fraction_(((13, 0), (8, 8)), ((0, 0), (0, 0)),
                K.NSCompositingOperationSourceOver, 1.0)
    image.unlockFocus()
    image.setTemplate_(True)
    return image


STATES = {
    "active": ("Готово", "Ready"),
    "secure": ("Защищённый ввод — Lado отключён", "Secure input — Lado is inactive"),
    "permission": ("Нужен доступ в настройках macOS", "Permission needed in macOS Settings"),
    "paused": ("На паузе", "Paused"),
    "excluded": ("Отключено в этом приложении", "Disabled in this application"),
    "layout": ("Активная раскладка вне выбранной пары", "Active layout is outside your pair"),
    "unsupported": ("Нет поддерживаемого текстового поля", "No supported text field focused"),
    "error": ("Обработка остановлена. Перезапустите Lado", "Processing stopped. Restart Lado"),
}


class LadoDelegate(N.NSObject):
    def applicationDidFinishLaunching_(self, _):
        self.settings = load()
        self.windows = []
        self.pending = []
        self.preferences = None
        self.about = None
        self.available_update = None
        self.pending_update = None
        self.seen_updates = set()
        self.update_service = UpdateService(__version__)
        test_bundle = "com.sirdimitry.lado-testpad" if "--compatibility-test" in sys.argv else None
        self.backend = MacBackend(self.settings, self.updateStatus_, self.defer, test_bundle=test_bundle)
        main = K.NSMenu.alloc().init()
        root_item = K.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Lado", None, "")
        main.addItem_(root_item)
        app_menu = K.NSMenu.alloc().initWithTitle_("Lado")
        root_item.setSubmenu_(app_menu)
        for title, action, key in ((t("О Lado…", "About Lado…"), "showAbout:", ""),
                                   (t("Настройки…", "Settings…"), "showPreferences:", ","),
                                   (t("Закрыть окно", "Close Window"), "closeWindow:", "w"),
                                   (t("Выйти из Lado", "Quit Lado"), "quit:", "q")):
            m = K.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
            m.setTarget_(self)
            app_menu.addItem_(m)
        K.NSApp.setMainMenu_(main)
        if test_bundle:
            item = K.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Run isolated compatibility test", "runCompatibility:", "t")
            item.setTarget_(self)
            app_menu.insertItem_atIndex_(item, 0)
        self.item = K.NSStatusBar.systemStatusBar().statusItemWithLength_(K.NSVariableStatusItemLength)
        self.menu_focus = None
        self.menu = K.NSMenu.alloc().init()
        self.menu.setDelegate_(self)
        self.state_item = self.addItem("Lado", None)
        self.state_item.setEnabled_(False)
        self.menu.addItem_(K.NSMenuItem.separatorItem())
        self.auto_item = self.addItem(t("Автоисправление", "Automatic correction"), "toggleAuto:")
        self.pause_item = self.addItem(t("Пауза", "Pause"), "togglePause:")
        self.exclude_item = self.addItem(t("Не работать в этом приложении", "Exclude current application"), "excludeApp:")
        self.menu.addItem_(K.NSMenuItem.separatorItem())
        self.update_item = self.addItem(t("Проверить обновления…", "Check for Updates…"), "checkUpdates:")
        self.permission_item = self.addItem(t("Разрешения macOS…", "macOS permissions…"), "permissions:")
        self.addItem(t("Настройки…", "Settings…"), "showPreferences:")
        self.addItem(t("О Lado…", "About Lado…"), "showAbout:")
        self.addItem(t("Диагностика ввода…", "Input Status…"), "showInputStatus:")
        self.menu.addItem_(K.NSMenuItem.separatorItem())
        self.addItem(t("Выйти", "Quit"), "quit:", "q")
        self.item.setMenu_(self.menu)
        self.backend.start()
        self.timer = N.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, "tick:", None, True)
        N.NSRunLoop.mainRunLoop().addTimer_forMode_(self.timer, N.NSRunLoopCommonModes)
        self.updateStatus_(self.backend.focus)
        if self.backend.focus.state == "permission":
            self.showPermissionsWindow()

    @objc.python_method
    def addItem(self, title, action, key=""):
        item = K.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
        item.setTarget_(self)
        self.menu.addItem_(item)
        return item

    @objc.python_method
    def defer(self, fn, delay):
        self.pending.append((N.NSDate.timeIntervalSinceReferenceDate() + delay, fn))
        self.performSelector_withObject_afterDelay_("runDeferred:", None, delay)

    def runDeferred_(self, _):
        now = N.NSDate.timeIntervalSinceReferenceDate()
        ready = [x for x in self.pending if x[0] <= now + 0.001]
        self.pending = [x for x in self.pending if x not in ready]
        for _, fn in ready:
            fn()

    def tick_(self, _):
        if not self.backend.tap and A.AXIsProcessTrusted():
            if self.backend.start() and hasattr(self, "permission_window"):
                self.permission_window.close()
        self.backend.refresh()
        if (self.backend.tap and self.backend.test_bundle and
                "--run-compatibility-test" in sys.argv and not hasattr(self, "compatibility_runner")):
            self.runCompatibility_(None)
        if not self.backend.test_bundle:
            self.updateTick()

    @objc.python_method
    def updateTick(self):
        if self.settings.check_updates and self.update_service.due():
            self.update_service.check()
        result = self.update_service.poll()
        if result:
            self.update_item.setEnabled_(True)
            if result.update:
                self.available_update = result.update
                self.update_item.setTitle_(t("Новая версия: ", "New version: ") + result.update.version + "…")
                if result.manual:
                    self.showUpdatePrompt_(None)
                elif self.settings.check_updates and result.update.version not in self.seen_updates:
                    self.pending_update = result.update
            else:
                if result.status == "ok":
                    self.available_update = None
                    self.pending_update = None
                if not self.available_update:
                    self.update_item.setTitle_(t("Проверить обновления…", "Check for Updates…"))
                if result.manual:
                    self.updateMessage(result.status == "ok")
        if (self.pending_update and self.backend.focus.state != "secure" and not K.NSApp.modalWindow()
                and Q.CGEventSourceSecondsSinceLastEventType(Q.kCGEventSourceStateCombinedSessionState, Q.kCGEventKeyDown) >= 3):
            self.showUpdatePrompt_(None)

    @objc.python_method
    def updateMessage(self, success):
        alert = K.NSAlert.alloc().init()
        alert.setMessageText_(t("Новых версий пока нет", "No newer version available") if success
                              else t("Не удалось проверить обновления", "Could not check for updates"))
        alert.setInformativeText_(t("Lado продолжает работать. Можно проверить позже.", "Lado continues to work. You can check again later."))
        alert.addButtonWithTitle_("OK")
        K.NSApp.activateIgnoringOtherApps_(True)
        alert.runModal()

    def checkUpdates_(self, _):
        if self.available_update:
            self.showUpdatePrompt_(None)
        elif self.update_service.check(manual=True):
            self.update_item.setTitle_(t("Проверяем обновления…", "Checking for updates…"))
            self.update_item.setEnabled_(False)

    def showUpdatePrompt_(self, _):
        update = self.pending_update or self.available_update
        if not update or self.backend.focus.state == "secure":
            return
        self.pending_update = None
        self.seen_updates.add(update.version)
        alert = K.NSAlert.alloc().init()
        alert.setMessageText_(t("Новая версия Lado: ", "New Lado version: ") + update.version)
        alert.setInformativeText_(t(
            "Обновить? Кнопка откроет загрузку DMG в браузере. После загрузки перетащите Lado в «Программы».",
            "Update now? The button opens the DMG download in your browser. After downloading, drag Lado to Applications."))
        alert.addButtonWithTitle_(t("Обновить", "Update"))
        alert.addButtonWithTitle_(t("Позже", "Later"))
        K.NSApp.activateIgnoringOtherApps_(True)
        if alert.runModal() == K.NSAlertFirstButtonReturn and trusted_download(update.url, update.filename):
            self.openURL(update.url)

    def updateStatus_(self, focus):
        if self.menu_focus is not None:
            focus = self.menu_focus
        if not hasattr(self, "item"):
            return
        active = focus.state == "active" and bool(self.backend.tap)
        if focus.layout == self.settings.english_source:
            code = "EN"
        elif focus.layout == self.settings.russian_source:
            code = "RU"
        else:
            code = "—"
        b = self.item.button()
        b.setTitle_("")
        b.setImage_(status_image(code, focus.state == "secure"))
        b.setImagePosition_(K.NSImageOnly)
        b.setAppearsDisabled_(not active)
        message = t(*STATES.get(focus.state, STATES["unsupported"]))
        if focus.state == "active" and not self.settings.automatic:
            message = t("Ручной режим · двойной Shift", "Manual mode · double Shift")
        b.setToolTip_("Lado · " + message)
        b.setAccessibilityLabel_("Lado · " + code + " · " + message)
        self.state_item.setTitle_(message)
        self.auto_item.setState_(K.NSControlStateValueOn if self.settings.automatic else K.NSControlStateValueOff)
        self.pause_item.setTitle_(t("Продолжить", "Resume") if self.backend.disabled else t("Пауза", "Pause"))
        self.pause_item.setEnabled_(not self.backend.faulted)
        self.exclude_item.setEnabled_(bool(focus.bundle and focus.bundle != "com.sirdimitry.lado"))

    def menuWillOpen_(self, _):
        self.menu_focus = self.backend.last_pointer_focus or self.backend.focus
        self.diagnostic_focus = self.menu_focus
        self.updateStatus_(self.menu_focus)

    def menuDidClose_(self, _):
        self.menu_focus = None
        self.updateStatus_(self.backend.focus)

    def showInputStatus_(self, _):
        # Cached metadata from BEFORE opening the menu; no text/selection read.
        f = getattr(self, "diagnostic_focus", None) or self.backend.last_pointer_focus or self.backend.focus
        details = "\n".join([
            "Lado " + __version__,
            t("Состояние: ", "State: ") + t(*STATES.get(f.state, STATES["unsupported"])),
            t("Приложение: ", "Application: ") + (f.bundle or "—"),
            t("Тип поля: ", "Field type: ") + (f.role or "—"),
            t("Причина: ", "Reason: ") + (f.reason or f.state),
            "Accessibility: " + str(bool(A.AXIsProcessTrusted())),
            t("Мониторинг ввода: ", "Input Monitoring: ") + str(bool(Q.CGPreflightListenEventAccess())),
            t("Наблюдатель подключён: ", "Observer connected: ") + str(bool(self.backend.tap)),
            t("Наблюдатель включён: ", "Observer enabled: ") + str(bool(self.backend.tap and Q.CGEventTapIsEnabled(self.backend.tap))),
            t("Режим: только наблюдение", "Mode: listen-only"),
            "",
            t("Диагностика не содержит набранный текст или содержимое выделения.",
              "This status contains no typed text or selection contents."),
        ])
        if not hasattr(self, "input_status_window"):
            self.input_status_window = self.window(t("Диагностика ввода", "Input Status"), 560, 390)
            self.input_status_label = label(details, ((22, 20), (516, 350)), 13)
            self.input_status_window.contentView().addSubview_(self.input_status_label)
        else:
            self.input_status_label.setStringValue_(details)
        self.show(self.input_status_window)

    def toggleAuto_(self, _):
        self.settings.automatic = not self.settings.automatic
        save(self.settings)
        self.backend.clear()
        self.backend.refresh()

    def togglePause_(self, _):
        self.backend.disabled = not self.backend.disabled
        self.backend.clear()
        self.backend.refresh()

    def excludeApp_(self, _):
        bundle = self.backend.focus.bundle
        if bundle and bundle not in self.settings.excluded_apps:
            self.settings.excluded_apps.append(bundle)
            save(self.settings)
            self.backend.clear()
            self.backend.refresh()

    @objc.python_method
    def window(self, title, width, height):
        w = K.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (width, height)), K.NSWindowStyleMaskTitled | K.NSWindowStyleMaskClosable,
            K.NSBackingStoreBuffered, False)
        w.setTitle_(title)
        w.setReleasedWhenClosed_(False)
        w.center()
        self.windows.append(w)
        return w

    @objc.python_method
    def show(self, window):
        K.NSApp.activateIgnoringOtherApps_(True)
        window.makeKeyAndOrderFront_(None)

    @objc.python_method
    def showPermissionsWindow(self):
        if not hasattr(self, "permission_window"):
            w = self.window(t("Добро пожаловать в Lado", "Welcome to Lado"), 500, 360)
            v = w.contentView()
            image = K.NSImageView.alloc().initWithFrame_(((26, 260), (60, 60)))
            image.setImage_(K.NSImage.alloc().initWithContentsOfFile_(resource("icon.png")))
            v.addSubview_(image)
            v.addSubview_(label("Lado", ((102, 277), (350, 35)), 27, bold=True))
            v.addSubview_(label(t("Ваши слова остаются у вас.", "Your words stay with you."), ((28, 227), (444, 26)), 17))
            v.addSubview_(label(t(
                "Для двойного Shift и исправления раскладки разрешите Lado доступ в разделе «Универсальный доступ». macOS также может запросить «Мониторинг ввода». Затем вернитесь к набору — Lado проверит доступ автоматически.",
                "Allow Lado in Accessibility to enable double Shift and layout correction. macOS may also request Input Monitoring. Return to typing afterwards — Lado checks permissions automatically."), ((28, 118), (444, 102))))
            v.addSubview_(label(t("Локальный ввод. Без истории. Без подписки.", "Local typing. No typing history. No subscription."), ((28, 78), (444, 30)), 12, K.NSColor.secondaryLabelColor()))
            v.addSubview_(button(t("Открыть настройки macOS", "Open macOS Settings"), ((232, 24), (240, 34)), self, "permissions:"))
            v.addSubview_(button(t("Настройки Lado…", "Lado Settings…"), ((26, 24), (180, 34)), self, "showPreferences:"))
            self.permission_window = w
        self.show(self.permission_window)

    def permissions_(self, _):
        A.AXIsProcessTrustedWithOptions({A.kAXTrustedCheckOptionPrompt: True})
        Q.CGRequestListenEventAccess()
        self.openURL("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")

    @objc.python_method
    def textEditor(self, view, frame, text):
        scroll = K.NSScrollView.alloc().initWithFrame_(frame)
        scroll.setBorderType_(K.NSBezelBorder)
        scroll.setHasVerticalScroller_(True)
        editor = K.NSTextView.alloc().initWithFrame_(((0, 0), (frame[1][0] - 18, frame[1][1])))
        editor.setRichText_(False)
        editor.setAutomaticQuoteSubstitutionEnabled_(False)
        editor.setAutomaticSpellingCorrectionEnabled_(False)
        editor.setFont_(K.NSFont.monospacedSystemFontOfSize_weight_(12, K.NSFontWeightRegular))
        editor.setString_(text)
        scroll.setDocumentView_(editor)
        view.addSubview_(scroll)
        return editor

    @objc.python_method
    def checkbox(self, title, frame, value):
        b = K.NSButton.checkboxWithTitle_target_action_(title, None, None)
        b.setFrame_(frame)
        b.setState_(int(value))
        return b

    def showPreferences_(self, _):
        if self.preferences:
            self.preferences.close()
        w = self.window(t("Настройки Lado", "Lado Settings"), 640, 510)
        v = w.contentView()
        tabs = K.NSTabView.alloc().initWithFrame_(((20, 80), (600, 410)))
        pages = []
        for title in (t("Основное", "General"), t("Исключения", "Exceptions"), t("Приватность", "Privacy")):
            tab = K.NSTabViewItem.alloc().initWithIdentifier_(title)
            tab.setLabel_(title)
            page = K.NSView.alloc().initWithFrame_(((0, 0), (570, 360)))
            tab.setView_(page)
            tabs.addTabViewItem_(tab)
            pages.append(page)
        v.addSubview_(tabs)
        general, exceptions, privacy = pages
        self.auto_box = self.checkbox(t("Исправлять раскладку автоматически", "Correct keyboard layout automatically"), ((18, 304), (530, 25)), self.settings.automatic)
        general.addSubview_(self.auto_box)
        general.addSubview_(label(t("Рабочая пара раскладок", "Keyboard layout pair"), ((18, 261), (530, 25)), bold=True))
        installed = self.backend.sources.all()
        self.source_ids = []
        self.source_popups = []
        for x, lang, selected in ((18, "en", self.settings.english_source), (298, "ru", self.settings.russian_source)):
            choices = [s for s in installed if s["language"] == lang]
            popup = K.NSPopUpButton.alloc().initWithFrame_pullsDown_(((x, 222), (254, 30)), False)
            popup.addItemsWithTitles_([s["name"] for s in choices] or [t("Добавьте раскладку в macOS", "Add this layout in macOS")])
            ids = [s["id"] for s in choices]
            if selected in ids:
                popup.selectItemAtIndex_(ids.index(selected))
            self.source_ids.append(ids)
            self.source_popups.append(popup)
            general.addSubview_(popup)
        general.addSubview_(label(t("На остальных языках Lado приостанавливается.", "Lado pauses when another layout is active."), ((18, 183), (530, 28)), 12, K.NSColor.secondaryLabelColor()))
        general.addSubview_(label(t("Интервал двойного Shift", "Double Shift interval"), ((18, 139), (300, 26))))
        self.interval = K.NSPopUpButton.alloc().initWithFrame_pullsDown_(((365, 137), (186, 30)), False)
        self.interval.addItemsWithTitles_(["300 ms", "400 ms", "500 ms", "600 ms"])
        self.interval.selectItemAtIndex_(min(range(4), key=lambda i: abs([300,400,500,600][i] - self.settings.double_shift_ms)))
        general.addSubview_(self.interval)
        self.login_box = self.checkbox(t("Запускать при входе в систему", "Start at login"), ((18, 100), (530, 26)), self.loginPath().exists())
        self.login_box.setEnabled_(bool(getattr(sys, "frozen", False)))
        general.addSubview_(self.login_box)
        self.updates_box = self.checkbox(t("Проверять новые версии на GitHub", "Check GitHub for new versions"), ((18, 65), (530, 26)), self.settings.check_updates)
        general.addSubview_(self.updates_box)
        general.addSubview_(label(t("Двойной Shift: выделенный текст или последнее слово. ЗАГЛАВНЫЕ слова автоматика пропускает.", "Double Shift: selected text or the last word. Automatic correction skips ALL-CAPS words."), ((18, 10), (530, 43)), 12, K.NSColor.secondaryLabelColor()))
        exceptions.addSubview_(label(t("Личные слова", "Personal words"), ((18, 308), (254, 24)), bold=True))
        exceptions.addSubview_(label(t("Приложения", "Applications"), ((298, 308), (254, 24)), bold=True))
        self.words_editor = self.textEditor(exceptions, ((18, 88), (254, 214)), "\n".join(self.settings.exceptions))
        self.excluded_draft = list(self.settings.excluded_apps)
        scroll = K.NSScrollView.alloc().initWithFrame_(((298, 132), (254, 170)))
        scroll.setBorderType_(K.NSBezelBorder)
        scroll.setHasVerticalScroller_(True)
        self.app_table = K.NSTableView.alloc().initWithFrame_(((0, 0), (236, 170)))
        column = K.NSTableColumn.alloc().initWithIdentifier_("application")
        column.setWidth_(234)
        self.app_table.addTableColumn_(column)
        self.app_table.setHeaderView_(None)
        self.app_table.setRowHeight_(25)
        self.app_table.setDataSource_(self)
        self.app_table.setDelegate_(self)
        scroll.setDocumentView_(self.app_table)
        exceptions.addSubview_(scroll)
        exceptions.addSubview_(button(t("Добавить…", "Add…"), ((298, 88), (124, 32)), self, "addExcluded:"))
        exceptions.addSubview_(button(t("Убрать", "Remove"), ((428, 88), (124, 32)), self, "removeExcluded:"))
        self.case_box = self.checkbox(t("Учитывать регистр слов", "Case-sensitive words"), ((18, 49), (530, 26)), self.settings.case_sensitive)
        exceptions.addSubview_(self.case_box)
        exceptions.addSubview_(label(t("По одному на строку. Исключения не мешают ручному двойному Shift.", "One entry per line. Word exceptions do not block manual double Shift."), ((18, 7), (530, 36)), 12, K.NSColor.secondaryLabelColor()))
        privacy.addSubview_(label(t("Ваш текст не покидает Mac", "Your text stays on your Mac"), ((20, 291), (525, 35)), 21, bold=True))
        privacy.addSubview_(label(t(
            "• Текст не передаётся. Нет аналитики и истории ввода.\n\n• В памяти — до трёх завершённых слов и текущего слова. Контекст очищается при смене поля, паузе и после 30 секунд бездействия.\n\n• Выделение читается по двойному Shift; при исправлении сверяется только короткий наблюдавшийся фрагмент. Последняя операция хранится в памяти до 30 секунд.\n\n• В защищённых полях обработка отключается, контекст очищается, значок показывает замок.\n\n• На диск сохраняются только настройки и ваши явные исключения. Проверка обновлений запрашивает лишь публичные релизы GitHub и отключается в настройках.",
            "• Typed text is never transmitted. No analytics or typing history.\n\n• Memory holds up to three completed words and the current word. Context clears on focus change, pause and after 30 idle seconds.\n\n• User selections are read on double Shift; word correction checks only the short observed span. The last operation stays in memory for up to 30 seconds.\n\n• Protected fields disable processing, clear context and show a lock icon.\n\n• Only preferences and explicit exceptions are saved. Optional update checks request only public GitHub release metadata; disable them in Settings."), ((20, 20), (530, 265)), 13))
        v.addSubview_(label(t("Ввод локально. Без истории ввода.", "Local typing. No typing history."), ((24, 26), (360, 28)), 12, K.NSColor.secondaryLabelColor()))
        v.addSubview_(button(t("Сохранить", "Save"), ((493, 22), (122, 34)), self, "savePreferences:"))
        self.preferences = w
        self.show(w)

    @objc.python_method
    def loginPath(self):
        return Path.home() / "Library/LaunchAgents/com.sirdimitry.lado.plist"

    @objc.python_method
    def setLogin(self, enabled):
        p = self.loginPath()
        if enabled and getattr(sys, "frozen", False):
            p.parent.mkdir(parents=True, exist_ok=True)
            contents = {"Label": "com.sirdimitry.lado", "ProgramArguments": [sys.executable],
                        "RunAtLoad": True, "ProcessType": "Interactive"}
            with p.open("wb") as f:
                plistlib.dump(contents, f)
            p.chmod(0o600)
        elif p.exists():
            p.unlink()

    def savePreferences_(self, _):
        self.settings.automatic = bool(self.auto_box.state())
        self.settings.check_updates = bool(self.updates_box.state())
        if not self.settings.check_updates:
            self.pending_update = None
        self.settings.case_sensitive = bool(self.case_box.state())
        self.settings.double_shift_ms = [300,400,500,600][self.interval.indexOfSelectedItem()]
        self.settings.exceptions = list(dict.fromkeys(x.strip()[:256] for x in str(self.words_editor.string()).splitlines() if x.strip()))[:5000]
        self.settings.excluded_apps = list(self.excluded_draft)
        for i, field in enumerate(("english_source", "russian_source")):
            index = self.source_popups[i].indexOfSelectedItem()
            if self.source_ids[i] and index >= 0:
                setattr(self.settings, field, self.source_ids[i][index])
        save(self.settings)
        self.setLogin(bool(self.login_box.state()))
        self.backend.reload()
        self.backend.refresh()
        self.preferences.close()

    def numberOfRowsInTableView_(self, _):
        return len(getattr(self, "excluded_draft", []))

    def tableView_objectValueForTableColumn_row_(self, table, column, row):
        bundle = self.excluded_draft[row]
        known = {"com.apple.Terminal": "Terminal", "com.googlecode.iterm2": "iTerm",
                 "com.microsoft.VSCode": "Visual Studio Code", "com.apple.dt.Xcode": "Xcode",
                 "com.agilebits.onepassword7": "1Password 7", "com.1password.1password": "1Password"}
        path = K.NSWorkspace.sharedWorkspace().absolutePathForAppBundleWithIdentifier_(bundle)
        return N.NSFileManager.defaultManager().displayNameAtPath_(path) if path else known.get(bundle, bundle)

    def addExcluded_(self, _):
        panel = K.NSOpenPanel.openPanel()
        panel.setTitle_(t("Выберите приложение", "Choose an application"))
        panel.setAllowedFileTypes_(["app"])
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(True)
        panel.setDirectoryURL_(N.NSURL.fileURLWithPath_("/Applications"))
        def picked(result):
            if result == K.NSModalResponseOK:
                for url in panel.URLs():
                    app = N.NSBundle.bundleWithPath_(str(url.path()))
                    bundle = str(app.bundleIdentifier() or "") if app else ""
                    if bundle and bundle not in self.excluded_draft and len(self.excluded_draft) < 5000:
                        self.excluded_draft.append(bundle)
                self.app_table.reloadData()
        panel.beginSheetModalForWindow_completionHandler_(self.preferences, picked)

    def removeExcluded_(self, _):
        row = self.app_table.selectedRow()
        if 0 <= row < len(self.excluded_draft):
            self.excluded_draft.pop(row)
            self.app_table.reloadData()

    @objc.python_method
    def openURL(self, url):
        K.NSWorkspace.sharedWorkspace().openURL_(N.NSURL.URLWithString_(url))

    def openX_(self, _):
        self.openURL("https://x.com/sirdimitry")

    def openGitHub_(self, _):
        self.openURL("https://github.com/sirdimitry")

    def openLicenses_(self, _):
        K.NSWorkspace.sharedWorkspace().openFile_(str(Path(__file__).parent / "data/NOTICE.md"))

    def showAbout_(self, _):
        if not self.about:
            w = self.window(t("О Lado", "About Lado"), 440, 450)
            v = w.contentView()
            iv = K.NSImageView.alloc().initWithFrame_(((170, 307), (100, 100)))
            iv.setImage_(K.NSImage.alloc().initWithContentsOfFile_(resource("icon.png")))
            v.addSubview_(iv)
            title = label("Lado", ((30, 253), (380, 48)), 32, bold=True)
            title.setAlignment_(K.NSTextAlignmentCenter)
            v.addSubview_(title)
            for text, y, size in [(t("Версия ", "Version ") + __version__ + " · macOS preview", 221, 12),
                                  (t("Ваши слова остаются у вас.", "Your words stay with you."), 176, 17),
                                  (t("Ввод локально. Без истории ввода.", "Local typing. No typing history."), 142, 12),
                                  (t("Создано @sirdimitry", "Created by @sirdimitry"), 103, 13)]:
                item = label(text, ((20, y), (400, 28)), size)
                item.setAlignment_(K.NSTextAlignmentCenter)
                v.addSubview_(item)
            v.addSubview_(button("X · @sirdimitry ↗", ((48, 57), (166, 32)), self, "openX:"))
            v.addSubview_(button("GitHub · @sirdimitry ↗", ((224, 57), (172, 32)), self, "openGitHub:"))
            credits = button(t("Лицензии и словари", "Licenses and dictionaries"), ((100, 16), (240, 28)), self, "openLicenses:")
            credits.setBordered_(False)
            v.addSubview_(credits)
            self.about = w
        self.show(self.about)

    def applicationWillTerminate_(self, _):
        self.backend.stop()

    def closeWindow_(self, _):
        window = K.NSApp.keyWindow()
        if window:
            window.close()

    def runCompatibility_(self, _):
        if self.backend.test_bundle != "com.sirdimitry.lado-testpad":
            return
        from .compatibility import CompatibilityRunner
        self.compatibility_runner = CompatibilityRunner(self)
        self.compatibility_runner.begin()

    def quit_(self, _):
        self.backend.stop()
        K.NSApp.terminate_(None)


def run():
    from .instance import InstanceLock
    from .settings import settings_path
    instance = InstanceLock(settings_path().parent / "instance.lock")
    if not instance.acquire():
        return
    try:
        app = K.NSApplication.sharedApplication()
        app.setActivationPolicy_(K.NSApplicationActivationPolicyAccessory)
        delegate = LadoDelegate.alloc().init()
        app.setDelegate_(delegate)
        app.run()
    finally:
        instance.close()
