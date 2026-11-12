"""傳票登錄、傳票查詢、審核過帳、傳票列印。"""
from decimal import Decimal

import flet as ft

from .. import printing, rocdate
from ..books import STATUS, V_TYPE_NAMES, BizError, money
from . import theme as T

TYPE_STYLE = [("收", "收入", ft.Icons.ADD_CARD, "green"), ("支", "支出", ft.Icons.REQUEST_QUOTE, "rose"),
              ("轉", "轉帳", ft.Icons.SWAP_HORIZ, "blue"), ("開帳", "開帳", ft.Icons.FLAG, "violet"),
              ("調整", "調整", ft.Icons.TUNE, "orange")]
H = 48   # 明細列輸入框高度


def parse_amount(s):
    try:
        return money(s)
    except BizError:
        return None


# ====================================================================== 明細列
class LineRow(ft.Container):
    def __init__(self, entry, data=None):
        self.entry = entry
        b = entry.ctx.books
        data = data or {}
        self.extra = dict(project=data.get("project", ""), currency=data.get("currency", ""),
                          fx_rate=data.get("fx_rate") or "", fx_amount=abs(Decimal(str(data.get("fx_amount") or 0))))
        self.no = ft.Text("", width=26, size=13, color=T.MUTED, text_align=ft.TextAlign.CENTER)
        self.account = T.dropdown("", entry.acct_opts, data.get("account") or None, width=250,
                                  on_select=self.on_account, hint_text="科目代號或名稱")
        self.summary = T.field("", data.get("summary", ""), width=196, hint_text="摘要", height=H)
        self.phrase = ft.PopupMenuButton(icon=ft.Icons.SHORT_TEXT, icon_size=18, tooltip="摘要片語", width=30,
                                         icon_color="#94A3B8",
                                         items=[ft.PopupMenuItem(p, on_click=lambda e, p=p: self.set_summary(p))
                                                for _, p in entry.phrases])
        self.debit = T.money_field("", data.get("debit"), width=130, hint_text="借方", on_change=self.changed,
                                   on_blur=self.tidy, on_submit=self.submit, height=H)
        self.credit = T.money_field("", data.get("credit"), width=130, hint_text="貸方", on_change=self.changed,
                                    on_blur=self.tidy, on_submit=self.submit, height=H)
        self.dept = T.dropdown("", entry.dept_opts, data.get("dept") or "", width=130, blank="部門",
                               filterable=False)
        self.partner = T.dropdown("", [], data.get("partner") or None, width=190, hint_text="往來對象")
        for tf in (self.summary, self.debit, self.credit):
            tf.content_padding = ft.Padding.symmetric(horizontal=12, vertical=14)
        self.more = ft.IconButton(ft.Icons.CURRENCY_EXCHANGE, icon_size=18, tooltip="外幣／專案",
                                  on_click=lambda e: self.extra_dialog())
        self.remove = ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18, icon_color="#E06666", tooltip="刪除這一行",
                                    on_click=lambda e: entry.remove_line(self))
        if T.MOBILE:
            # 手機：每一行明細是一張小卡片
            # 寬度一律按比例（手機字體放大時也不會超出卡片）
            for c in (self.account, self.summary, self.debit, self.credit, self.dept, self.partner):
                c.width = None
                c.expand = True
            self.debit.label, self.credit.label = "借方", "貸方"
            self.partner_row = ft.Row([self.partner])
            layout = ft.Column([
                ft.Row([self.no, self.account], spacing=6),
                ft.Row([self.summary, self.phrase], spacing=4),
                ft.Row([self.debit, self.credit], spacing=8),
                ft.Row([self.dept, self.more, self.remove], spacing=4),
                self.partner_row], spacing=8)
            super().__init__(layout, padding=12, border_radius=14, border=ft.Border.all(1, T.LINE),
                             bgcolor=T.CARD, data=T.READY)
        else:
            super().__init__(ft.Row([self.no, self.account, ft.Row([self.summary, self.phrase], spacing=4, width=230),
                                     self.debit, self.credit, self.dept, self.partner, self.more, self.remove],
                                    spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                             padding=ft.Padding.symmetric(vertical=4, horizontal=6), border_radius=10)
        self.refresh_partner(data.get("partner"))
        self.mark_extra()

    def set_summary(self, p):
        self.summary.value = p
        self.summary.update()

    def account_row(self):
        return self.entry.acct_map.get(self.account.value or "")

    def on_account(self, e=None):
        self.refresh_partner()
        a = self.account_row()
        if a and a["currency"] and not self.extra["currency"]:
            self.extra_dialog()
        self.update()

    def refresh_partner(self, keep=None):
        a = self.account_row()
        kind = a["partner_kind"] if a else ""
        self.partner.options = [ft.DropdownOption(key=k, text=t) for k, t in self.entry.partner_opts(kind)]
        self.partner.visible = bool(kind)
        if getattr(self, "partner_row", None) is not None:
            self.partner_row.visible = bool(kind)
        self.partner.hint_text = {"C": "選擇客戶", "V": "選擇廠商", "E": "選擇員工"}.get(kind, "")
        if not kind:
            self.partner.value = None
        elif keep:
            self.partner.value = keep

    def mark_extra(self):
        on = bool(self.extra["currency"] or self.extra["project"])
        self.more.icon_color = T.ACCENT if on else "#94A3B8"
        self.more.tooltip = "外幣 %s %s／專案 %s" % (self.extra["currency"], T.amt(self.extra["fx_amount"]),
                                                  self.extra["project"]) if on else "外幣／專案"

    def changed(self, e=None):
        self.entry.recalc()

    def tidy(self, e):
        v = parse_amount(e.control.value)
        if v:
            e.control.value = T.amt(v)
            if e.control is self.debit and self.credit.value:
                self.credit.value = ""
            if e.control is self.credit and self.debit.value:
                self.debit.value = ""
            self.update()
        self.entry.recalc()

    def submit(self, e):
        self.tidy(e)
        if self is self.entry.rows[-1]:
            self.entry.add_line(focus=True)

    def values(self):
        return dict(account=self.account.value or "", summary=self.summary.value, debit=self.debit.value,
                    credit=self.credit.value, dept=self.dept.value or "", partner=self.partner.value or "",
                    project=self.extra["project"], currency=self.extra["currency"],
                    fx_rate=self.extra["fx_rate"] or 0, fx_amount=self.extra["fx_amount"] or 0)

    def amounts(self):
        return parse_amount(self.debit.value) or Decimal(0), parse_amount(self.credit.value) or Decimal(0)

    def extra_dialog(self):
        c = self.entry.ctx
        b = c.books
        a = self.account_row()
        cur = T.dropdown("幣別", [(r["code"], "%s %s" % (r["code"], r["name"])) for r in b.master_rows("currencies")
                                if r["code"] != "TWD"], self.extra["currency"] or (a["currency"] if a else "") or "",
                         width=200, blank="（不使用外幣）", filterable=False)
        rate = T.field("匯率", str(self.extra["fx_rate"] or ""), width=140)
        fx = T.money_field("外幣金額", self.extra["fx_amount"], width=160)
        side = ft.RadioGroup(value="C" if (self.credit.value and not self.debit.value) else "D",
                             content=ft.Row([ft.Radio(value="D", label="借方"), ft.Radio(value="C", label="貸方")]))
        proj = T.dropdown("專案", self.entry.project_opts, self.extra["project"] or "", width=260, blank="（無）")
        result = T.muted("", 13)

        def on_cur(e=None):
            if cur.value:
                rate.value = str(b.currency_rate(cur.value).normalize())
            calc()
        cur.on_select = on_cur

        def calc(e=None):
            try:
                v = (money(fx.value) * Decimal(rate.value or 0)).quantize(Decimal("0.01"))
                result.value = "換算本國幣：%s 元" % T.amt(v) if cur.value else ""
            except Exception:
                result.value = ""
            result.update() if result.page else None
        fx.on_change = calc
        rate.on_change = calc
        if cur.value and not rate.value:
            rate.value = str(b.currency_rate(cur.value).normalize())

        def ok(e):
            self.extra["project"] = proj.value or ""
            if cur.value:
                try:
                    r, f = Decimal(rate.value or 0), money(fx.value)
                except Exception:
                    c.toast("匯率或外幣金額格式不對", True)
                    return
                base = (f * r).quantize(Decimal("0.01"))
                self.extra.update(currency=cur.value, fx_rate=r, fx_amount=f)
                (self.debit if side.value == "D" else self.credit).value = T.amt(base)
                (self.credit if side.value == "D" else self.debit).value = ""
            else:
                self.extra.update(currency="", fx_rate="", fx_amount=Decimal(0))
            self.mark_extra()
            c.close()
            self.entry.recalc()
            self.update()
        calc()
        c.dialog("外幣與專案", ft.Column([ft.Row([cur, rate]), ft.Row([fx, side]), result, ft.Divider(), proj],
                                       tight=True, spacing=12),
                 [T.btn("取消", kind="ghost", on_click=lambda e: c.close()), T.btn("確定", ft.Icons.CHECK, ok)],
                 icon=ft.Icons.CURRENCY_EXCHANGE, tone="teal", width=480)


# ====================================================================== 傳票登錄
class VoucherEntry(ft.Column):
    def __init__(self, ctx, v_type="轉", vid=None, copy_from=None):
        self.ctx = ctx
        b = ctx.books
        self.vid = None
        self.locked = False
        self.acct_opts = b.options("accounts")
        self.acct_map = {a["code"]: a for a in b.accounts(detail_only=True)}
        self.dept_opts = b.options("departments")
        self.project_opts = b.options("projects")
        self.phrases = b.options("phrases")
        self._partners = {}
        self.v_type = v_type
        self.type_row = ft.Row(spacing=8)
        self.date = T.date_field("傳票日期", width=160, on_blur=self.tidy_date)
        self.no = ft.Text("存檔後自動編號", size=15, weight=ft.FontWeight.W_700, color=T.PRIMARY)
        self.state = ft.Container()
        self.attach = T.field("附件張數", "0", width=100)
        self.memo = T.field("傳票備註", "", expand=True)
        self.rows = []
        self.lines = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)
        self.tot_d = ft.Text("0", size=18, weight=ft.FontWeight.W_800, color=T.TEXT)
        self.tot_c = ft.Text("0", size=18, weight=ft.FontWeight.W_800, color=T.TEXT)
        self.diff = ft.Container()
        self.lock_banner = ft.Container(visible=False)
        self.save_btn = T.btn("存檔", ft.Icons.SAVE, lambda e: self.save(False))
        self.save_new_btn = T.btn("存檔並新增下一張", ft.Icons.PLAYLIST_ADD, lambda e: self.save(True), kind="accent")
        self.del_btn = T.btn("刪除", ft.Icons.DELETE_OUTLINE, lambda e: self.delete(), kind="danger", visible=False)
        head = T.card(ft.Column([
            # 視窗較窄（iPad、縮小的視窗）時按鈕自動換到下一行
            ft.Row([self.type_row,
                    ft.Row([T.btn("套用常用分錄", ft.Icons.BOOKMARKS, lambda e: self.template_dialog(), kind="outline"),
                            T.btn("匯入明細", ft.Icons.UPLOAD_FILE, lambda e: self.import_dialog(), kind="outline"),
                            T.btn("新傳票", ft.Icons.NOTE_ADD, lambda e: self.reset(), kind="ghost")], spacing=8)],
                   wrap=True, run_spacing=10, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([self.date, ft.Column([T.muted("傳票號碼", 11), self.no], spacing=0), self.state, self.attach,
                    self.memo], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER)], spacing=14),
            padding=16)
        header_row = ft.Container(ft.Row([
            ft.Text("#", width=26, size=12, color=T.MUTED, text_align=ft.TextAlign.CENTER),
            *[ft.Text(t, width=w, size=12, color="#475569", weight=ft.FontWeight.W_700,
                      text_align=ft.TextAlign.RIGHT if t in ("借方金額", "貸方金額") else ft.TextAlign.LEFT)
              for t, w in (("會計科目", 250), ("摘要", 230), ("借方金額", 130), ("貸方金額", 130), ("部門", 130),
                           ("往來對象", 190))]], spacing=8),
            bgcolor="#EEF3FA", border_radius=10, padding=ft.Padding.symmetric(vertical=8, horizontal=6))
        header_row.visible = not T.MOBILE
        # 電腦版明細約 1130 寬：可視寬度不夠時（iPad、縮小的視窗）整片左右捲動，欄位不會被截掉
        grid = (self.lines if T.MOBILE else
                ft.Row([ft.Column([header_row, self.lines], width=1130, spacing=2)], scroll=ft.ScrollMode.AUTO,
                       expand=True, vertical_alignment=ft.CrossAxisAlignment.START))
        body = T.card(ft.Column([header_row if T.MOBILE else ft.Container(height=0), grid,
                                 ft.Row([T.btn("新增一行", ft.Icons.ADD, lambda e: self.add_line(True), kind="ghost"),
                                         T.muted("提示：在金額欄按 Enter 會自動新增下一行，摘要自動沿用上一行，金額自動帶入差額",
                                                 12)])], spacing=6), expand=True, padding=14)
        foot = T.card(ft.Row([
            total_box("借方合計", self.tot_d, "blue"), total_box("貸方合計", self.tot_c, "teal"), self.diff,
            ft.Container(expand=True), self.del_btn, self.save_btn, self.save_new_btn], spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER), padding=14)
        if T.MOBILE:
            # 手機：類別一排可換行、欄位一行一個、合計與按鈕上下排列
            self.type_row.wrap, self.type_row.run_spacing = True, 8
            self.date.width = self.attach.width = None
            self.date.expand, self.attach.expand = 3, 2
            self.memo.expand = False
            head = T.card(ft.Column([
                self.type_row,
                ft.Row([T.btn("常用分錄", ft.Icons.BOOKMARKS, lambda e: self.template_dialog(), kind="outline"),
                        T.btn("新傳票", ft.Icons.NOTE_ADD, lambda e: self.reset(), kind="ghost")], wrap=True),
                ft.Row([self.date, self.attach], spacing=10),
                ft.Row([T.muted("傳票號碼", 12), self.no, self.state], spacing=10),
                self.memo], spacing=12, data=T.READY), padding=14)
            for b_ in (self.save_btn, self.save_new_btn, self.del_btn):
                b_.expand = True
            foot = T.card(ft.Column([
                ft.Row([ft.Container(total_box("借方合計", self.tot_d, "blue"), expand=True),
                        ft.Container(total_box("貸方合計", self.tot_c, "teal"), expand=True)], spacing=10),
                self.diff,
                ft.Row([self.del_btn, self.save_btn], spacing=10), ft.Row([self.save_new_btn])],
                spacing=10, data=T.READY), padding=14)
        super().__init__([self.lock_banner, head, body, foot], spacing=12, expand=True)
        if vid:
            self.load(b.voucher(vid))
        elif copy_from:
            v = b.voucher(copy_from)
            self.set_type(v["v_type"] if v["v_type"] in [t[0] for t in TYPE_STYLE] else "轉", refresh=False)
            self.memo.value = v["memo"]
            for ln in v["lines"]:
                self.add_line(data=ln, refresh=False)
            self.recalc(refresh=False)
        else:
            self.set_type(v_type, refresh=False)
            for _ in range(2):
                self.add_line(refresh=False)
            self.recalc(refresh=False)
        self.render_types()

    # ---------------------------------------------------------- 類別
    def render_types(self):
        out = []
        for code, name, icon, tone in TYPE_STYLE:
            sel = code == self.v_type
            bg, fg = T.TONES[tone]
            out.append(ft.Container(ft.Row([ft.Icon(icon, size=18, color=ft.Colors.WHITE if sel else fg),
                                            ft.Text(name + "傳票" if len(name) == 2 and code in "收支轉" else name,
                                                    size=14, weight=ft.FontWeight.W_700,
                                                    color=ft.Colors.WHITE if sel else fg)], spacing=6, tight=True),
                                    bgcolor=fg if sel else bg, border_radius=12, ink=True,
                                    padding=ft.Padding.symmetric(horizontal=14, vertical=9),
                                    on_click=None if self.locked else (lambda e, c=code: self.set_type(c))))
        self.type_row.controls = out

    def set_type(self, code, refresh=True):
        self.v_type = code
        self.render_types()
        if refresh:
            self.update()

    def tidy_date(self, e):
        try:
            self.date.value = rocdate.show(rocdate.read(self.date.value))
            self.date.error_text = None
        except ValueError as ex:
            self.date.error_text = str(ex)
        self.date.update()

    # ---------------------------------------------------------- 明細
    def partner_opts(self, kind):
        if not kind:
            return []
        if kind not in self._partners:
            self._partners[kind] = self.ctx.books.options({"C": "customers", "V": "vendors", "E": "employees"}[kind])
        return self._partners[kind]

    def add_line(self, focus=False, data=None, refresh=True):
        if data is None and self.rows:
            prev = self.rows[-1]
            d, c = self.totals()
            data = dict(summary=prev.summary.value)
            if d > c:
                data["credit"] = d - c
            elif c > d:
                data["debit"] = c - d
        row = LineRow(self, data)
        self.rows.append(row)
        self.renumber()
        self.lines.controls.append(row)
        if refresh:
            self.recalc(refresh=False)
            self.update()
            if focus:
                row.account.focus()

    def remove_line(self, row):
        if len(self.rows) <= 1 or self.locked:
            return
        self.rows.remove(row)
        self.lines.controls.remove(row)
        self.renumber()
        self.recalc()

    def renumber(self):
        for i, r in enumerate(self.rows, 1):
            r.no.value = str(i)
            r.bgcolor = "#F8FAFD" if i % 2 == 0 else None

    def totals(self):
        d = c = Decimal(0)
        for r in self.rows:
            a, b = r.amounts()
            d += a
            c += b
        return d, c

    def recalc(self, refresh=True):
        d, c = self.totals()
        self.tot_d.value, self.tot_c.value = T.amt(d), T.amt(c)
        if d == c and d:
            self.diff.content = T.chip("借貸平衡", "green", ft.Icons.CHECK_CIRCLE, 13)
        elif d == c:
            self.diff.content = T.chip("尚未輸入金額", "slate", ft.Icons.EDIT, 13)
        else:
            self.diff.content = T.chip("差額 %s" % T.amt(abs(d - c)), "rose", ft.Icons.ERROR_OUTLINE, 13)
        if refresh:
            self.update()

    # ---------------------------------------------------------- 載入／存檔
    def load(self, v):
        self.vid = v["id"]
        self.set_type(v["v_type"], refresh=False)
        self.date.value = rocdate.show(v["v_date"])
        self.no.value = v["v_no"]
        self.state.content = T.status_chip(v["status"])
        self.attach.value = str(v["attachments"])
        self.memo.value = v["memo"]
        self.rows, self.lines.controls = [], []
        for ln in v["lines"]:
            ln = dict(ln)
            ln["debit"], ln["credit"] = ln["debit"] or None, ln["credit"] or None
            self.add_line(data=ln, refresh=False)
        self.recalc(refresh=False)
        self.locked = v["status"] != 0 or v["v_type"] == "結帳"
        b = self.ctx.books
        if not self.locked and v["created_by"] != b.uid and not b.can("APR"):
            self.locked = True
        self.del_btn.visible = not self.locked
        self.save_new_btn.visible = not self.locked
        self.save_btn.visible = not self.locked
        if self.locked:
            self.lock_banner.content = ft.Container(ft.Row([
                ft.Icon(ft.Icons.LOCK, color=T.WARN), ft.Text("此傳票%s，只能查看。如需修改，請主管在「審核過帳」退回。"
                                                              % STATUS[v["status"]], color="#92400E")]),
                bgcolor="#FFF7E6", border_radius=12, padding=12, border=ft.Border.all(1, "#FCD9A0"))
            self.lock_banner.visible = True
            for r in self.rows:
                for ctl in (r.account, r.summary, r.phrase, r.debit, r.credit, r.dept, r.partner, r.more, r.remove):
                    ctl.disabled = True
            for ctl in (self.date, self.attach, self.memo):
                ctl.disabled = True

    def reset(self):
        self.ctx.app.go("voucher_entry", v_type=self.v_type)

    def save(self, then_new):
        b = self.ctx.books
        vid = self.ctx.guard(b.save_voucher, self.vid, self.date.value, self.v_type, self.memo.value,
                             [r.values() for r in self.rows], int(self.attach.value or 0) if
                             (self.attach.value or "0").isdigit() else 0)
        if not vid:
            return
        v = b.voucher(vid)
        self.ctx.toast("已存檔：%s %s（%s）" % (V_TYPE_NAMES[v["v_type"]], v["v_no"], STATUS[v["status"]]))
        if then_new:
            keep_date = self.date.value
            self.ctx.app.go("voucher_entry", v_type=self.v_type)
            body = self.ctx.app.body.content
            body.date.value = keep_date
            body.update()
        else:
            self.ctx.app.go("voucher_entry", vid=vid)

    def delete(self):
        if not self.vid:
            self.reset()
            return
        self.ctx.confirm("刪除傳票", "確定要刪除傳票 %s 嗎？刪除後無法復原。" % self.no.value,
                         lambda: self.ctx.guard(self.ctx.books.delete_voucher, self.vid, ok="已刪除")
                         and self.reset(), yes="刪除")

    # ---------------------------------------------------------- 匯入明細（期初餘額等大量分錄）
    def import_dialog(self):
        from .. import csvio
        c = self.ctx
        if self.locked:
            return

        async def template(e):
            await c.save_generated("傳票明細範本.csv", csvio.voucher_template)

        async def pick(e):
            path = await c.pick_csv("選擇傳票明細（CSV）")
            if not path:
                return
            lines = c.guard(csvio.read_voucher_lines, path)
            if not lines:
                return
            unknown = [ln["account"] for ln in lines if ln["account"] not in self.acct_map]
            if unknown:
                c.toast("找不到明細科目：%s（請先到會計科目新增）" % "、".join(sorted(set(unknown))[:8]), True)
                return
            if all(not r.account.value and not any(r.amounts()) for r in self.rows):
                self.rows, self.lines.controls = [], []
            for ln in lines:
                self.add_line(data=ln, refresh=False)
            c.close()
            self.recalc()
            c.toast("已帶入 %d 行明細，請確認借貸平衡後存檔" % len(lines))

        c.dialog("匯入傳票明細", ft.Column([
            T.muted("適合一次輸入大量分錄，例如期初開帳。用 Excel 整理成以下欄位，另存為 CSV：", 13),
            ft.Container(ft.Text("　".join(csvio.VOUCHER_COLS), size=14, weight=ft.FontWeight.W_600, color=T.PRIMARY),
                         bgcolor="#EEF3FA", border_radius=10, padding=12),
            T.muted("科目代號用四碼明細科目；借方、貸方擇一填寫；往來對象填客戶、廠商或員工代號（應收應付科目必填）。", 12),
            ft.Row([T.btn("下載範本", ft.Icons.DOWNLOAD, template, kind="outline"),
                    T.btn("選擇檔案", ft.Icons.UPLOAD_FILE, pick)])], tight=True, spacing=12),
            [T.btn("關閉", kind="ghost", on_click=lambda e: c.close())], icon=ft.Icons.UPLOAD_FILE, tone="sky",
            width=560)

    # ---------------------------------------------------------- 常用分錄
    def template_dialog(self):
        c, b = self.ctx, self.ctx.books
        tpls = b.templates()
        if not tpls:
            c.toast("尚未建立常用分錄", True)
            return
        pick = T.dropdown("常用分錄", [(t["id"], t["name"]) for t in tpls], width=360)
        amount = T.money_field("金額", "", width=180, hint_text="依分錄說明輸入")
        hint = T.muted("", 12)
        preview = ft.Column(spacing=4)

        def show(e=None):
            t = next((t for t in tpls if str(t["id"]) == (pick.value or "")), None)
            if not t:
                return
            hint.value = t["memo"] or "金額會依各行比率自動計算；比率 0 的行請自行輸入。"
            lines = b.apply_template(t, amount.value or 0)
            names = self.acct_map
            preview.controls = [ft.Row([
                T.chip("借" if ln["debit"] or not ln["credit"] and tl["side"] == "D" else "貸",
                       "blue" if tl["side"] == "D" else "teal"),
                ft.Text("%s %s" % (ln["account"], names.get(ln["account"], {}).get("name", "")), width=220, size=13),
                ft.Text(ln["summary"], width=150, size=13, color=T.MUTED),
                ft.Text(T.amt(ln["debit"] or ln["credit"], blank_zero=True) or "（自行輸入）", size=13, width=110,
                        text_align=ft.TextAlign.RIGHT)]) for ln, tl in zip(lines, t["lines"])]
            c.page.update()
        pick.on_select = show
        amount.on_change = show

        def apply(e):
            t = next((t for t in tpls if str(t["id"]) == (pick.value or "")), None)
            if not t:
                return
            try:
                lines = b.apply_template(t, amount.value or 0)
            except BizError as ex:
                c.toast(str(ex), True)
                return
            # 目前沒有內容的空白列就清掉
            if all(not r.account.value and not any(r.amounts()) for r in self.rows):
                self.rows, self.lines.controls = [], []
            for ln in lines:
                ln["debit"], ln["credit"] = ln["debit"] or None, ln["credit"] or None
                self.add_line(data=ln, refresh=False)
            if t["v_type"] in [x[0] for x in TYPE_STYLE]:
                self.v_type = t["v_type"]
                self.render_types()
            if not self.memo.value:
                self.memo.value = t["name"]
            c.close()
            self.recalc()
        c.dialog("套用常用分錄", ft.Column([ft.Row([pick, amount]), hint, preview], tight=True, spacing=12),
                 [T.btn("取消", kind="ghost", on_click=lambda e: c.close()), T.btn("套用", ft.Icons.CHECK, apply)],
                 icon=ft.Icons.BOOKMARKS, tone="sky", width=620)


def total_box(title, text, tone):
    bg, fg = T.TONES[tone]
    return ft.Container(ft.Column([ft.Text(title, size=11, color=fg), text], spacing=0),
                        bgcolor=bg, border_radius=12, padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                        width=170)


# ====================================================================== 傳票查詢
class VoucherList(ft.Row):
    def __init__(self, ctx, focus=None):
        self.ctx = ctx
        b = ctx.books
        today = rocdate.today()
        self.start = T.date_field("起日", today.replace(month=1, day=1), width=145)
        self.end = T.date_field("迄日", today, width=145)
        self.status = T.dropdown("狀態", [(k, v) for k, v in STATUS.items()], "", width=130, blank="全部",
                                 filterable=False)
        self.vtype = T.dropdown("類別", [(k, V_TYPE_NAMES[k]) for k in V_TYPE_NAMES], "", width=140, blank="全部",
                                filterable=False)
        self.account = T.dropdown("科目", b.options("accounts"), "", width=220, blank="全部")
        self.keyword = T.field("關鍵字", "", width=180, hint_text="號碼或摘要", on_submit=lambda e: self.search())
        self.grid = Grid_for_vouchers(self.pick)
        self.detail = ft.Container(T.empty_state(ft.Icons.TOUCH_APP, "點選左邊的傳票查看明細"), width=420)
        left = ft.Column([
            T.card(ft.Row([self.start, self.end, self.status, self.vtype, self.account, self.keyword,
                           T.btn("查詢", ft.Icons.SEARCH, lambda e: self.search())], wrap=True, spacing=10),
                   padding=14),
            self.grid], expand=True, spacing=12)
        side = [] if T.MOBILE else [T.card(self.detail, padding=16)]     # 手機：明細改用彈出視窗
        super().__init__([left] + side, expand=True, spacing=14, data="split",
                         vertical_alignment=ft.CrossAxisAlignment.START)
        self.search(refresh=False)
        if focus:
            self.pick(b.voucher(focus), refresh=False)

    def search(self, refresh=True):
        try:
            s, e = rocdate.read(self.start.value), rocdate.read(self.end.value)
        except ValueError as ex:
            self.ctx.toast(str(ex), True)
            return
        rows = self.ctx.books.find_vouchers(s, e, self.status.value, self.vtype.value or "", self.keyword.value.strip(),
                                            self.account.value or "")
        self.grid.set_rows(rows)
        if refresh:
            self.update()

    def pick(self, v, refresh=True):
        b, c = self.ctx.books, self.ctx
        v = b.voucher(v["id"])
        names = b.account_names()
        st = v["status"]
        acts = []
        if st == 0 and b.can("VOU", 2):
            acts.append(T.btn("修改", ft.Icons.EDIT, lambda e: c.app.go("voucher_entry", vid=v["id"])))
            acts.append(T.btn("刪除", ft.Icons.DELETE_OUTLINE, lambda e: self.do(b.delete_voucher, v["id"]),
                              kind="danger"))
        elif b.can("VOU", 1):
            acts.append(T.btn("開啟", ft.Icons.OPEN_IN_NEW, lambda e: c.app.go("voucher_entry", vid=v["id"]),
                              kind="outline"))
        if b.can("APR", 2):
            if st == 0:
                acts.append(T.btn("審核並過帳", ft.Icons.DONE_ALL, lambda e: self.batch(b.approve_and_post, v),
                                  kind="accent"))
            if st == 1:
                acts.append(T.btn("過帳", ft.Icons.DONE_ALL, lambda e: self.batch(b.post, v), kind="accent"))
                acts.append(T.btn("退回", ft.Icons.UNDO, lambda e: self.batch(b.unapprove, v), kind="outline"))
            if st == 2 and v["v_type"] != "結帳":
                acts.append(T.btn("取消過帳", ft.Icons.UNDO, lambda e: self.batch(b.unpost, v), kind="outline"))
            if st in (0, 1):
                acts.append(T.btn("作廢", ft.Icons.BLOCK, lambda e: self.batch(b.void, v), kind="danger"))
        if b.can("VOU", 2):
            acts.append(T.btn("複製為新傳票", ft.Icons.CONTENT_COPY,
                              lambda e: c.app.go("voucher_entry", copy_from=v["id"]), kind="ghost"))
        acts.append(T.btn("列印", ft.Icons.PRINT, lambda e: print_voucher(c, v), kind="ghost"))
        lines = ft.Column([ft.Container(ft.Row([
            ft.Column([ft.Text("%s %s" % (ln["account"], names.get(ln["account"], "")), size=13,
                               weight=ft.FontWeight.W_600),
                       T.muted(ln["summary"] + ("　" + ln["partner"] if ln["partner"] else ""), 11)],
                      spacing=0, expand=True),
            ft.Text(T.amt(ln["debit"], True), width=95, size=13, text_align=ft.TextAlign.RIGHT, color="#1D4ED8"),
            ft.Text(T.amt(ln["credit"], True), width=95, size=13, text_align=ft.TextAlign.RIGHT, color="#0F766E")]),
            padding=ft.Padding.symmetric(vertical=6), border=ft.Border.only(bottom=ft.BorderSide(1, "#EEF1F5")))
            for ln in v["lines"]], spacing=0, scroll=ft.ScrollMode.AUTO, height=330)
        meta = "製單 %s%s%s" % (v["created_by"], "　審核 %s" % v["approved_by"] if v["approved_by"] else "",
                              "　過帳 %s" % v["posted_by"] if v["posted_by"] else "")
        self.detail.content = ft.Column([
            ft.Row([T.chip(V_TYPE_NAMES[v["v_type"]], T.VTYPE_TONE.get(v["v_type"], "slate")),
                    ft.Text(v["v_no"], size=18, weight=ft.FontWeight.W_800), ft.Container(expand=True),
                    T.status_chip(st)]),
            T.muted("%s　%s" % (rocdate.show(v["v_date"]), v["memo"] or ""), 13),
            ft.Row([ft.Text("科目／摘要", size=12, color=T.MUTED, expand=True),
                    ft.Text("借方", width=95, size=12, color=T.MUTED, text_align=ft.TextAlign.RIGHT),
                    ft.Text("貸方", width=95, size=12, color=T.MUTED, text_align=ft.TextAlign.RIGHT)]),
            lines,
            ft.Row([ft.Text("合計", weight=ft.FontWeight.W_700, expand=True),
                    ft.Text(T.amt(v["total"]), width=95, text_align=ft.TextAlign.RIGHT, weight=ft.FontWeight.W_700),
                    ft.Text(T.amt(v["total"]), width=95, text_align=ft.TextAlign.RIGHT, weight=ft.FontWeight.W_700)]),
            T.muted(meta, 11),
            ft.Row(acts, wrap=True, spacing=8, run_spacing=8)], spacing=8)
        if T.MOBILE:
            content, self.detail.content = self.detail.content, None
            lines.height = 240
            if refresh:
                c.dialog("傳票明細", content, [T.btn("關閉", kind="ghost", on_click=lambda e: c.close())],
                         icon=ft.Icons.RECEIPT_LONG, tone=T.VTYPE_TONE.get(v["v_type"], "slate"))
            return
        if refresh:
            self.update()

    def do(self, fn, vid):
        self.ctx.confirm("刪除傳票", "確定要刪除嗎？刪除後無法復原。",
                         lambda: self.ctx.guard(fn, vid, ok="已刪除") and self.after())

    def batch(self, fn, v):
        ok = self.ctx.guard(fn, [v["id"]])
        if ok:
            done, errs = ok
            if errs:
                self.ctx.toast("；".join(errs), True)
            else:
                self.ctx.toast("完成：%s" % "、".join(done))
            self.after(v)

    def after(self, v=None):
        if T.MOBILE:
            try:
                self.ctx.close()
            except Exception:
                pass
            self.search()
            return
        self.search(refresh=False)
        if v and self.ctx.books.voucher(v["id"]):
            self.pick(v, refresh=False)
        else:
            self.detail.content = T.empty_state(ft.Icons.TOUCH_APP, "點選左邊的傳票查看明細")
        self.update()


def Grid_for_vouchers(on_pick=None, selectable=False):
    return T.Grid([("v_no", "傳票號碼", "s", 88), ("v_date", "日期", "d", 74), ("v_type", "類別", "vtype", 40),
                   ("memo", "備註", "s", 110 if not selectable else 220), ("total", "金額", "n", 92),
                   ("status", "狀態", "status", 56), ("created_by", "製單", "s", 52)], on_pick=on_pick,
                  selectable=selectable, totals=("total",), empty="沒有符合條件的傳票")


# ====================================================================== 審核過帳
class Review(ft.Column):
    TABS = [(0, "待審核", ft.Icons.PENDING_ACTIONS, "amber"), (1, "已審核待過帳", ft.Icons.VERIFIED, "sky"),
            (2, "已過帳", ft.Icons.TASK_ALT, "green")]

    def __init__(self, ctx):
        self.ctx = ctx
        self.tab = 0
        self.tabs = ft.Row(spacing=10, wrap=True, run_spacing=8)
        self.grid = Grid_for_vouchers(selectable=True)
        self.actions = ft.Row(spacing=10)
        today = rocdate.today()
        self.start = T.date_field("起日", today.replace(month=1, day=1), width=145)
        self.end = T.date_field("迄日", today, width=145)
        super().__init__([
            T.page_header(ft.Icons.FACT_CHECK, "傳票審核過帳", "勾選傳票後執行；製單與審核分離可在公司設定調整", "amber"),
            T.card(ft.Row([self.tabs, ft.Container(expand=True), self.start, self.end,
                           T.btn("重新整理", ft.Icons.REFRESH, lambda e: self.load(), kind="outline")],
                          data="split"), padding=12),
            self.grid, T.card(self.actions, padding=12)], spacing=12, expand=True)
        self.load(refresh=False)

    def load(self, refresh=True):
        b = self.ctx.books
        try:
            s, e = rocdate.read(self.start.value), rocdate.read(self.end.value)
        except ValueError as ex:
            self.ctx.toast(str(ex), True)
            return
        counts = {k: len(b.find_vouchers(s, e, status=k, limit=5000)) for k, *_ in self.TABS}
        tabs = []
        for k, name, icon, tone in self.TABS:
            sel = k == self.tab
            bg, fg = T.TONES[tone]
            tabs.append(ft.Container(ft.Row([ft.Icon(icon, size=18, color=ft.Colors.WHITE if sel else fg),
                                             ft.Text("%s（%d）" % (name, counts[k]), size=14, weight=ft.FontWeight.W_700,
                                                     color=ft.Colors.WHITE if sel else fg)], spacing=6, tight=True),
                                     bgcolor=fg if sel else bg, border_radius=12, ink=True,
                                     padding=ft.Padding.symmetric(horizontal=14, vertical=9),
                                     on_click=lambda e, k=k: self.switch(k)))
        self.tabs.controls = tabs
        self.grid.set_rows(sorted(b.find_vouchers(s, e, status=self.tab, limit=5000), key=lambda v: v["v_no"]))
        A = []
        if self.tab == 0:
            A = [T.btn("審核", ft.Icons.VERIFIED, lambda e: self.run(b.approve)),
                 T.btn("審核並過帳", ft.Icons.DONE_ALL, lambda e: self.run(b.approve_and_post), kind="accent"),
                 T.btn("作廢", ft.Icons.BLOCK, lambda e: self.run(b.void, "作廢"), kind="danger")]
        elif self.tab == 1:
            A = [T.btn("過帳", ft.Icons.DONE_ALL, lambda e: self.run(b.post), kind="accent"),
                 T.btn("退回製單人", ft.Icons.UNDO, lambda e: self.run(b.unapprove), kind="outline"),
                 T.btn("作廢", ft.Icons.BLOCK, lambda e: self.run(b.void, "作廢"), kind="danger")]
        else:
            A = [T.btn("取消過帳", ft.Icons.UNDO, lambda e: self.run(b.unpost, "取消過帳"), kind="outline")]
        self.actions.controls = [T.muted("先勾選左側方框（表頭方框可全選），再按：", 13)] + A
        if refresh:
            self.update()

    def switch(self, k):
        self.tab = k
        self.load()

    def run(self, fn, confirm_word=None):
        rows = self.grid.selected_rows()
        if not rows:
            self.ctx.toast("請先勾選傳票", True)
            return

        def go():
            r = self.ctx.guard(fn, [v["id"] for v in rows])
            if r:
                done, errs = r
                if errs:
                    self.ctx.toast("完成 %d 張；%d 張未處理：%s" % (len(done), len(errs), "；".join(errs[:3])), True)
                else:
                    self.ctx.toast("完成 %d 張傳票" % len(done))
            self.load()
        if confirm_word:
            self.ctx.confirm(confirm_word, "確定要%s勾選的 %d 張傳票嗎？" % (confirm_word, len(rows)), go, yes=confirm_word)
        else:
            go()


# ====================================================================== 列印
def print_voucher(ctx, v):
    b = ctx.books
    names = b.account_names()
    rows = [dict(acct="%s %s" % (ln["account"], names.get(ln["account"], "")), summary=ln["summary"] +
                 ("（%s）" % ln["partner"] if ln["partner"] else ""), debit=T.amt(ln["debit"], True),
                 credit=T.amt(ln["credit"], True)) for ln in v["lines"]]
    rows.append(dict(acct="合　　計", summary="", debit=T.amt(v["total"]), credit=T.amt(v["total"]), total=1))
    body = ("<div class='meta'><span>傳票號碼：%s</span><span>日期：%s</span><span>附件：%s 張</span></div>"
            % (v["v_no"], rocdate.show(v["v_date"]), v["attachments"]))
    body += printing.table([("acct", "會計科目", False), ("summary", "摘要", False), ("debit", "借方金額", True),
                            ("credit", "貸方金額", True)], rows, lambda r: "total" if r.get("total") else "")
    if v["memo"]:
        body += "<p>備註：%s</p>" % printing.esc(v["memo"])
    body += ("<div class='sign'><div>核准</div><div>審核 %s</div><div>記帳 %s</div><div>製單 %s</div></div>"
             % (printing.esc(v["approved_by"]), printing.esc(v["posted_by"]), printing.esc(v["created_by"])))
    printing.write_and_open(printing.page(b.company().get("name", ""), V_TYPE_NAMES[v["v_type"]],
                                          "狀態：%s" % STATUS[v["status"]], body), "voucher_" + v["v_no"])
