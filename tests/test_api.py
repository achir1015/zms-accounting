"""手機連線：真的啟動 API 服務，用 RemoteBooks／RemoteReports 走 HTTP 測試。"""
import datetime as dt
from decimal import Decimal

import pytest

from acct.api import ApiServer
from acct.books import BizError
from acct.remote import Client, RemoteBooks, RemoteReports

PORT = 8799


@pytest.fixture()
def api(books):
    books.save_user("clerk", "出納", "出納", False, True, {"VOU": 2, "LED": 1}, pw="pass123", is_new=True)
    srv = ApiServer(books.db, port=PORT, host="127.0.0.1")
    srv.start()
    yield srv
    srv.stop()


def connect(uid, pw):
    c = Client("127.0.0.1:%d" % PORT)
    rb = RemoteBooks(c)
    rb.login(uid, pw)
    return rb, RemoteReports(c)


def test_ping_and_login(api):
    c = Client("http://127.0.0.1:%d" % PORT)
    assert c.ping()["app"] == "資料助秘之一般公司會計"
    rb = RemoteBooks(c)
    with pytest.raises(BizError, match="帳號或密碼錯誤"):
        rb.login("admin", "wrong")
    rb.login("admin", "admin123")
    assert rb.user["uid"] == "admin" and "pw_hash" not in rb.user and rb.can("SYS")


def test_full_roundtrip(api):
    rb, rr = connect("admin", "admin123")
    assert rb.account("1113")["name"] == "銀行存款"
    vid = rb.save_voucher(None, "115/11/12", "支", "測試", [dict(account="6213", debit="1,250.50", summary="文具"),
                                                          dict(account="1111", credit="1250.5")])
    v = rb.voucher(vid)
    assert v["total"] == Decimal("1250.50") and isinstance(v["v_date"], dt.date)
    ok, errs = rb.approve_and_post([vid])
    assert errs == [] or "不能審核自己" in errs[0]
    tb = rr.trial_balance(dt.date(2026, 1, 1), dt.date(2026, 12, 31), 4, True)
    assert tb["balanced"] and isinstance(tb["total"]["debit"], Decimal)
    tpl = next(t for t in rb.templates() if t["name"] == "股東現金增資")
    assert sum(x["debit"] for x in rb.apply_template(tpl, 1000)) == Decimal(1000)


def test_permissions_enforced_on_server(api, books):
    rb, rr = connect("clerk", "pass123")
    assert not rb.can("SYS")
    with pytest.raises(BizError, match="系統管理"):
        rb.save_company(name="X")                  # 手機端本地沒擋，電腦端擋下
    with pytest.raises(BizError, match="不允許"):
        rb._c.call("books", "login", ["admin", "admin123"], {})   # 遠端不能呼叫 login 換身分
    with pytest.raises(BizError, match="不允許"):
        rb._c.call("books", "db", [], {})
    # 電腦端停用帳號 → 手機下一次呼叫就失效
    books.save_user("clerk", "出納", "出納", False, False, {"VOU": 2}, is_new=False)
    with pytest.raises(BizError, match="停用"):
        rb.accounts()


def test_client_ip_trust():
    from acct.api import client_ip
    h = {"Cf-Connecting-Ip": "203.0.113.9", "X-Forwarded-For": "198.51.100.1"}
    assert client_ip("127.0.0.1", h) == "203.0.113.9"          # 經本機 Cloudflare 通道：採信
    assert client_ip("192.168.6.50", h) == "192.168.6.50"      # 區網直連：不採信標頭（防偽造）
    assert client_ip("127.0.0.1", {}) == "127.0.0.1"


def test_tunnel_url_parse():
    from acct.tunnel import parse_quick_url
    line = "2026-11-12T14:00:00Z INF |  https://brave-cat-happy-river.trycloudflare.com                 |"
    assert parse_quick_url(line) == "https://brave-cat-happy-river.trycloudflare.com"
    assert parse_quick_url("INF Requesting new quick Tunnel on trycloudflare.com...") == ""


def test_switch_to_alternate_url(api):
    c = Client("127.0.0.1:1", alternates=["127.0.0.1:%d" % PORT])   # 第一個連不上（例如離開公司）
    rb = RemoteBooks(c)
    switched = []
    c.on_switch = switched.append
    rb.login("admin", "admin123")
    assert c.url.endswith(":%d" % PORT) and switched
    assert rb.account("1111")["name"] == "庫存現金"


def test_login_throttle(api):
    c = Client("127.0.0.1:%d" % PORT)
    rb = RemoteBooks(c)
    for _ in range(8):
        with pytest.raises(BizError):
            rb.login("admin", "bad")
    with pytest.raises(BizError, match="次數太多"):
        rb.login("admin", "admin123")
