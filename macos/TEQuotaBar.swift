import AppKit
import SwiftUI

final class GateModel: ObservableObject {
    @Published var data: [String: Any] = [:]
    @Published var error = ""
    var refresh: (() -> Void)?
    var decision: [String: Any] { data["decision"] as? [String: Any] ?? [:] }
    var activity: [String: Any] { data["activity"] as? [String: Any] ?? [:] }
    var hooks: [String: Any] { data["hooks"] as? [String: Any] ?? [:] }
    var active: Bool { decision["active"] as? Bool ?? false }
    var ready: Bool { hooks["ready"] as? Bool ?? false }
    var last: [String: Any] { activity["lastEvent"] as? [String: Any] ?? [:] }
    var forwarded: [String: Any] { activity["lastForwarded"] as? [String: Any] ?? [:] }
    var context: [String: Any] { activity["lastContext"] as? [String: Any] ?? [:] }
    var title: String {
        if !error.isEmpty { return "監測器無法確認狀態" }
        if data.isEmpty { return "正在讀取本機狀態" }
        if !ready { return hooks.isEmpty ? "hooks 狀態尚未確認" : "hooks 尚未準備完成" }
        if !active { return decision["reason"] as? String == "quota_sufficient" ? "待命 · 額度充足" : "目前不符合啟用條件" }
        if let stamp = context["at"] as? Double, Date().timeIntervalSince1970 - stamp < 30 { return "剛回傳經驗內容" }
        if let stamp = forwarded["at"] as? Double, Date().timeIntervalSince1970 - stamp < 30 { return "剛轉交 TokenEconomizer" }
        return "符合介入條件 · 等待 hook"
    }
    var tint: Color { !error.isEmpty ? .red : (!ready || active ? .orange : Color(red: 0.23, green: 0.48, blue: 0.43)) }
    var barTitle: String {
        if !error.isEmpty { return "TE !" }
        if data.isEmpty { return "TE …" }
        if !ready { return "TE ?" }
        if !active { return "TE 待命" }
        return "TE 可介入"
    }
    func percent(_ key: String) -> String {
        guard let value = decision[key] as? Double else { return "—" }
        return String(format: "%.0f%%", value)
    }
    func when(_ receipt: [String: Any]) -> String {
        guard let stamp = receipt["at"] as? Double else { return "尚無紀錄" }
        return Self.date(Date(timeIntervalSince1970: stamp))
    }
    static func date(_ value: Date) -> String {
        let formatter = DateFormatter(); formatter.dateFormat = "MM/dd HH:mm:ss"
        return formatter.string(from: value)
    }
    func reset(_ duration: Int) -> String {
        let windows = data["windows"] as? [[String: Any]] ?? []
        guard let window = windows.first(where: { ($0["windowDurationMins"] as? Int) == duration }),
              let stamp = window["resetsAt"] as? Double else { return "重置時間未知" }
        return "重置 " + Self.date(Date(timeIntervalSince1970: stamp))
    }
    var reason: String {
        let names = ["quota_sufficient":"額度充足，已跳過", "below_threshold":"低於門檻", "project_excluded":"此專案已排除",
                     "disabled_by_settings":"總開關已關閉", "forwarded_envfacts":"已轉交 envfacts",
                     "upstream_failed":"上游失敗或逾時", "stale_snapshot":"額度資料已過期",
                     "reset_requires_refresh":"等待重置後的新額度", "explicitly_disabled":"本次執行已停用",
                     "upstream_bootstrap_changed":"上游檔案變動，已停止轉交"]
        guard let key = last["reason"] as? String else { return "尚未觀測到 hook" }
        return names[key] ?? key
    }
}

