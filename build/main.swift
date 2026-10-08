// Qwen Image Studio — the Mac shell.
//
// A native window around the local studio: picks a port, prepares the small
// Python environment the server needs (bootstrap.sh), starts the server, and
// loads it in a WKWebView. A second launch joins the studio already running.

import AppKit
import UniformTypeIdentifiers
import WebKit

let bundle = Bundle.main
let resources = bundle.resourceURL ?? URL(fileURLWithPath: NSHomeDirectory())
let dataDir = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true)
    .appendingPathComponent("Qwen Image Studio", isDirectory: true)
let logsDir = dataDir.appendingPathComponent("logs", isDirectory: true)

let portRange = Array(8730...8739)

// ── helpers ─────────────────────────────────────────────────────────────

func httpGetSync(_ url: URL, timeout: TimeInterval) -> (status: Int, body: Data)? {
    var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: timeout)
    request.httpShouldHandleCookies = false
    let semaphore = DispatchSemaphore(value: 0)
    var result: (Int, Data)?
    let task = URLSession.shared.dataTask(with: request) { data, response, _ in
        if let http = response as? HTTPURLResponse {
            result = (http.statusCode, data ?? Data())
        }
        semaphore.signal()
    }
    task.resume()
    _ = semaphore.wait(timeout: .now() + timeout + 1)
    return result.map { ($0.0, $0.1) }
}

/// A port with a live studio behind /api/config, if one is already running.
func findRunningStudio() -> Int? {
    for port in portRange {
        if let response = httpGetSync(URL(string: "http://127.0.0.1:\(port)/api/config")!, timeout: 1.0),
           response.status == 200,
           let config = try? JSONSerialization.jsonObject(with: response.body) as? [String: Any],
           let servedDirectory = config["data_dir"] as? String,
           URL(fileURLWithPath: servedDirectory).standardizedFileURL.path == dataDir.standardizedFileURL.path {
            return port
        }
    }
    return nil
}

