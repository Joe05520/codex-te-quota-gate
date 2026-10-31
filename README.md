# Codex TE Quota Gate

Only allow **TokenEconomizer's `envfacts`** when either the **5-hour** or **weekly**
Codex quota falls below its own configurable remaining-percentage threshold (default: 15%).
Exclude selected project folders. Adjust everything through a local browser GUI.
Keep all tools available and the loop guard off.

**Status: executable prototype, not installed on the author's Codex environment.**
The local GUI, shared settings, policy, subprocess protocol and generated hook bridge are tested. Real desktop
hook loading, live account integration, quota savings and research-answer quality are not
established. This project is independent of Microsoft and OpenAI.

## 這是什麼？

這個本機工具替 [Microsoft TokenEconomizer](https://github.com/microsoft/TokenEconomizer)
加上額度門檻。它不會更換你的主要模型，也不會自動安裝或核准任何插件。

## v0.2.0：GUI、兩個獨立門檻與專案排除

```bash
python3 -m quota_gate gui --demo --open
```

macOS 也可雙擊專案根目錄的 **`launch_demo.command`**。正式本機設定介面使用
`python3 -m quota_gate gui --open`，或雙擊 **`launch_gui.command`**。
需要已安裝的 Python 3.10+；啟動器不會安裝軟體。GUI 僅綁定 `127.0.0.1`，
不建立公網網站、不接入帳號、不自動啟動 quota reader，也不安裝插件。

![GUI：分開調整 5h / weekly 門檻，合成資料](docs/gui-overview.png)

- 兩個門檻可各自用數字或滑桿設定 **0–100%**；0 表示不使用該視窗觸發。
- 仍採 **OR**：任一剩餘比例嚴格低於對應門檻就符合條件；等於門檻不觸發。
- 手動加入專案完整路徑，切換參與開關。新增專案預設不參與，須儲存才生效。
- 排除涵蓋該路徑與子資料夾，使用正規化路徑比對；相似前綴資料夾不會被誤排除。
- 未列出的專案預設參與；其他位置的 clone/worktree 必須另外加入。
- 「試算某個專案」使用尚未儲存的畫面設定，**不執行 TokenEconomizer**。
- 「儲存設定」會寫入共用設定檔，之後每次 hook 都重新讀取，不必重建 bundle。
- GUI 不會掃描專案檔案。設定存在本機，`runtime/` 已由 git 排除。

![GUI：專案參與開關與子資料夾排除試算，合成資料](docs/gui-projects.png)

預設一般模式共用 `runtime/settings.json` 與 `runtime/quota.json`；demo 使用
獨立的 `runtime/demo/`。**Demo 的設定不會偷偷套用到一般模式。**
若你的既有 bundle 使用其他 runtime，使用 `--settings` 與 `--snapshot` 指向相同檔案。

以下是預設 15% / 15% 的行為；調整門檻後會依各自的新門檻判斷：

| 5 小時剩餘 | 每週剩餘 | 行為 |
|---:|---:|---|
| 40% | 60% | 不呼叫 TokenEconomizer hook |
| 14% | 60% | 允許 `envfacts` |
| 40% | 14% | 允許 `envfacts` |
| 15% | 15% | 不呼叫 TokenEconomizer hook |
| 資料過期、缺少一個視窗、額度已重設但未重讀 | — | 不呼叫 TokenEconomizer hook |

預設強制 `microskills=envfacts`、`toolprune=off`、`loopguard=off`、`repomap=off`。
插件資料使用獨立目錄，避免混入另一套 TokenEconomizer 先前學到的內容。
這減少能力受影響的途徑，**不代表已證明品質完全相同，也不保證可以省多少額度**。

## 先看離線展示

Python 3.10+，只有標準函式庫。從此專案根目錄執行，無需 pip 安裝：

```bash
python3 -m quota_gate demo
python3 -m unittest discover -s tests -v
```

這兩個命令使用合成資料和臨時目錄，不登入、不讀取個人對話、不呼叫模型，
也不安裝插件。範例輸出見 [離線展示](docs/demo.txt)。

## 運作架構

```text
Codex app-server: account/rateLimits/read
       │  本機 quota reader，預設每 60 秒一次；不建立 thread/turn
       ▼
runtime/quota.json（只保存時間、bucket 和額度視窗）
runtime/settings.json（GUI / CLI / hook 共用的獨立門檻與專案參與設定）
       │
Codex hook → gate → 此專案未排除，且任一剩餘低於對應門檻，且資料有效？
                       ├─ 否 → {}
                       └─ 是 → pinned TokenEconomizer bootstrap
                               envfacts only / dedicated state
```

辨識視窗使用 `windowDurationMins=300 / 10080`，不假設 primary 一定是 5 小時。
優先使用 `rateLimitsByLimitId.codex`，避免混用其他模型或方案的 bucket。
某些方案只回傳 weekly；本版會停用，**不猜測缺失視窗的意思**。

## 在你看過原型後，才進行實際整合

目前 collector 與產生的 shell hook 限 macOS/Linux。實際整合需要可用的 Codex CLI
（登入既有 ChatGPT 帳號）以及你手動信任 hook。不需要 API key。
桌面 App 是否載入同一個插件／hook 環境，必須在目標版本另外確認。

### 1. 只讀取額度，尚不接入插件

先確認 `codex` 可執行。若它不在 PATH，使用你確認過的 CLI 完整路徑；本工具不會
自行下載 CLI、尋找登入憑證、登入、刷新登入或更換帳號。

```bash
python3 -m quota_gate capture --codex /absolute/path/to/codex --output runtime/quota.json
python3 -m quota_gate evaluate --snapshot runtime/quota.json --settings runtime/settings.json --project /absolute/path/to/project
```

`capture` 只送出 `initialize`、`initialized` 和 `account/rateLimits/read`。
任何 server-initiated 請求都回覆不支援，不會核准權限、購買 credits 或消耗重設次數。
失敗時立即覆寫成無效快照。stdout 顯示預設門檻的額度判斷，不輸出原始帳號回應；
已自訂門檻／專案時以 GUI 或帶 `--settings --project` 的 `evaluate` 為準。
先開 GUI 儲存設定，或由 `build` 建立預設設定後，再執行上面的 `evaluate`。

### 2. 取得經查核的上游版本，產生可審閱的本機 marketplace

```bash
git clone https://github.com/microsoft/TokenEconomizer.git ../TokenEconomizer
git -C ../TokenEconomizer checkout --detach e428fc91b0f8ffecb5a596d56b14fe2f1485a5f9
python3 scripts/check_upstream.py --source ../TokenEconomizer
python3 -m quota_gate build --source ../TokenEconomizer --output local-marketplace --snapshot runtime/quota.json --settings runtime/settings.json
```

`build` 要求乾淨、符合指定 commit 的上游 checkout，並在新目錄產生 hooks、manifest
和本機路徑設定。**它不安裝、不修改 Codex config、不核准 hook**。每次執行產生的
hook，都會比對上游 Python 程式的 SHA-256；上游新增、刪除或修改程式時停止轉交。
這是更新防護，不是對未知上游程式的安全認證。保留上游 clone 和所用 Python 的位置。

### 3. 手動檢閱並接入

先閱讀 [整合與回復說明](docs/INTEGRATION.md)，尤其是獨立原版插件與既有 deny list。
確認產生的 `local-marketplace/plugin/hooks/codex-hooks.json` 後，才使用：

```bash
codex plugin marketplace add "$PWD/local-marketplace"
codex plugin add te-quota-gate@te-quota-gate
```

Codex 要求時由使用者審閱並信任這個 hook。此工具不代為核准。
接著在另一個終端機保持額度 reader 執行：

```bash
python3 -m quota_gate watch --codex /absolute/path/to/codex --output runtime/quota.json
```

Ctrl+C 停止 reader，並使快照無效。不設定 launchd、排程工作或背景常駐。
崩潰時，快照最晚在 90 秒後失效；已到 `resetsAt` 的快照立即失效。
預設 60 秒更新意味門檻跨越並非即時偵測，正常情況約在下一次更新與 hook 時點生效。

## 能力代價與重要限制

- 不關閉圖片檢視、子代理、網路或其他工具，也不改主要模型／reasoning effort。
- `envfacts` 仍會把學到的操作經驗加入上下文，經驗可能過時；沒有「品質零損失」證明。
- 本工具和指定的保守功能不主動呼叫模型；注入的文字本身仍會成為日後模型輸入。
- 額度高時不轉交新的 upstream hooks，但 gate 本身仍需執行，reader 仍需讀額度。
- 已加入對話的文字不會在額度恢復後從歷史中消失。需要完全乾淨的上下文時開新對話。
- 上游可在有效的 hook 中啟動 detached fold；已啟動的工作不會因之後恢復額度而被終止。
- Facts 主要在有效的 SessionStart 注入。中途跌破門檻可以開始處理有效 hooks，
  但不保證當下立刻注入新經驗或節省額度；效果可能到之後的有效 session 才出現。
- 不修改／還原以前安裝的原版 TokenEconomizer 所留下的工具 deny list。
- 專案排除比對每次 hook 的 `cwd`，不會清除已學資料、撤回已注入內容或停止已啟動的 fold。
  請讓一段 Codex 對話專注在一個專案；這不是混合專案對話的內容刪除／隱私隔離工具。
- 不啟用完整 distiller 或 loop guard，不應套用上游宣稱的 18–31% 成本降幅。
- 兩個額度視窗都需有效；未知欄位、錯誤 bucket、非法數字、過期與讀取失敗皆停用。
- 此版本只管理指定 `codex` bucket。切換帳號／workspace／計費 bucket 時，
  先停止 reader 並移除快照，再以同一目標環境重新啟動；不跨帳號共用 runtime。
- 不對已耗盡的訂閱額度提供繞過、補充或自動付費方式。

## 驗證與來源

見 [驗證報告](docs/VALIDATION.md) 與 [資料流和權限](docs/PRIVACY.md)。
CI 僅執行離線測試，不需要帳號、密鑰或模型費用。v0.1.0 使用者請參考
[升級與共用設定說明](docs/INTEGRATION.md#upgrading-from-v010)；舊版已複製的 bundle 不會自動獲得 GUI 設定功能。

- [OpenAI app-server：初始化與額度讀取](https://learn.chatgpt.com/docs/app-server)
- [OpenAI hooks：由使用者檢閱／信任](https://learn.chatgpt.com/docs/hooks)
- [TokenEconomizer 設定與卸載](https://github.com/microsoft/TokenEconomizer/blob/e428fc91b0f8ffecb5a596d56b14fe2f1485a5f9/plugin/README.md)
- [TokenEconomizer hook dispatcher](https://github.com/microsoft/TokenEconomizer/blob/e428fc91b0f8ffecb5a596d56b14fe2f1485a5f9/tokeneconomizer/plugin/hook.py)

MIT license for this wrapper. Upstream TokenEconomizer remains under its own Apache-2.0 license;
its implementation is not redistributed here.
