"""開發用：在開發資料庫（data/）寫入一年份示範交易，方便檢查畫面與報表。

用法：先開過一次程式（建立資料庫與管理員 admin），再執行 python tools/demo_data.py
"""
import datetime as dt
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acct.books import Books  # noqa: E402
from acct.database import DB  # noqa: E402
from acct.settings import Settings  # noqa: E402

random.seed(7)
st = Settings.load()
db = DB(st)
b = Books(db)
b.user = db.row("SELECT * FROM users WHERE is_admin=1 LIMIT 1")
db.exec("UPDATE company SET name='示範股份有限公司', tax_id='12345675', owner='王大明', phone='02-2345-6789', "
        "address='臺北市內湖區瑞光路 100 號', separate_approver=0 WHERE id=1")
for code, name in (("C001", "大成貿易股份有限公司"), ("C002", "永信科技有限公司"), ("C003", "安心醫材行")):
    db.exec("INSERT IGNORE INTO partners (kind, code, name) VALUES ('C', %s, %s)", (code, name))
for code, name in (("V001", "永豐材料行"), ("V002", "全國物流股份有限公司"), ("V003", "群創文具")):
    db.exec("INSERT IGNORE INTO partners (kind, code, name) VALUES ('V', %s, %s)", (code, name))
for code, name, dept in (("E001", "林雅婷", "100"), ("E002", "陳志明", "200"), ("E003", "黃美玲", "200")):
    db.exec("INSERT IGNORE INTO employees (code, name, dept) VALUES (%s, %s, %s)", (code, name, dept))


def v(date, t, lines, memo=""):
    return b.save_voucher(None, date, t, memo, lines)


v(dt.date(2026, 1, 1), "開帳", [dict(account="1113", debit=2_000_000, summary="期初餘額"),
                                dict(account="1111", debit=50_000, summary="期初餘額"),
                                dict(account="1451", debit=300_000, summary="期初餘額"),
                                dict(account="3111", credit=2_350_000, summary="期初股本")], "期初開帳")
for m in range(1, 12):
    d = lambda day: dt.date(2026, m, day)  # noqa: E731
    for i in range(random.randint(2, 3)):
        amt = random.randrange(80_000, 260_000, 1000)
        cust = random.choice(["C001", "C002", "C003"])
        v(d(3 + i * 7), "轉", [dict(account="1141", debit=amt * 1.05, partner=cust, summary="銷貨"),
                               dict(account="4111", credit=amt, summary="銷貨"),
                               dict(account="2161", credit=amt * 0.05, summary="銷項稅額")], "銷貨")
        if m < 11 or i == 0:
            v(d(20 + i), "收", [dict(account="1113", debit=amt * 1.05, summary="收回貨款"),
                               dict(account="1141", credit=amt * 1.05, partner=cust, summary="收回貨款")], "收款")
    pur = random.randrange(50_000, 140_000, 1000)
    v(d(5), "轉", [dict(account="5112", debit=pur, summary="進貨"), dict(account="1161", debit=pur * 0.05,
                                                                   summary="進項稅額"),
                   dict(account="2131", credit=pur * 1.05, partner="V001", summary="進貨")], "進貨")
    v(d(25), "支", [dict(account="2131", debit=pur * 1.05, partner="V001", summary="支付貨款"),
                    dict(account="1113", credit=pur * 1.05, summary="支付貨款")], "付款")
    v(d(5), "支", [dict(account="6212", debit=40_000, summary="支付本月房租", dept="100"),
                   dict(account="1113", credit=40_000, summary="支付本月房租")], "房租")
    v(d(10), "支", [dict(account="6211", debit=120_000, summary="發放本月薪資", dept="100"),
                    dict(account="6111", debit=90_000, summary="發放本月薪資", dept="200"),
                    dict(account="2173", credit=9_800, summary="代扣勞健保"),
                    dict(account="1113", credit=200_200, summary="實發薪資")], "薪資")
    exp = [random.randrange(4_000, 9_000, 10), 1_899, random.randrange(500, 3_000, 10)]
    v(d(15), "支", [dict(account="6217", debit=exp[0], summary="支付水電費"),
                    dict(account="6215", debit=exp[1], summary="支付電話網路費"),
                    dict(account="6213", debit=exp[2], summary="購買文具用品"),
                    dict(account="1111", credit=sum(exp), summary="雜支")], "雜支")
    v(d(28), "轉", [dict(account="6222", debit=5_000, summary="提列本月折舊"),
                    dict(account="1452", credit=5_000, summary="提列本月折舊")], "折舊")
v(dt.date(2026, 6, 18), "支", [dict(account="1441", debit=680_000, summary="購置公務貨車"),
                               dict(account="1113", credit=680_000, summary="購置公務貨車")], "購車")
v(dt.date(2026, 9, 1), "收", [dict(account="1113", debit=500_000, summary="向銀行借款"),
                              dict(account="2311", credit=500_000, summary="向銀行借款")], "借款")
ids = [r["id"] for r in db.rows("SELECT id FROM vouchers WHERE status=0 AND v_date < '2026-11-01'")]
print(b.approve_and_post(ids)[1][:3])
db.exec("UPDATE company SET separate_approver=1 WHERE id=1")
print("vouchers:", db.value("SELECT COUNT(*) FROM vouchers"), "posted:", db.value("SELECT COUNT(*) FROM vouchers "
                                                                                    "WHERE status=2"))
