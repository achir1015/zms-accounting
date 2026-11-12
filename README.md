# 資料助秘之一般公司會計
<img width="800" height="500" alt="image" src="https://github.com/user-attachments/assets/ea87b23e-cb89-492a-b201-1ee45a9a0eae" />



單一公司使用的總帳會計系統：基本資料 → 傳票登錄 → 審核過帳 → 日記簿／分類帳 → 財務報表 → 關帳與年度結帳。
資料庫使用 **MariaDB**（安裝版內附，程式開啟自動啟動、關閉自動停止）。

平台規劃：**Windows 11（v1.0.0 起）**、**macOS（v1.2.0 起）** → Android → iPhone → iPad。

下載：[最新版 Releases](https://github.com/achir1015/zms-accounting/releases/latest)

## 安裝（macOS 11 以上，Intel 與 Apple 晶片皆可）
1. 下載 `ZMSAccounting-<版本>-mac.dmg`，開啟後把「資料助秘之一般公司會計」拖到「應用程式」。
2. 第一次開啟：在「應用程式」對 App 按右鍵 → 「打開」→ 再按「打開」（App 未經 Apple 公證，只需第一次這樣做）。
3. 內附 MariaDB 10.11.18（與 Windows 版同版本），開啟自動啟動、結束（含 ⌘Q）自動停止。Apple 晶片 Mac 會透過 Rosetta 2 執行。
4. 資料存放在 `~/Library/Application Support/ZMSAccounting`；程式內「版本更新」會下載新版並自動取代 App 後重新開啟。
5. 建置（在 Mac 上）：`bash tools/build_macos.sh`（會先執行 `tools/prepare_mariadb_mac.sh` 從 Homebrew 封存下載 MariaDB）。

## 安裝（Windows 10／11 64 位元）
1. 執行 `ZMSAccounting-Setup-<版本>.exe`（不需系統管理員權限，裝在 `%LOCALAPPDATA%\Programs\ZMSAccounting`）。
2. 安裝時可勾選「建立桌面捷徑」；開始功能表也會有捷徑。
3. 第一次開啟時建立系統管理員帳號（密碼至少 6 個字）。
4. 會計資料與設定放在 `%LOCALAPPDATA%\ZMSAccounting`，更新或解除安裝都不會刪除。

## 功能
| 群組 | 功能 |
|---|---|
| 傳票作業 | 收入／支出／轉帳／開帳／調整傳票；科目搜尋、摘要自動沿用上一行、自動帶入借貸差額、摘要片語、常用分錄套用（依比率自動算金額）、外幣換算、部門／專案／往來對象；傳票查詢、複製、列印；審核、過帳、退回、作廢、取消過帳 |
| 帳簿查詢 | 日記簿、明細分類帳（含期初與累計餘額、可依往來對象）、總分類帳（1～4 碼層級）、現金簿、往來明細（應收／應付／員工借支） |
| 財務報表 | 試算表、損益表（部門別、去年同期比較）、資產負債表、現金流量表（直接法）、財務比率（公式可自訂）、預算比較；全部可列印／另存 PDF、匯出 Excel |
| 基本資料 | 會計科目（四碼制，預設 199 個科目）、常用分錄（14 組範本）、摘要片語、部門、員工、客戶、廠商、專案、幣別匯率 |
| 期末作業 | 期間關帳（關帳後不能異動）、外幣現值調整（自動產生兌換損益傳票）、年度結帳（損益結轉累積盈虧，可取消重做）、預算編列、比率公式 |
| 系統管理 | 使用者與權限（角色範本＋七項功能「無／查詢／維護」）、製單與審核分離、即時或分批過帳、公司設定、備份還原（.sql.gz）、操作紀錄、版本更新與桌面捷徑 |
| 使用說明 | **前言：系統導入說明**（以虛構範例「祥和貿易股份有限公司」說明導入準備 → 資料整理 → 系統建置 → 期初開帳 → 平行作業 → 正式上線，含日常、每月、年度結帳程序，可列印成導入手冊），加上 38 節功能操作說明；每節都可語音朗讀；每個畫面上方「本頁說明」直接朗讀該頁；損益表／資產負債表可「朗讀重點」 |
| Excel 匯入 | 客戶、廠商、員工、部門、專案、幣別、摘要片語可下載範本後匯入（CSV，Big5 或 UTF-8 皆可，代號已存在就更新）；傳票登錄可「匯入明細」一次帶入期初餘額等大量分錄 |

### 權限
| 角色 | 基本資料 | 傳票登錄 | 審核過帳 | 帳簿 | 財務報表 | 期末作業 | 系統管理 |
|---|---|---|---|---|---|---|---|
| 系統管理員 | 全部 | | | | | | |
| 會計主管 | 維護 | 維護 | 維護 | 維護 | 維護 | 維護 | 無 |
| 會計人員 | 維護 | 維護 | 無 | 查詢 | 查詢 | 無 | 無 |
| 出納 | 查詢 | 維護 | 無 | 查詢 | 無 | 無 | 無 |
| 查帳人員 | 查詢 | 查詢 | 無 | 查詢 | 查詢 | 無 | 無 |

## 語音
- 使用說明：建置時用微軟神經語音（臺灣華語「曉臻」）預先產生 MP3（`assets/voice`），離線可播。
- 報表重點等即時文字：有網路用神經語音，沒有網路改用 Windows 內建「Microsoft Hanhan」臺灣中文語音。

## 版本更新
程式開啟時檢查 GitHub Releases 最新版；有新版時上方出現提示，按「下載並安裝」會靜默安裝後自動重新開啟。
發佈新版：改 `acct/__init__.py` 的 `APP_VERSION` → `python tools/build_windows.py` → 在 GitHub 建立 `v<版本>` Release 並上傳 `ZMSAccounting-Setup-<版本>.exe`。

## 開發
```bash
python -m venv .venv
.venv\Scripts\pip install flet==1.1.2 flet-desktop==1.1.2 pymysql edge-tts pillow pytest pyinstaller
.venv\Scripts\python main.py               # 桌面版（資料在 data\）
.venv\Scripts\python -m pytest -q tests    # 7 項測試（自動啟動測試用 MariaDB，連接埠 3348）
.venv\Scripts\python tools\build_windows.py
```
- 需要 `C:\mariadb`（MariaDB 10.11 Windows 版）與 Inno Setup 6。
- `run_web.py`：網頁模式預覽（http://127.0.0.1:8560，開發用自動登入）；`tools/shots_all.py` 逐頁截圖；`tools/demo_data.py` 寫入示範交易。

系統開發：吳玉柱 先生 與 Claude AI Opus 5.5
