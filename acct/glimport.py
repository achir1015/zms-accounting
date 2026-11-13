"""拋轉匯入：接收「資料助秘之一般公司進銷存」與「資料助秘之一般公司人事薪資差勤」產生的傳票批次
（zms-gl 格式，.zmsgl 拋轉檔或直接傳送）。

* 同一批次（batch_uid）只能匯入一次；匯入後產生「未審核」傳票（公司設定即時過帳時直接過帳），
  摘要前依來源加 [進銷存] 或 [人事薪資]。
* 批次內需要的明細科目、客戶、廠商、部門若會計系統還沒有，會自動建立（科目須有上層科目）。
* 整批一起成功或一起失敗；關帳月份、科目停用、借貸不平衡等都會擋下並說明是哪一張。
* 取消匯入：批次內傳票都還是「未審核」時，可以整批刪除，來源系統才能取消拋轉、修改單據。
"""
import datetime as dt
import json

from . import rocdate
from . import books as B   # books 也會匯入本模組（循環匯入），所以執行時才取用 B.BizError


def BizError(msg):
    return B.BizError(msg)


def money(v):
    return B.money(v)

FORMAT = "zms-gl"
# 拋轉來源可能用到、預設科目表沒有的科目：(名稱, 正常餘額)
KNOWN_ACCOUNTS = {"1219": ("備抵存貨跌價損失", "C"), "5115": ("存貨盤盈虧", "D"), "5116": ("存貨報廢損失", "D"),
                  "5117": ("存貨跌價及呆滯損失", "D"),
                  # 人事薪資差勤
                  "2145": ("應付休假給付", "C"), "2175": ("代扣自提勞退", "C")}


def source_label(source):
    """依批次的 source 判斷來源簡稱（摘要前綴、自動建立科目備註用）。"""
    return "人事薪資" if "人事薪資" in (source or "") else "進銷存"


class _DryRun(Exception):
    pass


