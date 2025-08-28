import os
import requests
import time
import pandas as pd
from datetime import datetime
from time import perf_counter
import warnings
import networkx as nx
from pyvis.network import Network

warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)

DEBUG_FILTER = True
MIN_CONNECTIONS = 2
MIN_AMOUNT = 1

def read_wallets(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Wallet list error: {e}")
        return []

class TransactionFetcher:
    def __init__(self, start_date, end_date, min_amount=1):
        self.start_date = start_date
        self.end_date = end_date
        self.min_amount = min_amount
        self.api_base = "https://api.trongrid.io"
        self.filtered_records = []

    def hex_to_address(self, hex_addr):
        if not hex_addr: return ""
        if hex_addr.startswith("41"):
            try:
                from tronpy.keys import to_base58check_address
                return to_base58check_address(bytes.fromhex(hex_addr))
            except:
                return hex_addr
        return hex_addr

    def fetch_paginated(self, url, params):
        all_items = []
        seen_txids = set()
        fail_count = 0
        while url:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code == 429:
                print("TronGrid rate limited, sleeping for 30 seconds...")
                time.sleep(30)
                fail_count += 1
                if fail_count > 5:
                    print("Repeated rate limits, aborting...")
                    break
                continue
            if not r.ok:
                print(f"API error {url} | {r.status_code}")
                time.sleep(2)
                break
            fail_count = 0
            resp = r.json()
            batch = resp.get('data', [])
            for item in batch:
                txid = item.get('txID') or item.get('transaction_id') or ''
                if txid in seen_txids:
                    continue
                seen_txids.add(txid)
                all_items.append(item)
            url = resp.get('meta', {}).get('links', {}).get('next')
            params = {}
            time.sleep(0.2)
        return all_items

    def fetch_trx(self, wallet):
        url = f"{self.api_base}/v1/accounts/{wallet}/transactions"
        params = {"limit": 200, "only_confirmed": "true", "order_by": "block_timestamp,asc"}
        txs = []
        for item in self.fetch_paginated(url, params):
            ts = datetime.utcfromtimestamp(item["block_timestamp"] // 1000)
            for c in item.get("raw_data", {}).get("contract", []):
                if c.get("type") != "TransferContract":
                    continue
                v = c["parameter"]["value"]
                amt = v.get("amount", 0) / 1_000_000
                from_addr = self.hex_to_address(v.get("owner_address", ""))
                to_addr = self.hex_to_address(v.get("to_address", ""))
                if not self.filter_and_debug(ts, amt, tx_id=item.get("txID"),
                                             from_addr=from_addr, to_addr=to_addr,
                                             token="TRX"):
                    continue
                txs.append({"From": from_addr, "To": to_addr, "Amount": amt, "Token": "TRX", "Time": ts})
        return txs

    def fetch_trc20(self, wallet):
        url = f"{self.api_base}/v1/accounts/{wallet}/transactions/trc20"
        params = {"limit": 200, "only_confirmed": "true", "order_by": "block_timestamp,asc"}
        txs = []
        for ev in self.fetch_paginated(url, params):
            ts = datetime.utcfromtimestamp(ev["block_timestamp"] // 1000)
            token_addr = ev.get("token_info", {}).get("address", "")
            sym = ev.get("token_info", {}).get("symbol", "TRC20")
            amt = int(ev.get("value", 0)) / (10 ** ev.get("token_info", {}).get("decimals", 6))
            from_addr = self.hex_to_address(ev.get("from", ""))
            to_addr = self.hex_to_address(ev.get("to", ""))
            if not self.filter_and_debug(ts, amt, token_addr=token_addr,
                                         tx_id=ev.get("transaction_id"),
                                         from_addr=from_addr, to_addr=to_addr,
                                         token=sym):
                continue
            txs.append({"From": from_addr, "To": to_addr, "Amount": amt, "Token": sym, "Time": ts})
        return txs

    def filter_and_debug(self, ts, amount, token_addr=None, expected_addr=None,
                         tx_id="N/A", from_addr="", to_addr="", token=""):
        reasons = []
        if not (self.start_date <= ts <= self.end_date):
            reasons.append(f"Time out of range {ts}")
        if expected_addr and token_addr and expected_addr.lower() != token_addr.lower():
            reasons.append(f"Contract mismatch {token_addr}")
        if amount < self.min_amount:
            reasons.append(f"Amount too small {amount}")
        if reasons:
            self.filtered_records.append({
                "TxID": tx_id, "From": from_addr, "To": to_addr,
                "Amount": amount, "Token": token, "Time": ts,
                "Filtered_Reasons": " / ".join(reasons)
            })
            if DEBUG_FILTER:
                print("[Filtered]", tx_id, "->", " / ".join(reasons))
            return False
        return True

def detailed_common_analysis(df, tracked_wallets, min_connections=2):
    funders = {}
    collectors = {}
    all_addrs = set(df["From"]) | set(df["To"])
    for addr in all_addrs:
        if addr in tracked_wallets:
            continue
        out = df[(df["From"] == addr) & (df["To"].isin(tracked_wallets))]
        if len(out["To"].unique()) >= min_connections:
            funders[addr] = {"txs": out, "wallets": sorted(out["To"].unique())}
        inc = df[(df["To"] == addr) & (df["From"].isin(tracked_wallets))]
        if len(inc["From"].unique()) >= min_connections:
            collectors[addr] = {"txs": inc, "wallets": sorted(inc["From"].unique())}
    records = []
    for role, dic in [("Funder", funders), ("Collector", collectors)]:
        for addr, info in dic.items():
            txs = info["txs"]
            wallet_list = info["wallets"]
            records.append({
                "Address": addr,
                "Role": role,
                "ConnectedWalletCount": len(wallet_list),
                "ConnectedWallets": ",".join(wallet_list),
                "TotalAmount": round(txs["Amount"].sum(), 4),
                "AvgAmount": round(txs["Amount"].mean(), 4),
                "TxCount": len(txs),
                "Tokens": ",".join(sorted(txs["Token"].unique())),
                "FirstTx": txs["Time"].min(),
                "LastTx": txs["Time"].max()
            })
    df_result = pd.DataFrame(records)
    if not df_result.empty:
        df_result = df_result.sort_values(["ConnectedWalletCount", "TotalAmount"], ascending=False)
    return df_result

def export_common_tx_details(df_common_detail, df_all, wallets, filename="common_counterparty_txns.xlsx"):
    with pd.ExcelWriter(filename) as writer:
        for idx, row in df_common_detail.iterrows():
            addr = row["Address"]
            role = row["Role"]
            if role == "Funder":
                txs = df_all[(df_all["From"] == addr) & (df_all["To"].isin(wallets))]
            else:
                txs = df_all[(df_all["To"] == addr) & (df_all["From"].isin(wallets))]
            if not txs.empty:
                sheet_name = f"{role}_{addr[:6]}..."
                try:
                    txs.sort_values(by="Time").to_excel(writer, sheet_name=sheet_name[:31], index=False)
                except Exception as e:
                    print(f"Warning: sheet name too long or error exporting {sheet_name}: {e}")

def save_pyvis_html(token, df, tracked_wallets, funders, collectors, folder="networks_html"):
    import os
    if not os.path.exists(folder):
        os.makedirs(folder)
    d = df[df["Token"] == token]
    valid_nodes = set(funders) | set(collectors) | set(tracked_wallets)
    d = d[d["From"].isin(valid_nodes) & d["To"].isin(valid_nodes)]
    if d.empty:
        print(f"{token} No eligible graph nodes")
        return None
    G = nx.DiGraph()
    for _, r in d.iterrows():
        s, t = r["From"][:8], r["To"][:8]
        label_time = r["Time"].strftime('%m-%d %H:%M')
        label = f"Amount: {r['Amount']:.4f}<br>Time: {label_time}"
        if G.has_edge(s, t):
            G[s][t]['weight'] += r["Amount"]
            G[s][t]['count'] += 1
        else:
            G.add_edge(s, t, weight=r["Amount"], count=1, label=label)
    nt = Network(height="600px", width="100%", directed=True)
    nt.barnes_hut()
    for n in G.nodes():
        full = next((x for x in valid_nodes if x.startswith(n)), None)
        if full in tracked_wallets:
            color = "orange"
            title = "Tracked Wallet"
        elif full in funders:
            color = "purple"
            title = "Funder"
        elif full in collectors:
            color = "green"
            title = "Collector"
        else:
            color = "lightblue"
            title = "Other"
        nt.add_node(n, label=n, title=title, color=color)
    for u, v in G.edges():
        e = G[u][v]
        title = f"{e['label']}<br>Tx Count: {e['count']}"
        width = 1 + e['weight'] * 3 / max([data['weight'] for _, _, data in G.edges(data=True)])
        nt.add_edge(u, v, value=width, title=title, arrows='to')
    filename = os.path.join(folder, f"{token}_network.html")
    nt.write_html(filename, open_browser=False)
    print(f"Saved {filename}")
    return filename

def generate_tabs_html(filenames_dict):
    tabs_header = """
    <html><head>
    <style>
    body {font-family: Arial; margin:10px;}
    .tab {overflow: hidden; border-bottom: 1px solid #ccc;}
    .tab button {
        background-color: inherit; border: none; outline: none; cursor: pointer;
        padding: 10px 20px; transition: 0.3s; font-size:14px;
    }
    .tab button:hover {background-color: #ddd;}
    .tab button.active {background-color: #ccc;}
    .tabcontent {display: none; padding: 10px 0px; height: 620px;}
    iframe {border:none; width: 100%; height: 100%;}
    </style>
    <script>
    function openTab(evt, tabName) {
      var i, tabcontent, tablinks;
      tabcontent = document.getElementsByClassName("tabcontent");
      for (i = 0; i < tabcontent.length; i++) { tabcontent[i].style.display = "none"; }
      tablinks = document.getElementsByClassName("tablinks");
      for (i = 0; i < tablinks.length; i++) { tablinks[i].className = tablinks[i].className.replace(" active", ""); }
      document.getElementById(tabName).style.display = "block";
      evt.currentTarget.className += " active";
    }
    window.onload = function() {
      document.getElementsByClassName('tablinks')[0].click();
    }
    </script>
    </head><body>
    """
    tabs_buttons = '<div class="tab">\n'
    tabs_contents = ''
    for token, filepath in filenames_dict.items():
        tabs_buttons += f'<button class="tablinks" onclick="openTab(event, \'{token}\')">{token}</button>\n'
        tabs_contents += f'<div id="{token}" class="tabcontent">\n'
        tabs_contents += f'<iframe src="{filepath}"></iframe>\n</div>\n'
    tabs_footer = "</body></html>"
    return tabs_header + tabs_buttons + tabs_contents + tabs_footer

if __name__ == "__main__":
    START = datetime(yyyy, mm, dd)
    END = datetime(yyyy, mm, dd)
    wallets = read_wallets("wallets.txt")
    if not wallets:
        print("No wallets loaded, exiting.")
        exit(1)

    fetcher = TransactionFetcher(START, END, MIN_AMOUNT)
    all_tx = []
    for idx, w in enumerate(wallets, 1):
        print(f"[{idx}/{len(wallets)}] Fetching {w[:6]}...")
        all_tx += fetcher.fetch_trx(w)
        all_tx += fetcher.fetch_trc20(w)
    df_all = pd.DataFrame(all_tx)
    if df_all.empty:
        print("No transaction records found.")
        exit(1)

    df_common_detail = detailed_common_analysis(df_all, wallets, min_connections=MIN_CONNECTIONS)
    funders = df_common_detail[df_common_detail["Role"] == "Funder"]["Address"].tolist()
    collectors = df_common_detail[df_common_detail["Role"] == "Collector"]["Address"].tolist()
    tokens = list(df_all["Token"].unique())

    # 生成各 Token 獨立互動網路圖 HTML
    html_files = {}
    for token in tokens:
        file = save_pyvis_html(token, df_all, wallets, funders, collectors)
        if file:
            html_files[token] = file

    # 生成含多分頁 iframe 切換的主頁 HTML
    master_html = generate_tabs_html(html_files)
    with open("multi_token_networks_tabbed.html", "w", encoding="utf-8") as f:
        f.write(master_html)
    print("Generated multi_token_networks_tabbed.html - open with a browser.")

    # 匯出 Excel
    with pd.ExcelWriter("transaction_analysis_results.xlsx", engine="openpyxl") as writer:
        df_all.to_excel(writer, sheet_name="All_Transactions", index=False)
        for token in tokens:
            df_all[df_all["Token"] == token].to_excel(writer, sheet_name=f"{token}_Transactions", index=False)
        if not df_common_detail.empty:
            df_common_detail.to_excel(writer, sheet_name="Common_Counterparties", index=False)
        export_common_tx_details(df_common_detail, df_all, wallets)
        if fetcher.filtered_records:
            pd.DataFrame(fetcher.filtered_records).to_excel(writer, sheet_name="Filtered_Transactions", index=False)
    print("Excel Export Complete.")
