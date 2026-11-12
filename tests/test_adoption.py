"""導入說明的範例資料必須真的能在系統跑出說明裡寫的數字。"""
import csv
import datetime as dt
from decimal import Decimal

from acct import adoption, csvio
from acct.reports import Reports


def write_csv(path, rows, enc):
    with open(path, "w", encoding=enc, newline="") as f:
        csv.writer(f).writerows(rows)


def test_import_and_opening_balance(books, tmp_path):
    cust = tmp_path / "customers.csv"
    write_csv(cust, [["客戶代號", "客戶名稱", "統一編號", "使用中"], ["C001", "大成貿易股份有限公司", "12345675", "是"],
                     ["C002", "永信科技有限公司", "", ""]], "cp950")          # Excel 預設 Big5
    ok, errs = csvio.import_masters(books, "customers", str(cust))
    assert ok == 2 and not errs
    vend = tmp_path / "vendors.csv"
    write_csv(vend, [["廠商代號", "廠商名稱"], ["V001", "永豐材料行"], ["V002", "全國物流股份有限公司"], ["", "缺代號"]],
              "utf-8-sig")
    ok, errs = csvio.import_masters(books, "vendors", str(vend))
    assert ok == 2 and len(errs) == 1
    ok, errs = csvio.import_masters(books, "customers", str(cust))            # 再匯一次＝更新，不會重複
    assert ok == 2 and len(books.master_rows("customers")) == 2

    # 把導入說明裡的期初餘額表轉成 CSV，再用「匯入明細」讀回來開帳
    table = next(b for b in adoption.BY_KEY["adopt_data"]["blocks"] if b[0] == "table" and b[1][0] == "科目")
    rows = [r for r in table[2] if not r[0].startswith("合")]
    path = tmp_path / "opening.csv"
    write_csv(path, [csvio.VOUCHER_COLS] + [[r[0], "期初餘額", r[2], r[3], "", r[1]] for r in rows], "utf-8-sig")
    lines = csvio.read_voucher_lines(str(path))
    assert len(lines) == len(rows)
    vid = books.save_voucher(None, "115/01/01", "開帳", "期初開帳", lines)
    assert books.voucher(vid)["total"] == Decimal(4_606_000)
    books.db.exec("UPDATE company SET separate_approver=0 WHERE id=1")
    books.approve_and_post([vid])

    bs = Reports(books).balance_sheet(dt.date(2026, 1, 1))
    assert bs["balanced"]
    assert (bs["assets"], bs["liabilities"], bs["equity"]) == (Decimal(4_161_400), Decimal(1_246_400),
                                                                Decimal(2_915_000))
    ar = {r["code"]: r["balance"] for r in Reports(books).partner_balances("C", dt.date(2026, 1, 1))
          if r["account"] == "1141"}
    assert ar == {"C001": Decimal(280_000), "C002": Decimal(180_000)}


def test_cost_of_goods_example_balances():
    sec = adoption.BY_KEY["adopt_yearly"]
    table = next(b for b in sec["blocks"] if b[0] == "table")
    num = lambda s: Decimal(s.replace(",", "") or 0)  # noqa: E731
    assert sum(num(r[1]) for r in table[2]) == sum(num(r[2]) for r in table[2])
    assert num("7,420,000") - num("1,050,000") == Decimal(6_370_000)


def test_spoken_text():
    for s in adoption.SECTIONS:
        t = adoption.spoken(s)
        assert t.startswith(s["title"]) and len(t) > 40
