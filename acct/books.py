"""帳務服務：登入與權限、基本資料、傳票（登錄／審核／過帳）、期間關帳、年度結帳、現值調整。

所有規則都在這裡檢查（畫面只負責顯示），手機版或其他介面日後也能共用。
"""
import datetime as dt
import json
from decimal import ROUND_HALF_UP, Decimal

from . import passwords, rocdate
from .seed import FUNCS, ROLES

STATUS = {0: "未審核", 1: "已審核", 2: "已過帳", 9: "作廢"}
V_TYPES = ["收", "支", "轉", "開帳", "調整", "結帳"]
V_TYPE_NAMES = {"收": "收入傳票", "支": "支出傳票", "轉": "轉帳傳票", "開帳": "開帳傳票", "調整": "調整傳票",
                "結帳": "結帳傳票"}
PARTNER_KINDS = {"C": "客戶", "V": "廠商", "E": "員工"}
CF_SECTIONS = {"OP": "營業活動", "INV": "投資活動", "FIN": "籌資活動"}
CENT = Decimal("0.01")


class BizError(Exception):
    """可以直接顯示給使用者看的錯誤。"""


def money(v) -> Decimal:
    if v in (None, ""):
        return Decimal(0)
    if isinstance(v, str):
        v = v.replace(",", "").strip() or "0"
    try:
        return Decimal(str(v)).quantize(CENT, ROUND_HALF_UP)
    except Exception:
        raise BizError("金額格式不正確：%s" % v)


# 基本資料定義：欄位 (key, 標題, 型別 s文字/n數字/d日期/b是否/sel選單, 寬度)
MASTERS = {
    "departments": dict(title="部門", table="departments", key="code", fields=[
        ("code", "部門代號", "s", 100), ("name", "部門名稱", "s", 200), ("manager", "主管", "s", 140),
        ("active", "使用中", "b", 80)]),
    "employees": dict(title="員工", table="employees", key="code", fields=[
        ("code", "員工編號", "s", 100), ("name", "姓名", "s", 140), ("dept", "部門", "dept", 160),
        ("title", "職稱", "s", 120), ("phone", "電話", "s", 140), ("hire_date", "到職日", "d", 120),
        ("active", "在職", "b", 70)]),
    "customers": dict(title="客戶", table="partners", key="code", kind="C", fields=[
        ("code", "客戶代號", "s", 110), ("name", "客戶名稱", "s", 240), ("short_name", "簡稱", "s", 120),
        ("tax_id", "統一編號", "s", 110), ("contact", "聯絡人", "s", 110), ("phone", "電話", "s", 130),
        ("address", "地址", "s", 280), ("pay_terms", "收款條件", "s", 120), ("active", "使用中", "b", 70)]),
    "vendors": dict(title="廠商", table="partners", key="code", kind="V", fields=[
        ("code", "廠商代號", "s", 110), ("name", "廠商名稱", "s", 240), ("short_name", "簡稱", "s", 120),
        ("tax_id", "統一編號", "s", 110), ("contact", "聯絡人", "s", 110), ("phone", "電話", "s", 130),
        ("address", "地址", "s", 280), ("pay_terms", "付款條件", "s", 120), ("active", "使用中", "b", 70)]),
    "projects": dict(title="專案", table="projects", key="code", fields=[
        ("code", "專案代號", "s", 110), ("name", "專案名稱", "s", 240), ("start_date", "開始日", "d", 120),
        ("end_date", "結束日", "d", 120), ("budget", "預算金額", "n", 130), ("active", "進行中", "b", 80)]),
    "currencies": dict(title="幣別匯率", table="currencies", key="code", fields=[
        ("code", "幣別", "s", 70), ("name", "名稱", "s", 120), ("rate", "匯率（1 外幣＝？元）", "n", 170),
        ("rate_date", "匯率日期", "d", 120)]),
    "phrases": dict(title="摘要片語", table="phrases", key="id", fields=[("text", "摘要內容", "s", 360)]),
}


