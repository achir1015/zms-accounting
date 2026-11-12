import datetime as dt
from decimal import Decimal

import pytest

from acct.books import BizError, Books
from acct.reports import Reports

D = dt.date


def v(books, date, vtype, lines, memo=""):
    return books.save_voucher(None, date, vtype, memo, lines)


def post_all(books):
    ids = [r["id"] for r in books.find_vouchers(status=0)]
    books.db.exec("UPDATE company SET separate_approver=0 WHERE id=1")
    ok, errs = books.approve_and_post(ids)
    assert not errs, errs
    return ok


def sample(books):
    books.save_master("customers", dict(code="C001", name="大成貿易", active=1), True)
    books.save_master("vendors", dict(code="V001", name="永豐材料", active=1), True)
    v(books, D(2026, 1, 1), "開帳", [dict(account="1113", debit=1_000_000), dict(account="3111", credit=1_000_000)])
    v(books, D(2026, 1, 5), "轉", [dict(account="1141", debit=105_000, partner="C001"),
                                   dict(account="4111", credit=100_000), dict(account="2161", credit=5_000)])
    v(books, D(2026, 1, 6), "轉", [dict(account="5112", debit=60_000), dict(account="1161", debit=3_000),
                                   dict(account="2131", credit=63_000, partner="V001")])
    v(books, D(2026, 1, 10), "支", [dict(account="6212", debit=20_000), dict(account="1113", credit=20_000)])
    v(books, D(2026, 1, 20), "收", [dict(account="1113", debit=105_000),
                                    dict(account="1141", credit=105_000, partner="C001")])
    v(books, D(2026, 2, 1), "支", [dict(account="1441", debit=300_000), dict(account="1113", credit=300_000)])
    post_all(books)


def test_seed_and_login(books):
    assert books.account("1113")["name"] == "銀行存款"
    assert books.account("1422")["nature"] == "C"
    assert len(books.templates()) >= 10
    with pytest.raises(BizError):
        books.login("admin", "wrong")


def test_unbalanced_and_rules(books):
    with pytest.raises(BizError, match="借貸不平衡"):
        v(books, D(2026, 3, 1), "轉", [dict(account="6212", debit=100), dict(account="1113", credit=90)])
    with pytest.raises(BizError, match="統制科目"):
        v(books, D(2026, 3, 1), "轉", [dict(account="111", debit=100), dict(account="1113", credit=100)])
    with pytest.raises(BizError, match="往來客戶"):
        v(books, D(2026, 3, 1), "轉", [dict(account="1141", debit=100), dict(account="4111", credit=100)])
    with pytest.raises(BizError, match="收入傳票"):
        v(books, D(2026, 3, 1), "收", [dict(account="6212", debit=100), dict(account="4111", credit=100)])


def test_numbering_and_workflow(books):
    a = v(books, D(2026, 11, 12), "支", [dict(account="6213", debit=500), dict(account="1111", credit=500)])
    b = v(books, D(2026, 11, 12), "支", [dict(account="6213", debit=300), dict(account="1111", credit=300)])
    assert books.voucher(a)["v_no"] == "1151112001"
    assert books.voucher(b)["v_no"] == "1151112002"
    # 製單與審核分離：自己不能審自己的（管理員除外）→ 建一般使用者測
    books.save_user("acc1", "會計小王", "會計人員", False, True, {"VOU": 2, "LED": 1}, pw="pass123", is_new=True)
    books.save_user("mgr", "主管", "會計主管", False, True, {"VOU": 2, "APR": 2, "LED": 2, "FIN": 2, "CLS": 2},
                    pw="pass123", is_new=True)
    clerk = Books(books.db)
    clerk.login("acc1", "pass123")
    c = clerk.save_voucher(None, "115/11/12", "轉", "", [dict(account="6219", debit=800),
                                                        dict(account="2142", credit=800)])
    with pytest.raises(BizError, match="審核過帳"):
        clerk.approve([c])
    mgr = Books(books.db)
    mgr.login("mgr", "pass123")
    ok, errs = mgr.approve([c])
    assert ok and not errs
    with pytest.raises(BizError, match="不能修改"):
        clerk.save_voucher(c, "115/11/12", "轉", "", [dict(account="6219", debit=900), dict(account="2142", credit=900)])
    ok, errs = mgr.post([c])
    assert ok
    assert books.voucher(c)["status"] == 2
    ok, errs = mgr.void([c])
    assert errs and "已過帳" in errs[0]