class GLImportMixin:
    def gl_imports(self, limit=300):
        self.need("VOU", 1)
        return self.db.rows("SELECT * FROM gl_imports ORDER BY id DESC LIMIT %s", (limit,))

    def gl_import_status(self, batch_uid):
        self.need("VOU", 1)
        r = self.db.row("SELECT * FROM gl_imports WHERE batch_uid=%s ORDER BY id DESC LIMIT 1", (batch_uid,))
        if not r:
            return None
        ids = json.loads(r["voucher_ids"] or "[]")
        st = self.db.rows("SELECT status, COUNT(*) c FROM vouchers WHERE id IN (%s) GROUP BY status"
                          % ",".join(str(int(i)) for i in ids)) if ids else []
        r["by_status"] = {x["status"]: x["c"] for x in st}
        return r

    def preview_gl_batch(self, batch, allow_other_company=False):
        """試匯入（不寫入）：回傳摘要與會自動建立的資料；有問題時拋出 BizError。"""
        try:
            self._import(batch, allow_other_company, dry=True)
        except _DryRun as e:
            return e.args[0]

    def import_gl_batch(self, batch, allow_other_company=False):
        """正式匯入；回傳 dict(voucher_nos, count, total)。"""
        return self._import(batch, allow_other_company, dry=False)

    def _import(self, batch, allow_other_company, dry):
        self.need("VOU")
        if not isinstance(batch, dict) or batch.get("format") != FORMAT:
            raise BizError("這不是可匯入的拋轉檔（進銷存／人事薪資），格式不符")
        if int(batch.get("version") or 0) > 1:
            raise BizError("拋轉檔版本較新，請先更新會計系統")
        uid = str(batch.get("batch_uid") or "")
        if not uid:
            raise BizError("拋轉檔缺少批次代碼")
        old = self.db.row("SELECT * FROM gl_imports WHERE batch_uid=%s AND status=1", (uid,))
        if old:
            raise BizError("此拋轉批次 %s 已在 %s 匯入過（傳票 %s），不會重複匯入"
                           % (old["batch_no"], rocdate.show(old["imported_at"]), old["voucher_nos"]))
        comp = self.company()
        bc = batch.get("company") or {}
        if comp.get("tax_id") and bc.get("tax_id") and comp["tax_id"] != bc["tax_id"] and not allow_other_company:
            raise BizError("拋轉檔的公司（%s，統編 %s）與本會計系統的公司（統編 %s）不同"
                           % (bc.get("name", ""), bc["tax_id"], comp["tax_id"]))
        vouchers = batch.get("vouchers") or []
        if not vouchers:
            raise BizError("拋轉檔裡沒有傳票")
        label = source_label(batch.get("source"))
        created = dict(accounts=[], partners=[], departments=[])
        out_nos, out_ids, total = [], [], money(0)
        names = {a["code"]: a.get("name", "") for a in batch.get("accounts") or []}
        try:
            with self.db.transaction():
                # 1. 科目
                used = {ln.get("account", "") for v in vouchers for ln in v.get("lines") or []}
                have = {r["code"]: r for r in self.db.rows("SELECT code, level, active FROM accounts")}
                for code in sorted(used):
                    if code in have:
                        continue
                    parent = code[:-1]
                    if len(code) != 4 or parent not in have:
                        raise BizError("會計科目 %s %s 不存在，且沒有上層科目 %s 可以自動建立；請先在會計科目新增"
                                       % (code, names.get(code, ""), parent))
                    nm, nature = KNOWN_ACCOUNTS.get(code, (names.get(code) or "", ""))
                    if not nm:
                        raise BizError("會計科目 %s 不存在，拋轉檔也沒有科目名稱" % code)
                    if not nature:
                        nature = "C" if code[0] in "234" or code[:2] == "71" else "D"
                    self.db.exec("INSERT INTO accounts (code, name, parent, level, nature, memo) VALUES "
                                 "(%s, %s, %s, 4, %s, %s)", (code, nm[:60], parent, nature, "%s拋轉自動建立" % label))
                    have[code] = dict(code=code, level=4, active=1)
                    created["accounts"].append("%s %s" % (code, nm))
                # 2. 往來對象、部門
                for p in batch.get("partners") or []:
                    k, c = p.get("kind"), (p.get("code") or "").strip()
                    if k not in ("C", "V") or not c:
                        continue
                    if not self.db.value("SELECT 1 FROM partners WHERE kind=%s AND code=%s", (k, c)):
                        self.db.exec("INSERT INTO partners (kind, code, name, short_name, tax_id, contact, phone, address) "
                                     "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                                     (k, c[:12], (p.get("name") or c)[:80], (p.get("short_name") or "")[:20],
                                      (p.get("tax_id") or "")[:10], (p.get("contact") or "")[:30],
                                      (p.get("phone") or "")[:30], (p.get("address") or "")[:200]))
                        created["partners"].append("%s %s %s" % ("客戶" if k == "C" else "廠商", c, p.get("name", "")))
                for dp in batch.get("departments") or []:
                    c = (dp.get("code") or "").strip()
                    if c and not self.db.value("SELECT 1 FROM departments WHERE code=%s", (c,)):
                        self.db.exec("INSERT INTO departments (code, name) VALUES (%s, %s)", (c[:10], (dp.get("name") or c)[:40]))
                        created["departments"].append("%s %s" % (c, dp.get("name", "")))
                # 3. 傳票
                cash = {r["code"] for r in self.db.rows("SELECT code FROM accounts WHERE is_cash=1")}
                preview = []
                for v in vouchers:
                    ref = v.get("ref", "")
                    try:
                        d = rocdate.read(v.get("date"))
                    except ValueError as e:
                        raise BizError("%s：%s" % (ref, e))
                    if self.period_closed(d):
                        raise BizError("%s：%s 已關帳，不能匯入（請先重新開帳或改拋轉期間）"
                                       % (ref, rocdate.ym_show(rocdate.ym(d))))
                    try:
                        clean, tot = self._clean_lines(v.get("lines") or [])
                    except BizError as e:
                        raise BizError("%s：%s" % (ref, e))
                    dr_cash = any(x["account"] in cash and x["debit"] for x in clean)
                    cr_cash = any(x["account"] in cash and x["credit"] for x in clean)
                    vtype = "收" if dr_cash and not cr_cash else "支" if cr_cash and not dr_cash else "轉"
                    memo = ("[%s] %s" % (label, v.get("memo") or ref))[:200]
                    preview.append(dict(ref=ref, date=d, v_type=vtype, memo=memo, total=tot, lines=clean))
                    total += tot
                    if dry:
                        continue
                    no = self.next_voucher_no(d)
                    vid = self.db.exec("INSERT INTO vouchers (v_no, v_date, v_type, memo, total, created_by) VALUES "
                                       "(%s, %s, %s, %s, %s, %s)", (no, d, vtype, memo, tot, self.uid))
                    self.db.exec_many(
                        "INSERT INTO voucher_lines (voucher_id, line_no, account, summary, debit, credit, dept, project, "
                        "partner_kind, partner, currency, fx_rate, fx_amount) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, "
                        "%s, %s, %s, %s, %s)",
                        [(vid, i + 1, x["account"], x["summary"], x["debit"], x["credit"], x["dept"], x["project"],
                          x["partner_kind"], x["partner"], x["currency"], x["fx_rate"], x["fx_amount"])
                         for i, x in enumerate(clean)])
                    if comp.get("auto_post"):
                        self.db.exec("UPDATE vouchers SET status=2, approved_by=%s, approved_at=NOW(), posted_by=%s, "
                                     "posted_at=NOW() WHERE id=%s", (self.uid, self.uid, vid))
                    out_nos.append(no)
                    out_ids.append(vid)
                if dry:
                    raise _DryRun(dict(count=len(preview), total=total, vouchers=preview, created=created,
                                       company=bc, batch_no=batch.get("batch_no", ""),
                                       date_from=batch.get("date_from"), date_to=batch.get("date_to"),
                                       source=batch.get("source", "")))
                nos = "%s～%s" % (out_nos[0], out_nos[-1]) if len(out_nos) > 1 else out_nos[0]
                self.db.exec("INSERT INTO gl_imports (batch_uid, batch_no, source, company_name, tax_id, date_from, "
                             "date_to, voucher_count, total, voucher_ids, voucher_nos, created_info, imported_by) VALUES "
                             "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                             (uid, batch.get("batch_no", "")[:20], (batch.get("source") or "")[:60],
                              (bc.get("name") or "")[:80], (bc.get("tax_id") or "")[:10], _d(batch.get("date_from")),
                              _d(batch.get("date_to")), len(out_ids), total, json.dumps(out_ids), nos[:60],
                              json.dumps(created, ensure_ascii=False)[:2000], self.uid))
        except _DryRun:
            raise
        self.log("gl_import", batch.get("batch_no", ""), "%d 張傳票 %s" % (len(out_nos), total))
        return dict(voucher_nos=out_nos, count=len(out_nos), total=total, created=created)

    def cancel_gl_import(self, batch_uid):
        """取消匯入：批次內傳票都還是未審核時整批刪除。"""
        self.need("VOU")
        r = self.db.row("SELECT * FROM gl_imports WHERE batch_uid=%s AND status=1", (batch_uid,))
        if not r:
            raise BizError("找不到這個拋轉批次的匯入紀錄（可能已取消）")
        ids = json.loads(r["voucher_ids"] or "[]")
        vs = self.db.rows("SELECT id, v_no, status, v_date FROM vouchers WHERE id IN (%s)"
                          % ",".join(str(int(i)) for i in ids)) if ids else []
        bad = [v["v_no"] for v in vs if v["status"] != 0]
        if bad:
            raise BizError("傳票 %s 已審核或過帳，請會計人員先退回成未審核，才能取消匯入" % "、".join(bad[:5]))
        for v in vs:
            if self.period_closed(v["v_date"]):
                raise BizError("傳票 %s 所在月份已關帳" % v["v_no"])
        with self.db.transaction():
            if ids:
                self.db.exec("DELETE FROM voucher_lines WHERE voucher_id IN (%s)" % ",".join(str(int(i)) for i in ids))
                self.db.exec("DELETE FROM vouchers WHERE id IN (%s)" % ",".join(str(int(i)) for i in ids))
            self.db.exec("UPDATE gl_imports SET status=9, canceled_by=%s, canceled_at=NOW() WHERE id=%s",
                         (self.uid, r["id"]))
        self.log("gl_import_cancel", r["batch_no"], r["voucher_nos"])
        return dict(deleted=len(vs))


def _d(v):
    try:
        return rocdate.read(v) if v else None
    except ValueError:
        return None


_ = dt
