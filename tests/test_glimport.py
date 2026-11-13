"""拋轉匯入（zms-gl）：人事薪資差勤批次。"""
import pytest

from acct.books import BizError
from acct.glimport import source_label


def L(account, summary, debit=0, credit=0, dept=""):
    return dict(account=account, summary=summary, debit=str(debit), credit=str(credit),
                partner_kind="", partner="", dept=dept)


def hr_batch(uid="hr-test-0001"):
    # 和 zms-general-hr 的 hr/gl.py 產生的格式相同
    return dict(
        format="zms-gl", version=1, batch_uid=uid, batch_no="GL1151100001",
        source="資料助秘之一般公司人事薪資差勤", source_version="1.0.0",
        company=dict(name="測試公司", tax_id=""), date_from="2026-11-01", date_to="2026-11-30",
        accounts=[dict(code="6211", name="薪資支出"), dict(code="2173", name="代扣勞健保"),
                  dict(code="2175", name="代扣自提勞退"), dict(code="2141", name="應付薪資")],
        partners=[], departments=[],
        vouchers=[dict(ref="PAY1", date="2026-11-30", type="轉", memo="115年11月 薪資（2 人）", lines=[
            L("6211", "115年11月薪資 本薪", debit=80000),
            L("2173", "115年11月薪資 勞健保自付", credit=3600),
            L("2175", "115年11月薪資 自提勞退", credit=2400),
            L("2141", "115年11月薪資 實發", credit=74000)])])


def test_source_label():
    assert source_label("資料助秘之一般公司人事薪資差勤") == "人事薪資"
    assert source_label("資料助秘之一般公司進銷存") == "進銷存"
    assert source_label("") == "進銷存"


def test_hr_batch_import(books):
    assert not books.db.value("SELECT 1 FROM accounts WHERE code='2175'")
    pv = books.preview_gl_batch(hr_batch())
    assert pv["count"] == 1 and pv["created"]["accounts"] == ["2175 代扣自提勞退"]
    assert pv["vouchers"][0]["memo"].startswith("[人事薪資] ")
    # 試匯入不寫入
    assert not books.db.value("SELECT 1 FROM accounts WHERE code='2175'")

    res = books.import_gl_batch(hr_batch())
    assert res["count"] == 1 and res["created"]["accounts"] == ["2175 代扣自提勞退"]
    acc = books.db.row("SELECT * FROM accounts WHERE code='2175'")
    assert acc["name"] == "代扣自提勞退" and acc["nature"] == "C" and acc["parent"] == "217"
    assert acc["memo"] == "人事薪資拋轉自動建立"

    v = books.db.row("SELECT * FROM vouchers WHERE v_no=%s", (res["voucher_nos"][0],))
    assert v["memo"] == "[人事薪資] 115年11月 薪資（2 人）" and v["status"] == 0
    s = books.db.row("SELECT SUM(debit) d, SUM(credit) c FROM voucher_lines WHERE voucher_id=%s", (v["id"],))
    assert s["d"] == s["c"] == v["total"] == 80000
    lines = {r["account"]: r for r in books.db.rows("SELECT * FROM voucher_lines WHERE voucher_id=%s", (v["id"],))}
    assert set(lines) == {"6211", "2173", "2175", "2141"} and lines["2175"]["credit"] == 2400

    imp = books.gl_import_status("hr-test-0001")
    assert imp["source"] == "資料助秘之一般公司人事薪資差勤" and imp["voucher_count"] == 1

    with pytest.raises(BizError, match="已在"):
        books.import_gl_batch(hr_batch())
    assert books.cancel_gl_import("hr-test-0001")["deleted"] == 1


def test_inventory_prefix_and_bad_format(books):
    b = hr_batch("inv-test-0001")
    b["source"] = "資料助秘之一般公司進銷存"
    b["vouchers"][0]["lines"][2]["account"] = "2173"     # 不用 2175
    pv = books.preview_gl_batch(b)
    assert pv["vouchers"][0]["memo"].startswith("[進銷存] ") and not pv["created"]["accounts"]
    with pytest.raises(BizError, match="不是可匯入的拋轉檔（進銷存／人事薪資）"):
        books.preview_gl_batch(dict(format="other"))