def test_reports_balance(books):
    sample(books)
    r = Reports(books)
    tb = r.trial_balance(D(2026, 1, 1), D(2026, 12, 31))
    assert tb["balanced"]
    inc = r.income_statement(D(2026, 1, 1), D(2026, 12, 31))
    assert inc["revenue"] == Decimal(100_000)
    assert inc["gross"] == Decimal(40_000)
    assert inc["net"] == Decimal(20_000)
    bs = r.balance_sheet(D(2026, 12, 31))
    assert bs["balanced"]
    assert bs["assets"] == Decimal(1_000_000 + 105_000 - 105_000 + 3_000 - 20_000 + 105_000 - 300_000 + 300_000)
    cf = r.cash_flow(D(2026, 1, 1), D(2026, 12, 31))
    assert cf["sections"]["OP"]["total"] == Decimal(85_000)
    assert cf["sections"]["INV"]["total"] == Decimal(-300_000)
    assert cf["closing"] - cf["opening"] == cf["net"] + cf["other"]
    led = r.ledger("1113", D(2026, 1, 1), D(2026, 12, 31))
    assert led["closing"] == Decimal(785_000)
    ratios = {x["name"]: x for x in r.ratios(D(2026, 1, 1), D(2026, 12, 31))}
    assert ratios["毛利率"]["value"] == Decimal(40)
    ar = r.partner_balances("V", D(2026, 12, 31))
    assert ar[0]["balance"] == Decimal(63_000)


def test_period_close_and_year_end(books):
    sample(books)
    books.close_period("202601")
    with pytest.raises(BizError, match="已關帳"):
        v(books, D(2026, 1, 15), "支", [dict(account="6213", debit=1), dict(account="1111", credit=1)])
    books.close_period("202601", close=False)
    vid, net = books.year_end_close(2026)
    assert net == Decimal(20_000)
    r = Reports(books)
    bs = r.balance_sheet(D(2026, 12, 31))
    assert bs["balanced"] and bs["unclosed"] == 0
    assert r.income_statement(D(2026, 1, 1), D(2026, 12, 31))["net"] == Decimal(20_000)
    with pytest.raises(BizError, match="已結帳"):
        books.year_end_close(2026)
    books.year_end_reopen(2026)
    assert not books.year_closed(2026)


def test_template_and_revaluation(books):
    tpl = next(t for t in books.templates() if t["name"].startswith("支付個人房東"))
    lines = Books.apply_template(tpl, 25_000)
    assert sum(x["debit"] for x in lines) == sum(x["credit"] for x in lines) == Decimal(25_000)
    books.db.exec("UPDATE currencies SET rate=30 WHERE code='USD'")
    v(books, D(2026, 3, 1), "收", [dict(account="1114", debit=30_000, currency="USD", fx_rate=30, fx_amount=1000),
                                   dict(account="7191", credit=30_000)])
    post_all(books)
    books.db.exec("UPDATE currencies SET rate=32.5 WHERE code='USD'")
    prev = books.revaluation_preview("115/03/31")
    assert prev[0]["diff"] == Decimal(2500)
    vid = books.revaluation_voucher("115/03/31")
    lines = books.voucher(vid)["lines"]
    assert {(x["account"], x["debit"], x["credit"]) for x in lines} == {
        ("1114", Decimal(2500), Decimal(0)), ("7131", Decimal(0), Decimal(2500))}


def test_permissions(books):
    books.save_user("view", "查帳", "查帳人員", False, True, {"LED": 1, "FIN": 1}, pw="pass123", is_new=True)
    u = Books(books.db)
    u.login("view", "pass123")
    with pytest.raises(BizError, match="傳票登錄"):
        u.save_voucher(None, "115/11/12", "轉", "", [dict(account="6213", debit=1), dict(account="2142", credit=1)])
    with pytest.raises(BizError, match="基本資料"):
        u.save_master("departments", dict(code="300", name="研發部", active=1), True)
    assert u.can("FIN") and not u.can("SYS")
    with pytest.raises(BizError, match="不能取消自己"):
        books.save_user("admin", "管理員", "系統管理員", True, False, {}, is_new=False)
    books.save_user("boss", "老闆", "系統管理員", True, True, {}, pw="pass123", is_new=True)
    boss = Books(books.db)
    boss.login("boss", "pass123")
    boss.save_user("admin", "管理員", "系統管理員", False, True, {}, is_new=False)   # 還有 boss，可以
    boss.save_user("it", "資訊", "", False, True, {"SYS": 2}, pw="pass123", is_new=True)
    it = Books(books.db)
    it.login("it", "pass123")
    with pytest.raises(BizError, match="至少要保留"):
        it.save_user("boss", "老闆", "系統管理員", False, True, {}, is_new=False)   # boss 是最後一位管理員
    assert books.db.value("SELECT is_admin FROM users WHERE uid='boss'") == 1
