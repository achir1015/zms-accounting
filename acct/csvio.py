"""Excel（CSV）匯入：基本資料名冊、傳票明細（期初餘額）。

Excel「另存新檔」的 CSV 在中文 Windows 預設是 Big5（cp950），「CSV UTF-8」則是 UTF-8，兩種都接受。
"""
import csv
import io
import re

from .books import MASTERS, BizError

VOUCHER_COLS = ["科目代號", "摘要", "借方", "貸方", "部門", "往來對象"]


def read_rows(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp950", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise BizError("無法辨識檔案編碼，請在 Excel 另存為「CSV UTF-8」")
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise BizError("檔案沒有資料（第一列是欄位名稱，第二列起是資料）")
    head = [h.strip() for h in rows[0]]
    return [dict(zip(head, [c.strip() for c in r])) for r in rows[1:]]


def write_rows(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# ------------------------------------------------------------------ 基本資料
EXAMPLES = {
    "departments": ["100", "管理部", "林經理", "是"],
    "employees": ["E001", "陳小美", "100", "會計", "02-2345-6789", "115/01/01", "是"],
    "customers": ["C001", "大成貿易股份有限公司", "大成", "12345675", "王先生", "02-2222-3333", "臺北市中山區…", "月結30天", "是"],
    "vendors": ["V001", "永豐材料行", "永豐", "87654321", "李小姐", "02-3333-4444", "新北市板橋區…", "月結60天", "是"],
    "projects": ["P001", "年度展覽", "115/03/01", "115/03/31", "200000", "是"],
    "currencies": ["USD", "美元", "32.5", "115/01/01"],
    "phrases": ["支付本月房租"],
}


def master_template(name, path):
    m = MASTERS[name]
    write_rows(path, [f[1] for f in m["fields"]], [EXAMPLES.get(name, [])])


def _truthy(v):
    return str(v).strip() not in ("", "0", "否", "N", "n", "False", "false", "停用")


def import_masters(books, name, path):
    """回傳 (成功筆數, [錯誤訊息])。代號已存在就更新，不存在就新增。"""
    books.need("BAS")
    m = MASTERS[name]
    rows = read_rows(path)
    ok, errs = 0, []
    for i, r in enumerate(rows, 2):
        data = {}
        for key, title, typ, _ in m["fields"]:
            v = r.get(title, r.get(key, ""))
            if typ == "b":
                v = _truthy(v) if v != "" else True
            elif typ == "dept":
                v = (v or "").split(" ")[0]
            data[key] = v
        try:
            if name == "phrases":
                books.save_master(name, data, True)
            else:
                key = m["key"]
                exists = any(str(x[key]) == str(data[key]).strip() for x in books.master_rows(name))
                books.save_master(name, data, not exists)
            ok += 1
        except (BizError, ValueError) as e:
            errs.append("第 %d 列：%s" % (i, e))
    books.log("import", name, "成功 %d 筆、失敗 %d 筆" % (ok, len(errs)))
    return ok, errs


# ------------------------------------------------------------------ 傳票明細（期初餘額）
def voucher_template(path):
    write_rows(path, VOUCHER_COLS, [["1113", "期初餘額", "1850000", "", "", ""],
                                    ["1141", "期初餘額", "280000", "", "", "C001"],
                                    ["3111", "期初股本", "", "2500000", "", ""]])


def _lead(v):
    """「1113 銀行存款」→ 1113；「C001 大成」→ C001"""
    v = (v or "").strip()
    m = re.match(r"^([0-9A-Za-z_-]+)", v)
    return m.group(1) if m else v


def read_voucher_lines(path):
    rows = read_rows(path)
    out = []
    for r in rows:
        acct = _lead(r.get("科目代號") or r.get("科目") or r.get("account"))
        if not acct:
            continue
        out.append(dict(account=acct, summary=r.get("摘要", ""), debit=(r.get("借方") or "").replace(",", ""),
                        credit=(r.get("貸方") or "").replace(",", ""), dept=_lead(r.get("部門")),
                        partner=_lead(r.get("往來對象"))))
    if not out:
        raise BizError("找不到明細資料，請確認第一列欄位為：%s" % "、".join(VOUCHER_COLS))
    return out