struct QuotaCard: View {
    let name: String; let value: Double?; let threshold: Double?; let reset: String
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(name).font(.system(size: 12, weight: .semibold)).foregroundStyle(.secondary)
            HStack(spacing: 12) {
                ZStack {
                    Circle().stroke(Color.secondary.opacity(0.12), lineWidth: 5)
                    Circle().trim(from: 0, to: min(1, max(0, (value ?? 0)/100)))
                        .stroke(Color(red: 0.28, green: 0.56, blue: 0.48), style: StrokeStyle(lineWidth: 5, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                    Text(value == nil ? "?" : String(format: "%.0f", value!)).font(.system(size: 19, weight: .semibold, design: .rounded))
                }.frame(width: 54, height: 54)
                VStack(alignment: .leading, spacing: 3) {
                    Text("% 剩餘").font(.system(size: 12)).foregroundStyle(.secondary)
                    Text(threshold == nil ? "門檻 —" : String(format: "低於 %.0f%%", threshold!)).font(.system(size: 11))
                }
            }
            Text(reset).font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(14)
            .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 14))
    }
}

struct GateView: View {
    @ObservedObject var model: GateModel
    let openGUI: () -> Void
    let showFiles: () -> Void
    let quit: () -> Void
    func line(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label).foregroundStyle(.secondary)
            Spacer(minLength: 12)
            Text(value).multilineTextAlignment(.trailing).textSelection(.enabled)
        }.font(.system(size: 12))
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "leaf.fill").font(.system(size: 22)).foregroundStyle(model.tint)
                VStack(alignment: .leading, spacing: 2) {
                    Text("TE Quota Bar").font(.system(size: 19, weight: .semibold))
                    Text("TokenEconomizer · 本機監測").font(.system(size: 11)).foregroundStyle(.secondary)
                }
                Spacer()
                Text(model.data["demo"] as? Bool == true ? "DEMO" : "LIVE").font(.system(size: 10, weight: .bold, design: .monospaced))
                    .padding(6).background(model.tint.opacity(0.1), in: Capsule())
            }
            VStack(alignment: .leading, spacing: 7) {
                Label(model.title, systemImage: model.active ? "bolt.circle.fill" : "pause.circle").font(.system(size: 15, weight: .semibold)).foregroundStyle(model.tint)
                Text("額度資格與實際執行分開顯示；排除專案仍會跳過。")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
                if !model.error.isEmpty { Text(model.error).font(.system(size: 11)).foregroundStyle(.red) }
                if let version = model.hooks["version"] as? String, version.hasPrefix("0.2.") {
                    Text("目前 v\(version) 的 hooks 不寫逐次紀錄；升級並審核後才可觀察轉交與回傳時間。")
                        .font(.system(size: 11)).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true)
                }
            }
            HStack(spacing: 10) {
                QuotaCard(name: "5 小時", value: model.decision["remaining_5h"] as? Double,
                          threshold: (model.data["thresholds"] as? [Double])?.first, reset: model.reset(300))
                QuotaCard(name: "每週", value: model.decision["remaining_weekly"] as? Double,
                          threshold: (model.data["thresholds"] as? [Double])?.last, reset: model.reset(10080))
            }
            VStack(spacing: 10) {
                line("Hooks 信任", model.hooks.isEmpty ? "尚未確認" : "\(model.hooks["trusted"] as? Int ?? 0) / \(model.hooks["count"] as? Int ?? 0) 已信任")
                line("外掛版本", model.hooks["version"] as? String ?? "未知")
                line("額度更新", (model.data["snapshotAt"] as? Double).map { GateModel.date(Date(timeIntervalSince1970: $0)) } ?? "尚無資料")
                line("最後 hook", model.when(model.last))
                line("最後結果", model.reason)
                line("最後轉交 TE", model.when(model.forwarded))
                line("最後回傳注入內容", model.when(model.context))
                let counts = model.activity["counts"] as? [String: Int] ?? [:]
                line("累計檢查 / 轉交 / 回傳內容", "\(counts["checked"] ?? 0) / \(counts["forwarded"] ?? 0) / \(counts["contextEmitted"] ?? 0)")
                line("排除專案", (model.data["excludedProjects"] as? Int).map { "\($0) 個根目錄" } ?? "未知")
            }.padding(14).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 14))
            Text("轉交不代表一定有經驗可注入；回傳內容也不等於已證實節省額度。紀錄不含提示詞、回答或專案路徑。")
                .font(.system(size: 10)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 10) {
                Button("開啟設定", action: openGUI).buttonStyle(.borderedProminent).tint(Color(red: 0.23, green: 0.48, blue: 0.43))
                Button("重新讀取") { model.refresh?() }
                Spacer()
                Button(action: showFiles) { Image(systemName: "folder") }.help("查看本機紀錄")
                Button("結束", action: quit)
            }.controlSize(.small)
        }.padding(20).frame(width: 450)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    let model = GateModel()
    var item: NSStatusItem!
    let popover = NSPopover()
    var window: NSWindow?
    var process: Process?
    var input: Pipe?
    var buffer = Data()
    var quitting = false
    var base: URL { FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/TE Quota Gate") }
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "TE …"
        item.button?.target = self; item.button?.action = #selector(toggle)
        item.button?.toolTip = "TE Quota Gate：查看額度資格與實際執行紀錄"
        let view = GateView(model: model, openGUI: {
            NSWorkspace.shared.open(URL(string: "http://127.0.0.1:8766/")!)
        }, showFiles: { NSWorkspace.shared.activateFileViewerSelecting([self.base.appendingPathComponent("runtime/hook-activity.json")]) }, quit: { NSApp.terminate(nil) })
        popover.behavior = .transient
        popover.contentViewController = NSHostingController(rootView: view)
        model.refresh = { [weak self] in try? self?.input?.fileHandleForWriting.write(contentsOf: Data("refresh\n".utf8)) }
        startBackend()
        if !CommandLine.arguments.contains("--quiet") {
            let win = NSWindow(contentRect: NSRect(x:0,y:0,width:450,height:610), styleMask:[.titled,.closable,.miniaturizable], backing:.buffered,defer:false)
            win.title = "TE Quota Bar"; win.contentView = NSHostingView(rootView: view); win.center(); win.isReleasedWhenClosed = false
            win.makeKeyAndOrderFront(nil); window = win; NSApp.activate(ignoringOtherApps: true)
        } else { toggle() }
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if let window = window { window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
        return true
    }
    func startBackend() {
        guard let resources = Bundle.main.resourceURL,
              let configuration = NSDictionary(contentsOf: resources.appendingPathComponent("Runtime.plist")),
              let python = configuration["PythonExecutable"] as? String else { model.error = "找不到 Python 執行環境"; return }
        let p = Process(); p.executableURL = URL(fileURLWithPath: python)
        p.arguments = ["-u", "-m", "quota_gate.desktop", "--base", base.path, "--codex", "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"]
        if CommandLine.arguments.contains("--demo") { p.arguments?.append("--demo") }
        p.currentDirectoryURL = resources.appendingPathComponent("python")
        var env = ProcessInfo.processInfo.environment; env.removeValue(forKey: "PYTHONPATH"); env.removeValue(forKey: "PYTHONHOME")
        env["TE_DISABLE"] = "1"; env["TE_SIDECALL"] = "1"; p.environment = env
        let output = Pipe(); let stdin = Pipe(); p.standardOutput = output; p.standardInput = stdin; p.standardError = FileHandle.nullDevice
        input = stdin
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async { self?.consume(data) }
        }
        p.terminationHandler = { [weak self] _ in DispatchQueue.main.async {
            guard let self = self, !self.quitting else { return }
            self.model.error = "監測器已停止，請結束後重新開啟。"; self.item.button?.title = "TE !"
        }}
        do { try p.run(); process = p } catch { model.error = "無法啟動監測器：\(error.localizedDescription)" }
    }
    func consume(_ data: Data) {
        buffer.append(data)
        while let range = buffer.range(of: Data([10])) {
            let line = buffer.subdata(in: buffer.startIndex..<range.lowerBound); buffer.removeSubrange(buffer.startIndex...range.lowerBound)
            if let value = try? JSONSerialization.jsonObject(with: line) as? [String: Any] {
                model.data = value; model.error = ""; item.button?.title = model.barTitle
            }
        }
    }
    @objc func toggle() {
        if popover.isShown { popover.performClose(nil) }
        else if let button = item.button { popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY); NSApp.activate(ignoringOtherApps: true) }
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        quitting = true
        try? input?.fileHandleForWriting.close()
        if let process = process, process.isRunning { process.terminate() }
        return .terminateNow
    }
}
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
