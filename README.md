```markdown
# TRON 鏈上幣流分析與互動網路圖工具

本專案提供一套以 Python 實作的 TRON 鏈上交易分析工具，能自動抓取多個追蹤錢包在指定期間的 TRX 與 TRC20 交易資料，辨識「金主」與「收水錢包」等共同交易對象，輸出完整的 Excel 報表，並產生可在瀏覽器操作的互動式網路圖（支援以分頁頁籤切換不同 Token）。

# 使用前請至主程式第274、275行限縮共同分析時間區段；並參考下方使用教學新增欲追蹤的錢包位址

## 功能總覽

- 抓取 TRON 鏈上交易（TRX 與 TRC20），支援時間區間與最小金額過濾。
- 處理 API 頻率限制（429）自動重試，最大化避免交易遺漏。
- 自動辨識共同交易對象：
  - 金主 Funder：在期間內向多個追蹤錢包付款。
  - 收水 Collector：在期間內從多個追蹤錢包收款。
- 產出靜態報表（Excel），包含：
  - 全部交易總表
  - 各 Token 交易分頁
  - 共同交易對象分析（含每個對象連結之追蹤錢包清單）
  - 各共同交易對象與追蹤錢包的詳細交易明細（獨立工作簿檔）
  - 過濾掉的交易紀錄（若有）
- 產出互動式網路圖（HTML）：
  - 每個 Token 會生成獨立互動圖
  - 並以多分頁（Tabs + iframe）整合至單一 HTML 頁面
  - 節點顏色區分角色並支援滑鼠提示（legend/tooltip）：
    - 橙色：追蹤錢包
    - 紫色：金主 Funder
    - 綠色：收水 Collector
    - 藍色：其他
  - 邊（交易）提示包含 金額 與 時間

## 成功執行程式後與初始文件

- trx_common_analysis.py（主程式）
- wallets.txt（追蹤錢包清單，每行一個地址）
- requirements.txt（套件需求）
- networks_html/（互動式網路圖的分頁 HTML 子目錄，程式執行後自動生成）
- multi_token_networks_tabbed.html（多 Token 分頁互動網路圖主頁）
- transaction_analysis_results.xlsx（主報表）
- common_counterparty_txns.xlsx（共同交易對象的交易明細報表）
- .github/workflows/auto_analysis.yml（可選，GitHub Actions 自動化）

## 環境建置

- Python 版本：建議 Python 3.9（3.8+ 應可正常）
- 套件安裝：建議使用虛擬環境（venv 或 conda）

建立與啟用虛擬環境（以 venv 為例）：
- Windows
  - `python -m venv .venv`
  - `.venv\Scripts\activate`
- macOS/Linux
  - `python3 -m venv .venv`
  - `source .venv/bin/activate`

安裝套件：
- 建議使用 requirements.txt
  - `pip install -r requirements.txt`
- 或手動安裝
  - `pip install requests pandas networkx matplotlib openpyxl tronpy pyvis jinja2==3.1.2`

相容性建議：
- 若遇到 NumPy 2.x 與部分套件不相容，請採用穩定組合（例如 numpy 1.24.x 與對應的 pandas/matplotlib）。
- 若 pandas 提示 numexpr、bottleneck 版本過舊，請升級：
  - `pip install --upgrade numexpr bottleneck`

## 使用教學

1) 準備 wallets.txt  
將要追蹤的 TRON 錢包地址逐行放入，例如：
TXYZ1234...
TABCD5678...

2) 設定期間與參數  
在程式檔（trx_common_analysis.py）最下方 __main__ 區段可調整：
- START / END：分析期間
- MIN_AMOUNT：最小金額過濾
- MIN_CONNECTIONS：判定金主/收水所需連結的追蹤錢包最少數（預設 2）

3) 執行主程式
python trx_common_analysis.py

4) 檢視輸出  
- `transaction_analysis_results.xlsx`：完整靜態報表  
- `common_counterparty_txns.xlsx`：共同交易對象與追蹤錢包之詳細交易明細  
- `networks_html/*.html`：各 Token 的互動式網路圖（子頁）  
- `multi_token_networks_tabbed.html`：多 Token 分頁主頁，直接用瀏覽器開啟即可互動

## 報表與視覺化說明

- All_Transactions：所有交易記錄  
- {TOKEN}_Transactions：某 Token 的交易記錄分頁（如 TRX_Transactions、USDT_Transactions）  
- Common_Counterparties：共同交易對象分析（包含 ConnectedWallets 欄列出對應追蹤錢包清單）  
- Filtered_Transactions：因各種原因被過濾的交易紀錄  
- common_counterparty_txns.xlsx：每個共同對象與追蹤錢包的交易明細（獨立工作表）  
- multi_token_networks_tabbed.html：多 Token 互動圖主頁，分頁切換不同 Token，節點顏色區分角色，滑鼠提示交易金額與時間統計  

## 常見問題（FAQ）

- Q：TronGrid API 回傳 429（Rate Limit）怎麼辦？  
  A：程式已內建自動等待並重試機制，多次遭限流會暫停 30 秒並重試，最多 5 次。建議申請 API Key 或更改時間區間降低請求量。

- Q：為何互動網路圖在同一頁面看不到？  
  A：Pyvis 輸出的 HTML 為完整頁面，本專案以 iframe 方式在主頁整合。請確保 `networks_html` 子目錄與主頁檔案路徑正確，並用支援本機檔案載入的瀏覽器開啟。

- Q：Excel 匯出出現 xlsxwriter 版本警告？  
  A：升級 xlsxwriter（`pip install --upgrade xlsxwriter`），或改用 openpyxl 引擎（已預設）。

- Q：字型或中文亂碼？  
  A：互動圖本身以英文字顯示，若需中文標註，請確保系統有相應字型並調整 matplotlib 設定。

## 兼容性與建議版本

- Python：3.9（建議）  
- numpy：1.24.x 推薦以避免依賴問題  
- pandas、matplotlib、numexpr、bottleneck 等請保持與 numpy 相容的穩定版本  
- jinja2：3.1.2 預設用於 pyvis

