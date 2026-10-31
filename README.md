# Codex TE Quota Gate

Only allow **TokenEconomizer's `envfacts`** when either the **5-hour** or **weekly**
Codex quota has **less than 15% remaining**. Keep all tools available and the loop guard off.

**Status: executable prototype, not installed on the author's Codex environment.**
The offline policy, subprocess protocol and generated hook bridge are tested. Real desktop
hook loading, live account integration, quota savings and research-answer quality are not
established. This project is independent of Microsoft and OpenAI.

## 這是什麼？

這個本機工具替 [Microsoft TokenEconomizer](https://github.com/microsoft/TokenEconomizer)
加上額度門檻。它不會更換你的主要模型，也不會自動安裝或核准任何插件。

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
       │
Codex hook → gate → 任一剩餘 <15% 且資料有效？
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
python3 -m quota_gate evaluate --snapshot runtime/quota.json
```

`capture` 只送出 `initialize`、`initialized` 和 `account/rateLimits/read`。
任何 server-initiated 請求都回覆不支援，不會核准權限、購買 credits 或消耗重設次數。
失敗時立即覆寫成無效快照。stdout 顯示判斷結果，不輸出原始帳號回應。

### 2. 取得經查核的上游版本，產生可審閱的本機 marketplace

```bash
git clone https://github.com/microsoft/TokenEconomizer.git ../TokenEconomizer
git -C ../TokenEconomizer checkout --detach e428fc91b0f8ffecb5a596d56b14fe2f1485a5f9
python3 scripts/check_upstream.py --source ../TokenEconomizer
python3 -m quota_gate build --source ../TokenEconomizer --output local-marketplace --snapshot runtime/quota.json
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
- 不啟用完整 distiller 或 loop guard，不應套用上游宣稱的 18–31% 成本降幅。
- 兩個額度視窗都需有效；未知欄位、錯誤 bucket、非法數字、過期與讀取失敗皆停用。
- 此版本只管理指定 `codex` bucket。切換帳號／workspace／計費 bucket 時，
  先停止 reader 並移除快照，再以同一目標環境重新啟動；不跨帳號共用 runtime。
- 不對已耗盡的訂閱額度提供繞過、補充或自動付費方式。

## 驗證與來源

見 [驗證報告](docs/VALIDATION.md) 與 [資料流和權限](docs/PRIVACY.md)。
CI 僅執行離線測試，不需要帳號、密鑰或模型費用。

- [OpenAI app-server：初始化與額度讀取](https://learn.chatgpt.com/docs/app-server)
- [OpenAI hooks：由使用者檢閱／信任](https://learn.chatgpt.com/docs/hooks)
- [TokenEconomizer 設定與卸載](https://github.com/microsoft/TokenEconomizer/blob/e428fc91b0f8ffecb5a596d56b14fe2f1485a5f9/plugin/README.md)
- [TokenEconomizer hook dispatcher](https://github.com/microsoft/TokenEconomizer/blob/e428fc91b0f8ffecb5a596d56b14fe2f1485a5f9/tokeneconomizer/plugin/hook.py)

MIT license for this wrapper. Upstream TokenEconomizer remains under its own Apache-2.0 license;
its implementation is not redistributed here.