class Books:
    def __init__(self, db):
        self.db = db
        self.user = None
        self.perms = {}

    # ================================================================ 登入、權限、紀錄
    @property
    def uid(self):
        return self.user["uid"] if self.user else ""

    def has_users(self) -> bool:
        return bool(self.db.value("SELECT COUNT(*) FROM users"))

    def login(self, uid, pw):
        u = self.db.row("SELECT * FROM users WHERE uid=%s", ((uid or "").strip(),))
        if not u or not passwords.verify(pw, u["pw_hash"]):
            self.db.exec("INSERT INTO audit_log (uid, action, detail) VALUES (%s, 'login_fail', '')", (uid or "",))
            raise BizError("帳號或密碼錯誤")
        if not u["active"]:
            raise BizError("此帳號已停用，請洽系統管理員")
        self.user = u
        self.perms = {r["func"]: r["lvl"] for r in self.db.rows("SELECT func, lvl FROM user_perms WHERE uid=%s",
                                                                 (u["uid"],))}
        self.db.exec("UPDATE users SET last_login=NOW() WHERE uid=%s", (u["uid"],))
        self.log("login", u["uid"])
        return u

    def logout(self):
        if self.user:
            self.log("logout", self.uid)
        self.user, self.perms = None, {}

    def level(self, func) -> int:
        if not self.user:
            return 0
        if self.user["is_admin"]:
            return 2
        return int(self.perms.get(func, 0))

    def can(self, func, lvl=1) -> bool:
        return self.level(func) >= lvl

    def need(self, func, lvl=2):
        if not self.can(func, lvl):
            from .seed import FUNC_NAMES
            raise BizError("您沒有「%s」的%s權限" % (FUNC_NAMES.get(func, func), "維護" if lvl >= 2 else "查詢"))

    def log(self, action, target="", detail=""):
        try:
            self.db.exec("INSERT INTO audit_log (uid, action, target, detail) VALUES (%s, %s, %s, %s)",
                         (self.uid, action, str(target)[:60], str(detail)[:500]))
        except Exception:
            pass

    # ================================================================ 使用者
    def users(self):
        rows = self.db.rows("SELECT uid, name, role, is_admin, active, last_login FROM users ORDER BY uid")
        perms = self.db.rows("SELECT uid, func, lvl FROM user_perms")
        for u in rows:
            u["perms"] = {p["func"]: p["lvl"] for p in perms if p["uid"] == u["uid"]}
        return rows

    def create_first_admin(self, uid, name, pw):
        if self.has_users():
            raise BizError("系統已有使用者")
        self._check_new_password(pw)
        self._insert_user(uid, name, pw, "系統管理員", True)

    def save_user(self, uid, name, role, is_admin, active, perms, pw=None, is_new=False):
        self.need("SYS")
        uid = (uid or "").strip()
        if not uid or not (name or "").strip():
            raise BizError("帳號與姓名必填")
        if is_new:
            if self.db.value("SELECT 1 FROM users WHERE uid=%s", (uid,)):
                raise BizError("帳號 %s 已存在" % uid)
            self._check_new_password(pw)
            self._insert_user(uid, name, pw, role, is_admin, perms)
        else:
            if uid == self.uid and (not is_admin or not active) and self.user["is_admin"]:
                raise BizError("不能取消自己的管理員身分或停用自己")
            if (not is_admin or not active) and not self.db.value(
                    "SELECT COUNT(*) FROM users WHERE is_admin=1 AND active=1 AND uid<>%s", (uid,)):
                raise BizError("至少要保留一位啟用中的系統管理員")
            self.db.exec("UPDATE users SET name=%s, role=%s, is_admin=%s, active=%s WHERE uid=%s",
                         (name.strip(), role, int(bool(is_admin)), int(bool(active)), uid))
            self._write_perms(uid, perms)
            if pw:
                self._check_new_password(pw)
                self.db.exec("UPDATE users SET pw_hash=%s WHERE uid=%s", (passwords.make(pw), uid))
        self.log("user_save", uid, json.dumps({"role": role, "admin": bool(is_admin), "perms": perms},
                                               ensure_ascii=False))

    def _insert_user(self, uid, name, pw, role, is_admin, perms=None):
        uid = (uid or "").strip()
        if not uid:
            raise BizError("請輸入帳號")
        self.db.exec("INSERT INTO users (uid, name, pw_hash, role, is_admin) VALUES (%s, %s, %s, %s, %s)",
                     (uid, (name or uid).strip(), passwords.make(pw), role, int(bool(is_admin))))
        self._write_perms(uid, perms if perms is not None else ROLES.get(role, {}))

    def _write_perms(self, uid, perms):
        self.db.exec("DELETE FROM user_perms WHERE uid=%s", (uid,))
        self.db.exec_many("INSERT INTO user_perms (uid, func, lvl) VALUES (%s, %s, %s)",
                          [(uid, f, int(perms.get(f, 0))) for f, _, _ in FUNCS])

    @staticmethod
    def _check_new_password(pw):
        if len(pw or "") < 6:
            raise BizError("密碼至少 6 個字")

    def change_password(self, old, new):
        if not passwords.verify(old, self.db.value("SELECT pw_hash FROM users WHERE uid=%s", (self.uid,))):
            raise BizError("舊密碼不正確")
        self._check_new_password(new)
        self.db.exec("UPDATE users SET pw_hash=%s WHERE uid=%s", (passwords.make(new), self.uid))
        self.log("password", self.uid)

    def delete_user(self, uid):
        self.need("SYS")
        if uid == self.uid:
            raise BizError("不能刪除自己")
        if self.db.value("SELECT 1 FROM vouchers WHERE created_by=%s OR approved_by=%s OR posted_by=%s LIMIT 1",
                         (uid, uid, uid)):
            raise BizError("此帳號已有傳票紀錄，請改為「停用」以保留稽核軌跡")
        self.db.exec("DELETE FROM user_perms WHERE uid=%s", (uid,))
        self.db.exec("DELETE FROM users WHERE uid=%s", (uid,))
        self.log("user_delete", uid)

    def audit(self, limit=500, uid=""):
        sql = "SELECT * FROM audit_log" + (" WHERE uid=%s" if uid else "") + " ORDER BY id DESC LIMIT %s"
        return self.db.rows(sql, ((uid, limit) if uid else (limit,)))

    # ================================================================ 公司
    def company(self):
        return self.db.row("SELECT * FROM company WHERE id=1") or {}

    def save_company(self, **kw):
        self.need("SYS")
        keys = ["name", "tax_id", "owner", "phone", "address", "fiscal_start_month", "auto_post",
                "separate_approver"]
        vals = [kw.get(k) for k in keys]
        if not (kw.get("name") or "").strip():
            raise BizError("公司名稱必填")
        self.db.exec("UPDATE company SET %s, updated_at=NOW() WHERE id=1" % ", ".join("%s=%%s" % k for k in keys),
                     vals)
        self.log("company", "", kw.get("name"))

    # ================================================================ 會計科目
    def accounts(self, detail_only=False, active_only=False, search=""):
        sql = "SELECT * FROM accounts WHERE 1"
        args = []
        if detail_only:
            sql += " AND level=4"
        if active_only:
            sql += " AND active=1"
        if search:
            sql += " AND (code LIKE %s OR name LIKE %s)"
            args += [search + "%", "%" + search + "%"]
        return self.db.rows(sql + " ORDER BY code", args)

    def account(self, code):
        return self.db.row("SELECT * FROM accounts WHERE code=%s", (code,))

    def account_names(self):
        return {r["code"]: r["name"] for r in self.db.rows("SELECT code, name FROM accounts")}

    def save_account(self, a: dict, is_new: bool):
        self.need("BAS")
        code = (a.get("code") or "").strip()
        if not code.isdigit() or not 1 <= len(code) <= 4:
            raise BizError("科目代號要是 1～4 位數字（4 位為可記帳的明細科目）")
        if not (a.get("name") or "").strip():
            raise BizError("請輸入科目名稱")
        parent = code[:-1]
        if parent and not self.account(parent):
            raise BizError("上層科目 %s 不存在，請先建立" % parent)
        exists = self.account(code)
        if is_new and exists:
            raise BizError("科目 %s 已存在" % code)
        if a.get("currency") and not self.db.value("SELECT 1 FROM currencies WHERE code=%s", (a["currency"],)):
            raise BizError("幣別 %s 不存在" % a["currency"])
        row = dict(code=code, name=a["name"].strip(), parent=parent, level=len(code),
                   nature=a.get("nature") or "D", is_cash=int(bool(a.get("is_cash"))),
                   cf_section=a.get("cf_section") or "OP", partner_kind=a.get("partner_kind") or "",
                   need_dept=int(bool(a.get("need_dept"))), currency=a.get("currency") or "",
                   active=int(bool(a.get("active", 1))), memo=a.get("memo") or "")
        cols = list(row)
        self.db.exec("INSERT INTO accounts (%s) VALUES (%s) ON DUPLICATE KEY UPDATE %s" % (
            ", ".join(cols), ", ".join(["%s"] * len(cols)),
            ", ".join("%s=VALUES(%s)" % (c, c) for c in cols if c != "code")), [row[c] for c in cols])
        self.log("account_save", code, row["name"])

    def delete_account(self, code):
        self.need("BAS")
        if self.db.value("SELECT 1 FROM voucher_lines WHERE account=%s LIMIT 1", (code,)):
            raise BizError("科目 %s 已有傳票使用，不能刪除；可改為「停用」" % code)
        if self.db.value("SELECT 1 FROM accounts WHERE parent=%s LIMIT 1", (code,)):
            raise BizError("科目 %s 底下還有子科目，請先刪除子科目" % code)
        if self.db.value("SELECT 1 FROM template_lines WHERE account=%s LIMIT 1", (code,)):
            raise BizError("科目 %s 有常用分錄使用中，請先修改常用分錄" % code)
        self.db.exec("DELETE FROM accounts WHERE code=%s", (code,))
        self.log("account_delete", code)

    # ================================================================ 其他基本資料
    def master_rows(self, name, active_only=False):
        m = MASTERS[name]
        sql, args = "SELECT * FROM %s WHERE 1" % m["table"], []
        if m.get("kind"):
            sql += " AND kind=%s"
            args.append(m["kind"])
        if active_only and any(f[0] == "active" for f in m["fields"]):
            sql += " AND active=1"
        return self.db.rows(sql + " ORDER BY %s" % m["key"], args)

    def options(self, name):
        """下拉選單用：[(代號, 代號＋名稱)]"""
        if name == "accounts":
            return [(r["code"], "%s %s" % (r["code"], r["name"])) for r in self.accounts(True, True)]
        if name == "phrases":
            return [(r["text"], r["text"]) for r in self.master_rows("phrases")]
        return [(r["code"], "%s %s" % (r["code"], r.get("short_name") or r["name"]))
                for r in self.master_rows(name, active_only=True)]

    def save_master(self, name, row: dict, is_new: bool):
        self.need("BAS")
        m = MASTERS[name]
        data = {}
        for key, title, typ, _ in m["fields"]:
            v = row.get(key)
            if typ == "b":
                v = int(bool(v))
            elif typ == "n":
                v = money(v) if key != "rate" else Decimal(str(v or 0).replace(",", "") or 0)
            elif typ == "d":
                v = rocdate.read(v) if v else None
            else:
                v = (v or "").strip()
            data[key] = v
        if m["key"] != "id" and not data.get(m["key"]):
            raise BizError("請輸入%s" % m["fields"][0][1])
        first_text = next(f[0] for f in m["fields"] if f[0] not in ("code",))
        if not data.get(first_text) and first_text != "active":
            raise BizError("請輸入%s" % next(f[1] for f in m["fields"] if f[0] == first_text))
        if m.get("kind"):
            data["kind"] = m["kind"]
        if name == "phrases":
            if row.get("id"):
                self.db.exec("UPDATE phrases SET text=%s WHERE id=%s", (data["text"], row["id"]))
            else:
                self.db.exec("INSERT IGNORE INTO phrases (text) VALUES (%s)", (data["text"],))
            return
        where = "kind=%s AND code=%s" if m.get("kind") else "%s=%%s" % m["key"]
        wargs = (m["kind"], data["code"]) if m.get("kind") else (data[m["key"]],)
        exists = self.db.value("SELECT 1 FROM %s WHERE %s" % (m["table"], where), wargs)
        if is_new and exists:
            raise BizError("代號 %s 已存在" % data[m["key"]])
        cols = list(data)
        self.db.exec("INSERT INTO %s (%s) VALUES (%s) ON DUPLICATE KEY UPDATE %s" % (
            m["table"], ", ".join(cols), ", ".join(["%s"] * len(cols)),
            ", ".join("%s=VALUES(%s)" % (c, c) for c in cols)), [data[c] for c in cols])
        self.log("master_save", "%s:%s" % (name, data.get(m["key"])), data.get("name", ""))

    def delete_master(self, name, key):
        self.need("BAS")
        m = MASTERS[name]
        used = {
            "departments": ("SELECT 1 FROM voucher_lines WHERE dept=%s LIMIT 1", "已有傳票使用此部門"),
            "employees": ("SELECT 1 FROM voucher_lines WHERE partner_kind='E' AND partner=%s LIMIT 1", "已有傳票使用"),
            "customers": ("SELECT 1 FROM voucher_lines WHERE partner_kind='C' AND partner=%s LIMIT 1", "已有傳票使用"),
            "vendors": ("SELECT 1 FROM voucher_lines WHERE partner_kind='V' AND partner=%s LIMIT 1", "已有傳票使用"),
            "projects": ("SELECT 1 FROM voucher_lines WHERE project=%s LIMIT 1", "已有傳票使用"),
            "currencies": ("SELECT 1 FROM voucher_lines WHERE currency=%s LIMIT 1", "已有傳票使用"),
        }.get(name)
        if used and self.db.value(used[0], (key,)):
            raise BizError(used[1] + "，不能刪除；可改為停用")
        if name == "currencies" and key == "TWD":
            raise BizError("本國幣不能刪除")
        if m.get("kind"):
            self.db.exec("DELETE FROM partners WHERE kind=%s AND code=%s", (m["kind"], key))
        else:
            self.db.exec("DELETE FROM %s WHERE %s=%%s" % (m["table"], m["key"]), (key,))
        self.log("master_delete", "%s:%s" % (name, key))

    def currency_rate(self, code) -> Decimal:
        r = self.db.value("SELECT rate FROM currencies WHERE code=%s", (code,))
        return Decimal(str(r or 0))

    # ================================================================ 常用分錄
    def templates(self):
        rows = self.db.rows("SELECT * FROM templates ORDER BY name")
        lines = self.db.rows("SELECT * FROM template_lines ORDER BY tpl_id, line_no")
        for t in rows:
            t["lines"] = [ln for ln in lines if ln["tpl_id"] == t["id"]]
        return rows

    def save_template(self, tid, name, v_type, memo, lines):
        self.need("BAS")
        name = (name or "").strip()
        if not name:
            raise BizError("請輸入分錄名稱")
        lines = [ln for ln in lines if (ln.get("account") or "").strip()]
        if len(lines) < 2:
            raise BizError("常用分錄至少要有一借一貸兩行")
        for ln in lines:
            a = self.account(ln["account"])
            if not a or a["level"] != 4:
                raise BizError("科目 %s 不是可記帳的明細科目" % ln["account"])
        with self.db.transaction():
            if tid:
                self.db.exec("UPDATE templates SET name=%s, v_type=%s, memo=%s WHERE id=%s", (name, v_type, memo, tid))
                self.db.exec("DELETE FROM template_lines WHERE tpl_id=%s", (tid,))
            else:
                if self.db.value("SELECT 1 FROM templates WHERE name=%s", (name,)):
                    raise BizError("已有同名的常用分錄")
                tid = self.db.exec("INSERT INTO templates (name, v_type, memo) VALUES (%s, %s, %s)",
                                   (name, v_type, memo))
            self.db.exec_many("INSERT INTO template_lines (tpl_id, line_no, account, side, summary, ratio) "
                              "VALUES (%s, %s, %s, %s, %s, %s)",
                              [(tid, i + 1, ln["account"], ln.get("side") or "D", ln.get("summary") or "",
                                Decimal(str(ln.get("ratio") or 0))) for i, ln in enumerate(lines)])
        self.log("template_save", tid, name)
        return tid

    def delete_template(self, tid):
        self.need("BAS")
        self.db.exec("DELETE FROM template_lines WHERE tpl_id=%s", (tid,))
        self.db.exec("DELETE FROM templates WHERE id=%s", (tid,))
        self.log("template_delete", tid)

    @staticmethod
    def apply_template(tpl, amount):
        """把常用分錄展開成傳票明細（金額＝輸入金額 × 比率）。"""
        amt = money(amount)
        out = []
        for ln in tpl["lines"]:
            v = (amt * Decimal(str(ln["ratio"]))).quantize(CENT, ROUND_HALF_UP) if amt and ln["ratio"] else Decimal(0)
            out.append(dict(account=ln["account"], summary=ln["summary"],
                            debit=v if ln["side"] == "D" else Decimal(0), credit=v if ln["side"] == "C" else Decimal(0)))
        return out

    # ================================================================ 會計期間
    def period_closed(self, d: dt.date) -> bool:
        return bool(self.db.value("SELECT closed FROM periods WHERE ym=%s", (rocdate.ym(d),)))

    def periods(self, year):
        out = []
        for m in range(1, 13):
            ym = "%04d%02d" % (year, m)
            r = self.db.row("SELECT * FROM periods WHERE ym=%s", (ym,)) or {"ym": ym, "closed": 0, "closed_by": "",
                                                                             "closed_at": None}
            s, e = rocdate.month_first(dt.date(year, m, 1)), rocdate.month_last(dt.date(year, m, 1))
            cnt = self.db.row("SELECT COUNT(*) n, SUM(status IN (0,1)) pending FROM vouchers "
                              "WHERE v_date BETWEEN %s AND %s AND status<>9", (s, e))
            r.update(vouchers=int(cnt["n"] or 0), pending=int(cnt["pending"] or 0))
            out.append(r)
        return out

    def close_period(self, ym, close=True):
        self.need("CLS")
        if close:
            s = dt.date(int(ym[:4]), int(ym[4:]), 1)
            pending = self.db.value("SELECT COUNT(*) FROM vouchers WHERE v_date BETWEEN %s AND %s AND status IN (0,1)",
                                    (s, rocdate.month_last(s)))
            if pending:
                raise BizError("%s 還有 %d 張傳票未過帳，請先審核過帳或作廢後再關帳" % (rocdate.ym_show(ym), pending))
        self.db.exec("INSERT INTO periods (ym, closed, closed_by, closed_at) VALUES (%s, %s, %s, NOW()) "
                     "ON DUPLICATE KEY UPDATE closed=VALUES(closed), closed_by=VALUES(closed_by), closed_at=NOW()",
                     (ym, int(close), self.uid))
        self.log("period_close" if close else "period_reopen", ym)

    def _check_open(self, d: dt.date):
        if self.period_closed(d):
            raise BizError("%s 已關帳，不能新增或異動傳票（如需更正請由主管重新開帳）" % rocdate.ym_show(rocdate.ym(d)))

    # ================================================================ 傳票
    def next_voucher_no(self, d: dt.date) -> str:
        prefix = rocdate.compact(d)
        last = self.db.value("SELECT MAX(v_no) FROM vouchers WHERE v_no LIKE %s", (prefix + "%",))
        seq = int(last[len(prefix):]) + 1 if last else 1
        return "%s%03d" % (prefix, seq)

    def voucher(self, vid):
        v = self.db.row("SELECT * FROM vouchers WHERE id=%s", (vid,))
        if v:
            v["lines"] = self.db.rows("SELECT * FROM voucher_lines WHERE voucher_id=%s ORDER BY line_no", (vid,))
        return v

    def voucher_by_no(self, no):
        vid = self.db.value("SELECT id FROM vouchers WHERE v_no=%s", (no,))
        return self.voucher(vid) if vid else None

    def find_vouchers(self, start=None, end=None, status=None, v_type="", keyword="", account="", limit=1000):
        sql = ("SELECT v.*, (SELECT COUNT(*) FROM voucher_lines l WHERE l.voucher_id=v.id) AS line_count "
               "FROM vouchers v WHERE 1")
        args = []
        if start:
            sql += " AND v.v_date>=%s"
            args.append(start)
        if end:
            sql += " AND v.v_date<=%s"
            args.append(end)
        if status is not None and status != "":
            sql += " AND v.status=%s"
            args.append(int(status))
        if v_type:
            sql += " AND v.v_type=%s"
            args.append(v_type)
        if keyword:
            sql += (" AND (v.v_no LIKE %s OR v.memo LIKE %s OR EXISTS (SELECT 1 FROM voucher_lines l "
                    "WHERE l.voucher_id=v.id AND l.summary LIKE %s))")
            args += [keyword + "%", "%" + keyword + "%", "%" + keyword + "%"]
        if account:
            sql += " AND EXISTS (SELECT 1 FROM voucher_lines l WHERE l.voucher_id=v.id AND l.account LIKE %s)"
            args.append(account + "%")
        sql += " ORDER BY v.v_date DESC, v.v_no DESC LIMIT %d" % int(limit)
        return self.db.rows(sql, args)

    def _clean_lines(self, lines):
        accts = {r["code"]: r for r in self.db.rows("SELECT * FROM accounts")}
        out = []
        for i, ln in enumerate(lines, 1):
            code = (ln.get("account") or "").strip()
            d, c = money(ln.get("debit")), money(ln.get("credit"))
            if not code and not d and not c:
                continue                        # 空白列略過
            a = accts.get(code)
            if not a:
                raise BizError("第 %d 行：科目 %s 不存在" % (i, code or "（空白）"))
            if a["level"] != 4:
                raise BizError("第 %d 行：%s %s 是統制科目，請選四碼明細科目" % (i, code, a["name"]))
            if not a["active"]:
                raise BizError("第 %d 行：科目 %s %s 已停用" % (i, code, a["name"]))
            if d < 0 or c < 0:
                raise BizError("第 %d 行：金額不能是負數（要沖銷請記在另一方）" % i)
            if d and c:
                raise BizError("第 %d 行：借方與貸方只能擇一填寫" % i)
            if not d and not c:
                raise BizError("第 %d 行：請輸入借方或貸方金額" % i)
            pk = a["partner_kind"]
            partner = (ln.get("partner") or "").strip()
            if pk and not partner:
                raise BizError("第 %d 行：%s 需要選擇往來%s" % (i, a["name"], PARTNER_KINDS[pk]))
            if partner and pk:
                table, where = ("employees", "code=%s") if pk == "E" else ("partners", "kind=%s AND code=%s")
                args = (partner,) if pk == "E" else (pk, partner)
                if not self.db.value("SELECT 1 FROM %s WHERE %s" % (table, where), args):
                    raise BizError("第 %d 行：找不到%s %s" % (i, PARTNER_KINDS[pk], partner))
            dept = (ln.get("dept") or "").strip()
            if a["need_dept"] and not dept:
                raise BizError("第 %d 行：%s 需要選擇部門" % (i, a["name"]))
            cur = (ln.get("currency") or "").strip()
            fx_amt = money(ln.get("fx_amount")) if cur else Decimal(0)
            fx_rate = Decimal(str(ln.get("fx_rate") or 0)) if cur else Decimal(0)
            if cur and fx_amt and (c and fx_amt > 0):
                fx_amt = -fx_amt                    # 外幣金額：借正貸負
            out.append(dict(account=code, summary=(ln.get("summary") or "").strip()[:100], debit=d, credit=c,
                            dept=dept, project=(ln.get("project") or "").strip(),
                            partner_kind=pk if partner else "", partner=partner if pk else "",
                            currency=cur, fx_rate=fx_rate, fx_amount=fx_amt))
        if len(out) < 2:
            raise BizError("傳票至少要有借、貸各一行")
        td, tc = sum(x["debit"] for x in out), sum(x["credit"] for x in out)
        if td != tc:
            raise BizError("借貸不平衡：借方 %s、貸方 %s，差額 %s" % (f"{td:,.2f}", f"{tc:,.2f}", f"{td - tc:,.2f}"))
        return out, td

    def save_voucher(self, vid, v_date, v_type, memo, lines, attachments=0):
        """新增（vid=None）或修改未審核傳票；回傳傳票 id。"""
        self.need("VOU")
        d = rocdate.read(v_date)
        if v_type not in V_TYPES:
            raise BizError("傳票類別不正確")
        if v_type == "結帳":
            raise BizError("結帳傳票由「年度結帳」自動產生")
        self._check_open(d)
        clean, total = self._clean_lines(lines)
        cash_accts = {r["code"] for r in self.db.rows("SELECT code FROM accounts WHERE is_cash=1")}
        if v_type == "收" and not any(x["account"] in cash_accts and x["debit"] for x in clean):
            raise BizError("收入傳票的借方應有現金或銀行存款科目（否則請用轉帳傳票）")
        if v_type == "支" and not any(x["account"] in cash_accts and x["credit"] for x in clean):
            raise BizError("支出傳票的貸方應有現金或銀行存款科目（否則請用轉帳傳票）")
        comp = self.company()
        with self.db.transaction():
            if vid:
                old = self.db.row("SELECT * FROM vouchers WHERE id=%s FOR UPDATE", (vid,))
                if not old:
                    raise BizError("傳票不存在")
                if old["status"] != 0:
                    raise BizError("傳票 %s 已%s，不能修改（請先退回）" % (old["v_no"], STATUS[old["status"]]))
                if old["created_by"] != self.uid and not self.can("APR"):
                    raise BizError("只能修改自己製作的傳票")
                self._check_open(old["v_date"])
                v_no = old["v_no"]
                if rocdate.compact(old["v_date"]) != rocdate.compact(d):
                    v_no = self.next_voucher_no(d)
                self.db.exec("UPDATE vouchers SET v_no=%s, v_date=%s, v_type=%s, memo=%s, total=%s, attachments=%s, "
                             "updated_by=%s, updated_at=NOW() WHERE id=%s",
                             (v_no, d, v_type, memo or "", total, int(attachments or 0), self.uid, vid))
                self.db.exec("DELETE FROM voucher_lines WHERE voucher_id=%s", (vid,))
                action = "voucher_edit"
            else:
                v_no = self.next_voucher_no(d)
                vid = self.db.exec("INSERT INTO vouchers (v_no, v_date, v_type, memo, total, attachments, created_by) "
                                   "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                                   (v_no, d, v_type, memo or "", total, int(attachments or 0), self.uid))
                action = "voucher_new"
            self.db.exec_many(
                "INSERT INTO voucher_lines (voucher_id, line_no, account, summary, debit, credit, dept, project, "
                "partner_kind, partner, currency, fx_rate, fx_amount) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s)",
                [(vid, i + 1, x["account"], x["summary"], x["debit"], x["credit"], x["dept"], x["project"],
                  x["partner_kind"], x["partner"], x["currency"], x["fx_rate"], x["fx_amount"])
                 for i, x in enumerate(clean)])
            if comp.get("auto_post"):          # 即時過帳
                self.db.exec("UPDATE vouchers SET status=2, approved_by=%s, approved_at=NOW(), posted_by=%s, "
                             "posted_at=NOW() WHERE id=%s", (self.uid, self.uid, vid))
        self.log(action, v_no, "%s %s" % (v_type, total))
        return vid

    def delete_voucher(self, vid):
        self.need("VOU")
        v = self.db.row("SELECT * FROM vouchers WHERE id=%s", (vid,))
        if not v:
            return
        if v["status"] != 0:
            raise BizError("只能刪除未審核的傳票；已審核或已過帳請改用「作廢」")
        if v["created_by"] != self.uid and not self.can("APR"):
            raise BizError("只能刪除自己製作的傳票")
        self._check_open(v["v_date"])
        with self.db.transaction():
            self.db.exec("DELETE FROM voucher_lines WHERE voucher_id=%s", (vid,))
            self.db.exec("DELETE FROM vouchers WHERE id=%s", (vid,))
        self.log("voucher_delete", v["v_no"])

    def _change_status(self, ids, frm, to, action, extra_sql="", check=None):
        self.need("APR")
        done, errs = [], []
        for vid in ids:
            v = self.db.row("SELECT * FROM vouchers WHERE id=%s", (vid,))
            try:
                if not v:
                    raise BizError("傳票不存在")
                if v["status"] not in frm:
                    raise BizError("狀態是「%s」" % STATUS[v["status"]])
                self._check_open(v["v_date"])
                if check:
                    check(v)
                self.db.exec("UPDATE vouchers SET status=%%s%s WHERE id=%%s" % extra_sql,
                             (to, vid) if "%s" not in extra_sql else (to, self.uid, vid))
                self.log(action, v["v_no"])
                done.append(v["v_no"])
            except BizError as e:
                errs.append("%s：%s" % (v["v_no"] if v else vid, e))
        return done, errs

    def _not_own(self, v):
        if self.company().get("separate_approver") and v["created_by"] == self.uid and not self.user["is_admin"]:
            raise BizError("不能審核自己製作的傳票（公司設定為製單與審核分離）")

    def approve(self, ids):
        return self._change_status(ids, (0,), 1, "voucher_approve", ", approved_by=%s, approved_at=NOW()",
                                   self._not_own)

    def unapprove(self, ids):
        return self._change_status(ids, (1,), 0, "voucher_return", ", approved_by='', approved_at=NULL")

    def post(self, ids):
        return self._change_status(ids, (1,), 2, "voucher_post", ", posted_by=%s, posted_at=NOW()")

    def approve_and_post(self, ids):
        ok1, err1 = self.approve([i for i in ids if self.db.value("SELECT status FROM vouchers WHERE id=%s", (i,)) == 0])
        ok2, err2 = self.post(ids)
        return ok2, err1 + [e for e in err2 if "未審核" not in e]

    def unpost(self, ids):
        def only_mgr(v):
            if v["v_type"] == "結帳":
                raise BizError("結帳傳票請用「年度結帳 → 取消結帳」")
        return self._change_status(ids, (2,), 1, "voucher_unpost", ", posted_by='', posted_at=NULL", only_mgr)

    def void(self, ids):
        def chk(v):
            if v["v_type"] == "結帳":
                raise BizError("結帳傳票不能作廢")
        return self._change_status(ids, (0, 1), 9, "voucher_void", "", chk)

    # ================================================================ 年度結帳
    def year_closed(self, year) -> bool:
        s, e = rocdate.fiscal_year_range(year, int(self.company().get("fiscal_start_month") or 1))
        return bool(self.db.value("SELECT 1 FROM vouchers WHERE v_type='結帳' AND v_date BETWEEN %s AND %s "
                                  "AND status=2", (s, e)))

    def year_end_close(self, year):
        """把當年度損益類科目（4～8）結轉到 3351 累積盈虧，產生已過帳的結帳傳票。"""
        self.need("CLS")
        s, e = rocdate.fiscal_year_range(year, int(self.company().get("fiscal_start_month") or 1))
        if self.year_closed(year):
            raise BizError("%d 年度已結帳；如需重做請先「取消結帳」" % (year - 1911))
        pending = self.db.value("SELECT COUNT(*) FROM vouchers WHERE v_date BETWEEN %s AND %s AND status IN (0,1)",
                                (s, e))
        if pending:
            raise BizError("年度內還有 %d 張傳票未過帳，請先處理" % pending)
        if not self.account("3351"):
            raise BizError("找不到 3351 累積盈虧科目")
        rows = self.db.rows(
            "SELECT l.account, SUM(l.debit) d, SUM(l.credit) c FROM voucher_lines l JOIN vouchers v ON v.id=l.voucher_id "
            "WHERE v.status=2 AND v.v_date BETWEEN %s AND %s AND LEFT(l.account,1) IN ('4','5','6','7','8') "
            "GROUP BY l.account HAVING SUM(l.debit)<>SUM(l.credit) ORDER BY l.account", (s, e))
        if not rows:
            raise BizError("本年度沒有損益科目餘額，不需結帳")
        lines, net = [], Decimal(0)
        for r in rows:
            bal = Decimal(r["d"]) - Decimal(r["c"])            # 借餘為正
            lines.append(dict(account=r["account"], summary="年度結帳", debit=-bal if bal < 0 else Decimal(0),
                              credit=bal if bal > 0 else Decimal(0)))
            net += bal
        # net>0 代表費損大於收益（虧損）→ 借累積盈虧
        lines.append(dict(account="3351", summary="本期損益結轉", debit=net if net > 0 else Decimal(0),
                          credit=-net if net < 0 else Decimal(0)))
        lines = [x for x in lines if x["debit"] or x["credit"]]
        total = sum(x["debit"] for x in lines)
        with self.db.transaction():
            v_no = self.next_voucher_no(e)
            vid = self.db.exec("INSERT INTO vouchers (v_no, v_date, v_type, status, memo, total, created_by, "
                               "approved_by, approved_at, posted_by, posted_at) VALUES (%s, %s, '結帳', 2, %s, %s, %s, "
                               "%s, NOW(), %s, NOW())",
                               (v_no, e, "%d 年度損益結轉" % (year - 1911), total, self.uid, self.uid, self.uid))
            self.db.exec_many("INSERT INTO voucher_lines (voucher_id, line_no, account, summary, debit, credit) "
                              "VALUES (%s, %s, %s, %s, %s, %s)",
                              [(vid, i + 1, x["account"], x["summary"], x["debit"], x["credit"])
                               for i, x in enumerate(lines)])
        self.log("year_close", year, "net=%s" % (-net))
        return vid, -net     # 回傳本期淨利（正＝獲利）

    def year_end_reopen(self, year):
        self.need("CLS")
        s, e = rocdate.fiscal_year_range(year, int(self.company().get("fiscal_start_month") or 1))
        self._check_open(e)
        ids = [r["id"] for r in self.db.rows("SELECT id FROM vouchers WHERE v_type='結帳' AND v_date BETWEEN %s AND %s",
                                             (s, e))]
        if not ids:
            raise BizError("此年度尚未結帳")
        with self.db.transaction():
            for vid in ids:
                self.db.exec("DELETE FROM voucher_lines WHERE voucher_id=%s", (vid,))
                self.db.exec("DELETE FROM vouchers WHERE id=%s", (vid,))
        self.log("year_reopen", year)

    # ================================================================ 外幣現值調整
    def revaluation_preview(self, as_of):
        """外幣科目：外幣餘額 × 最新匯率 與 帳面金額的差額。"""
        d = rocdate.read(as_of)
        out = []
        for a in self.db.rows("SELECT * FROM accounts WHERE currency<>'' AND level=4 AND active=1 ORDER BY code"):
            r = self.db.row("SELECT SUM(l.debit-l.credit) book, SUM(l.fx_amount) fx FROM voucher_lines l "
                            "JOIN vouchers v ON v.id=l.voucher_id WHERE v.status=2 AND v.v_date<=%s AND l.account=%s",
                            (d, a["code"]))
            book, fx = Decimal(r["book"] or 0), Decimal(r["fx"] or 0)
            rate = self.currency_rate(a["currency"])
            value = (fx * rate).quantize(CENT, ROUND_HALF_UP)
            out.append(dict(code=a["code"], name=a["name"], currency=a["currency"], fx=fx, rate=rate, book=book,
                            value=value, diff=value - book))
        return out

    def revaluation_voucher(self, as_of):
        self.need("CLS")
        d = rocdate.read(as_of)
        lines = []
        for r in self.revaluation_preview(d):
            if not r["diff"]:
                continue
            summ = "外幣評價 %s %s @%s" % (r["currency"], f"{r['fx']:,.2f}", r["rate"])
            if r["diff"] > 0:
                lines += [dict(account=r["code"], summary=summ, debit=r["diff"]),
                          dict(account="7131", summary=summ, credit=r["diff"])]
            else:
                lines += [dict(account="7221", summary=summ, debit=-r["diff"]),
                          dict(account=r["code"], summary=summ, credit=-r["diff"])]
        if not lines:
            raise BizError("外幣科目帳面金額與現值相同，不需調整")
        return self.save_voucher(None, d, "調整", "期末外幣現值調整", lines)