func portIsFree(_ port: Int) -> Bool {
    let socketFD = socket(AF_INET, SOCK_STREAM, 0)
    guard socketFD >= 0 else { return false }
    defer { close(socketFD) }
    var addr = sockaddr_in()
    addr.sin_family = sa_family_t(AF_INET)
    addr.sin_port = in_port_t(port).bigEndian
    addr.sin_addr.s_addr = inet_addr("127.0.0.1")
    let connected = withUnsafePointer(to: &addr) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            connect(socketFD, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    return connected != 0
}

// ── the app delegate ────────────────────────────────────────────────────

class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var serverProcess: Process?
    var stdinHandle: FileHandle?
    var studioPort = 0

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.activate(ignoringOtherApps: true)
        buildWindow()
        showSplash()
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            let outcome = bringUpStudio()
            DispatchQueue.main.async { [self] in
                switch outcome {
                case .ready(let port):
                    studioPort = port
                    webView.load(URLRequest(url: URL(string: "http://127.0.0.1:\(port)/")!))
                case .failed(let message):
                    showError(message)
                }
            }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        guard let process = serverProcess, process.isRunning else { return }
        // the server takes its own ComfyUI down on the way out; give it the moment it needs
        let gone = DispatchSemaphore(value: 0)
        process.terminationHandler = { _ in gone.signal() }
        process.terminate()
        _ = gone.wait(timeout: .now() + 6)
        if process.isRunning {
            process.terminate() // it will be killed with the process group at worst
        }
    }

    // window ─────────────────────────────────────────────────────────────
    func buildWindow() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false)
        window.title = "qwen image studio"
        window.minSize = NSSize(width: 1080, height: 680)
        webView = WKWebView(frame: window.contentView!.bounds)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.uiDelegate = self
        window.contentView = webView
        window.center()
        window.makeKeyAndOrderFront(nil)
    }

    /// The picker behind “drop images here or click to add”, shown natively.
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.png, .jpeg, .webP]
        let respond: (NSApplication.ModalResponse) -> Void = { response in
            completionHandler(response == .OK ? panel.urls : nil)
        }
        if window.isVisible {
            panel.beginSheetModal(for: window, completionHandler: respond)
        } else {
            respond(panel.runModal())
        }
    }

    func showSplash() {
        let html = """
        <!DOCTYPE html><html><head><meta charset="utf-8"><style>
          body { margin:0; height:100vh; display:grid; place-items:center; background:#ece9e2;
                 font-family:Futura,'Avenir Next',-apple-system,sans-serif; color:#23252b; }
          @media (prefers-color-scheme: dark) {
            body { background:#101216; color:#e8e9ec; }
            .disc { opacity:.55; } }
          .stage { position:relative; width:120px; height:120px; }
          .shape { position:absolute; animation:spin 2.4s cubic-bezier(.6,.1,.3,.9) infinite; }
          .disc { width:74px; height:74px; border-radius:50%; background:#e0372b; top:4px; right:2px; opacity:.85; }
          .tri { width:0; height:0; border-left:30px solid transparent; border-right:30px solid transparent;
                 border-bottom:52px solid #2456b8; bottom:0; left:6px; animation-delay:.3s; }
          .bar { width:64px; height:22px; border-radius:11px; background:#edb02d; bottom:6px; right:0; animation-delay:.6s; }
          @keyframes spin { 50% { transform:translateY(-14px) rotate(8deg); } 100% { transform:none; } }
          p { position:fixed; bottom:36px; width:100%; text-align:center; letter-spacing:.24em;
              text-transform:uppercase; font-size:12px; opacity:.6; }
        </style></head><body>
          <div class="stage"><div class="shape disc"></div><div class="shape tri"></div><div class="shape bar"></div></div>
          <p>qwen image studio</p>
        </body></html>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    func showError(_ message: String) {
        let logPath = logsDir.appendingPathComponent("studio.log").path
        let escaped = message.replacingOccurrences(of: "<", with: "&lt;")
        let html = """
        <!DOCTYPE html><html><head><meta charset="utf-8"><style>
          body { margin:0; height:100vh; display:grid; place-items:center; background:#ece9e2;
                 font-family:-apple-system,sans-serif; color:#23252b; }
          .card { max-width:560px; padding:36px 40px; border-radius:24px; background:rgba(255,255,255,.7); box-shadow:0 24px 60px rgba(40,42,52,.18); }
          h1 { font:700 18px/1.4 Futura,'Avenir Next',sans-serif; letter-spacing:.1em; text-transform:uppercase; color:#e0372b; margin:0 0 12px; }
          p { font:400 13px/20px sans-serif; margin:0; white-space:pre-wrap; }
          code { font:400 12px Menlo,monospace; color:#575b65; display:block; margin-top:16px; }
        </style></head><body><div class="card">
          <h1>The studio could not start</h1>
          <p>\(escaped)</p><code>log: \(logPath)</code>
        </div></body></html>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    // studio ─────────────────────────────────────────────────────────────
    enum StudioOutcome {
        case ready(Int)
        case failed(String)
    }

    func bringUpStudio() -> StudioOutcome {
        try? FileManager.default.createDirectory(at: logsDir, withIntermediateDirectories: true)

        if let running = findRunningStudio() {
            return .ready(running)
        }

        let port = portRange.first(where: { portIsFree($0) }) ?? 8730

        // the small server environment (Python + Pillow)
        let bootstrap = resources.appendingPathComponent("bootstrap.sh")
        let bootstrapResult = runScript(bootstrap, arguments: ["--data-dir", dataDir.path, "--resources", resources.path])
        if bootstrapResult != 0 {
            return .failed("Preparing the studio's Python environment failed (exit \(bootstrapResult)). " +
                "Open the log for details — it usually means no Python 3.11+ is present and the network was unavailable for downloading one.")
        }

        let serverPython = dataDir.appendingPathComponent("server-env/bin/python")
        guard FileManager.default.fileExists(atPath: serverPython.path) else {
            return .failed("The studio's Python environment is missing after bootstrap.")
        }

        let serverLog = FileHandle(forWritingAtPath: logsDir.appendingPathComponent("studio.log").path)
            ?? FileHandle.nullDevice
        let process = Process()
        process.executableURL = serverPython
        process.arguments = [
            resources.appendingPathComponent("web/server.py").path,
            "--port", String(port),
            "--data-dir", dataDir.path,
            "--exit-on-stdin-eof",
        ]
        let stdinPipe = Pipe()
        stdinHandle = stdinPipe.fileHandleForWriting // held open; EOF when this app dies
        process.standardInput = stdinPipe
        process.standardOutput = serverLog
        process.standardError = serverLog
        do {
            try process.run()
        } catch {
            return .failed("The server process could not start: \(error.localizedDescription)")
        }
        serverProcess = process

        let started = Date()
        while Date().timeIntervalSince(started) < 240 {
            if !process.isRunning { return .failed("The server exited during startup — see the log.") }
            if let response = httpGetSync(URL(string: "http://127.0.0.1:\(port)/api/config")!, timeout: 2.0),
               response.status == 200 {
                return .ready(port)
            }
            Thread.sleep(forTimeInterval: 0.4)
        }
        return .failed("The server did not answer within four minutes — see the log.")
    }

    func runScript(_ script: URL, arguments: [String]) -> Int32 {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [script.path] + arguments
        let log = FileHandle(forWritingAtPath: logsDir.appendingPathComponent("studio.log").path) ?? FileHandle.nullDevice
        process.standardOutput = log
        process.standardError = log
        do {
            try process.run()
        } catch {
            return -1
        }
        process.waitUntilExit()
        return process.terminationStatus
    }
}

// ── menus ───────────────────────────────────────────────────────────────

func buildMenus() {
    let main = NSMenu()

    let appItem = NSMenuItem()
    main.addItem(appItem)
    let appMenu = NSMenu()
    appMenu.addItem(withTitle: "About qwen image studio", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
    appMenu.addItem(.separator())
    appMenu.addItem(withTitle: "Hide qwen image studio", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
    appMenu.addItem(withTitle: "Quit qwen image studio", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
    appItem.submenu = appMenu

    let fileItem = NSMenuItem()
    main.addItem(fileItem)
    let fileMenu = NSMenu(title: "File")
    fileMenu.addItem(withTitle: "Close Window", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
    fileItem.submenu = fileMenu

    let editItem = NSMenuItem()
    main.addItem(editItem)
    let editMenu = NSMenu(title: "Edit")
    editMenu.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
    editMenu.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
    editMenu.addItem(.separator())
    editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
    editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
    editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
    editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
    editItem.submenu = editMenu

    let viewItem = NSMenuItem()
    main.addItem(viewItem)
    let viewMenu = NSMenu(title: "View")
    viewMenu.addItem(withTitle: "Reload Page", action: #selector(WKWebView.reload(_:)), keyEquivalent: "r")
    viewItem.submenu = viewMenu

    let windowItem = NSMenuItem()
    main.addItem(windowItem)
    let windowMenu = NSMenu(title: "Window")
    windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
    windowItem.submenu = windowMenu

    NSApp.mainMenu = main
}

// ── run ─────────────────────────────────────────────────────────────────

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
buildMenus()
app.run()
