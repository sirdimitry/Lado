// Disposable native controls for compatibility checks. Never use real passwords.
import AppKit

final class TestPad: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var text: NSTextView!
    var password: NSSecureTextField!
    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 640, height: 480),
                          styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Lado Compatibility Test"
        let view = window.contentView!
        let title = NSTextField(labelWithString: "Lado test pad · synthetic text only")
        title.frame = NSRect(x: 28, y: 418, width: 580, height: 30)
        title.font = .boldSystemFont(ofSize: 20)
        view.addSubview(title)
        let scroll = NSScrollView(frame: NSRect(x: 28, y: 190, width: 584, height: 210))
        scroll.borderType = .bezelBorder
        scroll.hasVerticalScroller = true
        text = NSTextView(frame: NSRect(x: 0, y: 0, width: 565, height: 210))
        text.isRichText = false
        text.isAutomaticSpellingCorrectionEnabled = false
        text.font = .monospacedSystemFont(ofSize: 22, weight: .regular)
        text.setAccessibilityIdentifier("plain-test-field")
        scroll.documentView = text
        view.addSubview(scroll)
        let caption = NSTextField(labelWithString: "Protected field — use a made-up value only")
        caption.frame = NSRect(x: 28, y: 139, width: 580, height: 25)
        view.addSubview(caption)
        password = NSSecureTextField(frame: NSRect(x: 28, y: 95, width: 584, height: 32))
        password.placeholderString = "Synthetic password"
        password.setAccessibilityIdentifier("secure-test-field")
        view.addSubview(password)
        let reset = NSButton(title: "Reset test fields", target: self, action: #selector(resetFields))
        reset.frame = NSRect(x: 28, y: 30, width: 160, height: 32)
        view.addSubview(reset)
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        window.makeFirstResponder(text)
    }
    @objc func resetFields() {
        text.string = ""
        password.stringValue = ""
        window.makeFirstResponder(text)
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}
let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = TestPad()
app.delegate = delegate
app.run()
