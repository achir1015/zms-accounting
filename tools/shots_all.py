"""開發用：逐一截圖各畫面（需以 run_web.py 啟動，且設定 ACCT_DEV_LOGIN）。

用法：python tools/shots_all.py 輸出資料夾 [畫面代號…]
"""
import base64
import os
import sys
import time

from playwright.sync_api import sync_playwright

SCREENS = ["home", "voucher_entry", "voucher_list", "voucher_review", "journal", "ledger", "general_ledger",
           "cash_book", "partner_ledger", "trial_balance", "income", "balance_sheet", "cash_flow", "ratios",
           "budget_compare", "accounts", "templates", "phrases", "departments", "employees", "customers", "vendors",
           "projects", "currencies", "periods", "revaluation", "year_end", "budget_edit", "ratio_setup", "users",
           "company", "backup", "update", "audit", "help"]


def main():
    out = sys.argv[1]
    names = sys.argv[2:] or SCREENS
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        for n in names:
            pg = b.new_page(viewport={"width": int(os.environ.get("SHOT_W", 1440)), "height": int(os.environ.get("SHOT_H", 900))})
            errors = []
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            pg.goto(os.environ.get("SHOT_BASE", "http://127.0.0.1:8560/") + n)
            time.sleep(7)
            cdp = pg.context.new_cdp_session(pg)
            with open(os.path.join(out, n.replace("?", "_").replace(",", "-").replace("=", "-").replace("/", "_") + ".png"), "wb") as f:
                f.write(base64.b64decode(cdp.send("Page.captureScreenshot", {"format": "png"})["data"]))
            print(n, "errors:", errors[:2] if errors else "none", flush=True)
            pg.close()
        b.close()


if __name__ == "__main__":
    main()
