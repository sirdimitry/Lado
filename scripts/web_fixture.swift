import AppKit
import WebKit
final class WebTest: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    func applicationDidFinishLaunching(_ n: Notification) {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 700, height: 430), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Lado WebKit Compatibility Test"
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        web = WKWebView(frame: window.contentView!.bounds, configuration: config)
        web.navigationDelegate = self
        web.autoresizingMask = [.width, .height]
        window.contentView!.addSubview(web)
        web.loadHTMLString("""
        <!doctype html><meta charset="utf-8"><style>body{font:20px system-ui;padding:24px} [contenteditable],textarea,input{display:block;border:2px solid #555;padding:12px;width:90%;min-height:60px;margin:12px 0}</style>
        <h2>Lado · local WebKit test</h2><p>Synthetic text only. No network.</p>
        <div id="plain-test-field" contenteditable="true" role="textbox" aria-label="Synthetic web editor" spellcheck="false"></div>
        <textarea id="second-test-field" aria-label="Synthetic textarea" spellcheck="false"></textarea>
        <input id="secure-test-field" type="password" aria-label="Synthetic password" placeholder="Made-up value only">
        <script>document.getElementById('plain-test-field').focus()</script>
        """, baseURL: nil)
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        window.makeFirstResponder(web)
        web.evaluateJavaScript("document.getElementById('plain-test-field').focus()", completionHandler: nil)
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}
let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = WebTest()
app.delegate = delegate
app.run()
