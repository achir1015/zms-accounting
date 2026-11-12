"""基本資料：會計科目、常用分錄、通用基本資料（部門、員工、客戶、廠商、專案、幣別、摘要片語）。"""
from decimal import Decimal

import flet as ft

from .. import rocdate
from ..books import CF_SECTIONS, MASTERS, PARTNER_KINDS
from . import theme as T

MASTER_STYLE = {"departments": (ft.Icons.APARTMENT, "sky"), "employees": (ft.Icons.BADGE, "violet"),
                "customers": (ft.Icons.STOREFRONT, "green"), "vendors": (ft.Icons.LOCAL_SHIPPING, "orange"),
                "projects": (ft.Icons.WORK_OUTLINE, "teal"), "currencies": (ft.Icons.CURRENCY_EXCHANGE, "amber"),
                "phrases": (ft.Icons.SHORT_TEXT, "pink")}
CATS = [("", "全部"), ("1", "資產"), ("2", "負債"), ("3", "權益"), ("4", "收入"), ("5", "成本"), ("6", "費用"),
        ("7", "營業外"), ("8", "所得稅")]


def form_header(icon, tone, title, sub=""):
    return ft.Row([T.icon_tile(icon, tone, 40), ft.Column([ft.Text(title, size=17, weight=ft.FontWeight.W_700),
                                                          T.muted(sub, 12)] if sub else
                                                         [ft.Text(title, size=17, weight=ft.FontWeight.W_700)],
                                                         spacing=0)], spacing=12)


# ====================================================================== 通用基本資料
class MasterList(ft.Row):
    def __init__(self, ctx, name):
        self.ctx, self.name = ctx, name
        self.m = MASTERS[name]
        self.editable = ctx.books.can("BAS", 2)
        icon, tone = MASTER_STYLE.get(name, (ft.Icons.FOLDER, "blue"))
        self.icon, self.tone = icon, tone
        self.search = T.field("搜尋", "", width=240, prefix_icon=ft.Icons.SEARCH, on_change=lambda e: self.filter())
        self.grid = T.Grid([(k if typ != "dept" else "dept_show", t, typ if typ != "dept" else "s", min(w, 220))
                            for k, t, typ, w in self.m["fields"]],
                           on_pick=self.pick)
        self.rows = []
        self.current = None
        self.inputs = {}
        self.form = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        tools = [self.search, ctx.export_button(self.grid, self.m["title"])]
        if self.editable:
            tools += [ft.PopupMenuButton(
                content=ft.Container(ft.Row([ft.Icon(ft.Icons.UPLOAD_FILE, size=18, color=T.PRIMARY),
                                             ft.Text("匯入 Excel", color=T.PRIMARY, size=14,
                                                     weight=ft.FontWeight.W_500)], spacing=8, tight=True),
                                     border=ft.Border.all(1, "#C7D4E8"), border_radius=10,
                                     padding=ft.Padding.symmetric(horizontal=16, vertical=10)),
                tooltip="下載範本或匯入名冊",
                items=[ft.PopupMenuItem("下載範本（CSV）", icon=ft.Icons.DOWNLOAD, on_click=self.template),
                       ft.PopupMenuItem("選擇檔案匯入", icon=ft.Icons.UPLOAD_FILE, on_click=self.do_import)])]
        left = ft.Column([
            T.page_header(icon, self.m["title"], "可用 Excel 整理後匯入", tone, tools),
            self.grid], expand=True, spacing=12)
        super().__init__([left, T.card(self.form, width=400, padding=18)], expand=True, spacing=14,
                         vertical_alignment=ft.CrossAxisAlignment.START)
        self.reload()
        self.edit(None, refresh=False)

    def reload(self):
        self.rows = self.ctx.books.master_rows(self.name)
        if self.name == "employees":
            depts = dict(self.ctx.books.options("departments"))
            for r in self.rows:
                r["dept_show"] = depts.get(r["dept"], r["dept"])
        self.filter(refresh=False)

    def filter(self, refresh=True):
        q = (self.search.value or "").strip().lower()
        rows = [r for r in self.rows if not q or any(q in str(v).lower() for v in r.values())]
        self.grid.set_rows(rows)
        if refresh:
            self.update()

    def pick(self, r):
        self.edit(r)

    async def template(self, e):
        from .. import csvio
        path = await self.ctx.save_as("%s範本.csv" % self.m["title"], "csv")
        if path:
            csvio.master_template(self.name, path)
            self.ctx.toast("已存範本：用 Excel 開啟填寫後存檔，再按「選擇檔案匯入」")
            T.open_file(path)

    async def do_import(self, e):
        from .. import csvio
        files = await ft.FilePicker().pick_files(dialog_title="選擇%s名冊（CSV）" % self.m["title"],
                                                 allowed_extensions=["csv"])
        if not files:
            return
        r = self.ctx.guard(csvio.import_masters, self.ctx.books, self.name, files[0].path)
        if not r:
            return
        ok, errs = r
        self.reload()
        self.update()
        msg = ft.Column([ft.Text("成功匯入（新增或更新）%d 筆。" % ok, size=15, color=T.SUCCESS,
                                 weight=ft.FontWeight.W_600)] +
                        ([ft.Text("以下 %d 列未匯入：" % len(errs), color=T.DANGER)] +
                         [ft.Text(x, size=12, selectable=True) for x in errs[:30]] if errs else []),
                        tight=True, scroll=ft.ScrollMode.AUTO, height=None if len(errs) < 10 else 360)
        self.ctx.dialog("匯入結果", msg, [T.btn("確定", on_click=lambda e: self.ctx.close())],
                        icon=ft.Icons.UPLOAD_FILE, tone="green" if not errs else "amber", width=520)

    def edit(self, r, refresh=True):
        self.current = r
        self.inputs = {}
        ctrls = []
        for key, title, typ, w in self.m["fields"]:
            v = (r or {}).get(key)
            if typ == "b":
                c = T.switch(title, True if r is None else v)
            elif typ == "dept":
                c = T.dropdown(title, self.ctx.books.options("departments"), v or "", blank="（無）",
                               filterable=False)
            elif typ == "d":
                c = T.field(title, rocdate.show(v) if v else "", hint_text="115/01/01")
            elif typ == "n":
                c = T.field(title, "" if v is None else (str(Decimal(v).normalize()) if key == "rate" else T.amt(v)),
                            text_align=ft.TextAlign.RIGHT)
            else:
                c = T.field(title, v or "", read_only=bool(r) and key == self.m["key"] and key != "id")
            c.disabled = not self.editable
            self.inputs[key] = c
            ctrls.append(c)
        acts = []
        if self.editable:
            acts = [T.btn("儲存", ft.Icons.SAVE, lambda e: self.save()),
                    T.btn("新增", ft.Icons.ADD, lambda e: self.edit(None), kind="outline")]
            if r:
                acts.append(T.btn("刪除", ft.Icons.DELETE_OUTLINE, lambda e: self.delete(), kind="danger"))
        self.form.controls = [form_header(self.icon, self.tone, "修改%s" % self.m["title"] if r else
                                          "新增%s" % self.m["title"], "" if self.editable else "您只有查詢權限"),
                              *ctrls, ft.Row(acts, wrap=True, spacing=8)]
        if refresh:
            self.update()

    def save(self):
        row = {k: c.value for k, c in self.inputs.items()}
        if self.current and self.name == "phrases":
            row["id"] = self.current["id"]
        if self.ctx.guard(self.ctx.books.save_master, self.name, row, self.current is None, ok="已儲存"):
            self.reload()
            self.edit(None)

    def delete(self):
        key = self.current[self.m["key"]]
        label = self.current.get("name") or self.current.get("text") or key
        self.ctx.confirm("刪除%s" % self.m["title"], "確定要刪除「%s」嗎？" % label,
                         lambda: self.ctx.guard(self.ctx.books.delete_master, self.name, key, ok="已刪除")
                         and (self.reload(), self.edit(None)), yes="刪除")


# ====================================================================== 會計科目
class Accounts(ft.Row):
    def __init__(self, ctx):
        self.ctx = ctx
        self.editable = ctx.books.can("BAS", 2)
        self.cat = ""
        self.cats = ft.Row(spacing=6, wrap=True)
        self.search = T.field("搜尋代號或名稱", "", width=220, prefix_icon=ft.Icons.SEARCH,
                              on_change=lambda e: self.filter())
        self.grid = T.Grid([("show_name", "科目", "s", 280), ("nature_t", "餘額", "s", 40), ("flags", "設定", "s", 230),
                            ("active", "使用", "b", 40)], on_pick=self.edit, row_style=self.style)
        self.form = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        self.all = []
        left = ft.Column([
            T.page_header(ft.Icons.ACCOUNT_TREE, "會計科目", "四碼制：1 大類 → 2 中類 → 3 小類 → 4 明細（可記帳）",
                          "sky", [self.search, ctx.export_button(self.grid, "會計科目表")]),
            self.cats, self.grid], expand=True, spacing=10)
        super().__init__([left, T.card(self.form, width=420, padding=18)], expand=True, spacing=14,
                         vertical_alignment=ft.CrossAxisAlignment.START)
        self.reload()
        self.edit(None, refresh=False)

    @staticmethod
    def style(r):
        if r["level"] == 1:
            return {"weight": ft.FontWeight.W_800, "color": T.PRIMARY}
        if r["level"] == 2:
            return {"weight": ft.FontWeight.W_700}
        if r["level"] == 3:
            return {"weight": ft.FontWeight.W_600, "color": "#475569"}
        return None

    def reload(self):
        self.all = self.ctx.books.accounts()
        for a in self.all:
            a["show_name"] = "%s%s　%s" % ("　" * (a["level"] - 1), a["code"], a["name"])
            a["nature_t"] = "借" if a["nature"] == "D" else "貸"
            f = []
            if a["is_cash"]:
                f.append("現金")
            if a["partner_kind"]:
                f.append("往來:" + PARTNER_KINDS[a["partner_kind"]])
            if a["currency"]:
                f.append("外幣:" + a["currency"])
            if a["level"] == 4:
                f.append(CF_SECTIONS.get(a["cf_section"], ""))
            a["flags"] = "、".join(f)
        self.filter(refresh=False)

    def filter(self, refresh=True):
        self.cats.controls = [ft.Container(ft.Text(t, size=13, weight=ft.FontWeight.W_600,
                                                   color=ft.Colors.WHITE if k == self.cat else T.PRIMARY),
                                           bgcolor=T.PRIMARY if k == self.cat else "#E3EDFF", border_radius=20,
                                           padding=ft.Padding.symmetric(horizontal=14, vertical=6),
                                           on_click=lambda e, k=k: self.set_cat(k), ink=True) for k, t in CATS]
        q = (self.search.value or "").strip()
        rows = [a for a in self.all if (not self.cat or a["code"].startswith(self.cat)) and
                (not q or a["code"].startswith(q) or q in a["name"])]
        self.grid.set_rows(rows)
        if refresh:
            self.update()

    def set_cat(self, k):
        self.cat = k
        self.filter()

    def edit(self, a, refresh=True, parent=None):
        b = self.ctx.books
        new = a is None
        a = a or {}
        self.f_code = T.field("科目代號（1～4 碼數字）", a.get("code") or (parent or ""), read_only=not new)
        self.f_name = T.field("科目名稱", a.get("name", ""))
        self.f_nature = ft.RadioGroup(value=a.get("nature") or "D", content=ft.Row([
            ft.Radio(value="D", label="借方餘額"), ft.Radio(value="C", label="貸方餘額")]))
        self.f_cash = T.switch("現金及約當現金（列入現金簿）", a.get("is_cash"))
        self.f_cf = T.dropdown("現金流量歸類", list(CF_SECTIONS.items()), a.get("cf_section") or "OP",
                               filterable=False)
        self.f_pk = T.dropdown("往來對象", list(PARTNER_KINDS.items()), a.get("partner_kind") or "", blank="不需要",
                               filterable=False)
        self.f_dept = T.switch("記帳時必須選部門", a.get("need_dept"))
        self.f_cur = T.dropdown("外幣科目", [(r["code"], "%s %s" % (r["code"], r["name"]))
                                         for r in b.master_rows("currencies") if r["code"] != "TWD"],
                                a.get("currency") or "", blank="本國幣", filterable=False)
        self.f_active = T.switch("使用中", True if new else a.get("active"))
        self.f_memo = T.field("備註", a.get("memo", ""))
        for c in (self.f_code, self.f_name, self.f_nature, self.f_cash, self.f_cf, self.f_pk, self.f_dept,
                  self.f_cur, self.f_active, self.f_memo):
            c.disabled = not self.editable or (c is self.f_code and not new)
        acts = []
        if self.editable:
            acts = [T.btn("儲存", ft.Icons.SAVE, lambda e: self.save(new))]
            if not new and len(a["code"]) < 4:
                acts.append(T.btn("新增子科目", ft.Icons.ADD, lambda e: self.edit(None, parent=a["code"]),
                                  kind="outline"))
            acts.append(T.btn("新增", ft.Icons.ADD, lambda e: self.edit(None), kind="ghost"))
            if not new:
                acts.append(T.btn("刪除", ft.Icons.DELETE_OUTLINE, lambda e: self.delete(a), kind="danger"))
        lvl = {1: "大類", 2: "中類", 3: "小類", 4: "明細科目"}.get(len(a.get("code", "")), "")
        self.form.controls = [
            form_header(ft.Icons.ACCOUNT_TREE, "sky", "新增科目" if new else "%s %s" % (a["code"], a["name"]),
                        lvl if not new else "上層科目要先存在"),
            self.f_code, self.f_name, T.muted("正常餘額方向", 12), self.f_nature, self.f_cash, self.f_cf, self.f_pk,
            self.f_dept, self.f_cur, self.f_active, self.f_memo, ft.Row(acts, wrap=True, spacing=8)]
        if refresh:
            self.update()

    def save(self, new):
        a = dict(code=self.f_code.value, name=self.f_name.value, nature=self.f_nature.value,
                 is_cash=self.f_cash.value, cf_section=self.f_cf.value, partner_kind=self.f_pk.value or "",
                 need_dept=self.f_dept.value, currency=self.f_cur.value or "", active=self.f_active.value,
                 memo=self.f_memo.value)
        if self.ctx.guard(self.ctx.books.save_account, a, new, ok="科目已儲存"):
            self.reload()
            self.edit(self.ctx.books.account(a["code"].strip()) | {"show_name": ""})

    def delete(self, a):
        self.ctx.confirm("刪除科目", "確定要刪除 %s %s 嗎？" % (a["code"], a["name"]),
                         lambda: self.ctx.guard(self.ctx.books.delete_account, a["code"], ok="已刪除")
                         and (self.reload(), self.edit(None)), yes="刪除")


# ====================================================================== 常用分錄
class Templates(ft.Row):
    def __init__(self, ctx):
        self.ctx = ctx
        self.editable = ctx.books.can("BAS", 2)
        self.list = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        self.editor = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        self.acct_opts = ctx.books.options("accounts")
        super().__init__([
            ft.Column([T.page_header(ft.Icons.BOOKMARKS, "常用分錄", "經常發生的交易，一鍵套用", "sky"),
                       T.card(self.list, expand=True, padding=12)], width=420, spacing=12),
            T.card(self.editor, expand=True, padding=18)], expand=True, spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.START)
        self.reload()
        self.edit(None, refresh=False)

    def reload(self):
        self.tpls = self.ctx.books.templates()
        tone = {"收": "green", "支": "rose", "轉": "blue", "開帳": "violet", "調整": "orange"}
        self.list.controls = [ft.Container(ft.Row([
            T.icon_tile(ft.Icons.BOOKMARK, tone.get(t["v_type"], "blue"), 36),
            ft.Column([ft.Text(t["name"], size=14, weight=ft.FontWeight.W_600),
                       T.muted("%s傳票・%d 行%s" % (t["v_type"], len(t["lines"]), "・" + t["memo"] if t["memo"] else ""),
                               11)], spacing=0, expand=True)], spacing=10),
            padding=10, border_radius=12, bgcolor="#F7F9FC", ink=True, on_click=lambda e, t=t: self.edit(t))
            for t in self.tpls] or [T.empty_state(ft.Icons.BOOKMARKS, "尚無常用分錄")]

    def edit(self, t, refresh=True):
        self.cur = t
        t = t or {"name": "", "v_type": "轉", "memo": "", "lines": [{}, {}]}
        self.name = T.field("分錄名稱", t["name"])
        self.vtype = T.dropdown("傳票類別", [("收", "收入"), ("支", "支出"), ("轉", "轉帳"), ("調整", "調整")],
                                t["v_type"], width=150, filterable=False)
        self.memo = T.field("說明（套用時顯示）", t["memo"])
        self.rows = ft.Column(spacing=6)
        for ln in t["lines"]:
            self.add_row(ln)
        acts = []
        if self.editable:
            acts = [T.btn("儲存", ft.Icons.SAVE, lambda e: self.save()),
                    T.btn("新增分錄", ft.Icons.ADD, lambda e: self.edit(None), kind="outline")]
            if self.cur:
                acts.append(T.btn("刪除", ft.Icons.DELETE_OUTLINE, lambda e: self.delete(), kind="danger"))
        self.editor.controls = [
            form_header(ft.Icons.BOOKMARKS, "sky", "修改常用分錄" if self.cur else "新增常用分錄",
                        "比率：套用時「輸入金額 × 比率」＝該行金額；0 代表套用後自行輸入"),
            ft.Row([self.name, self.vtype]), self.memo,
            ft.Row([T.muted("科目", 12, width=280), T.muted("借貸", 12, width=90), T.muted("摘要", 12, width=200),
                    T.muted("比率", 12, width=90)]),
            self.rows,
            T.btn("新增一行", ft.Icons.ADD, lambda e: (self.add_row({}), self.update()), kind="ghost"),
            ft.Row(acts, spacing=8)]
        if refresh:
            self.update()

    def add_row(self, ln):
        acct = T.dropdown("", self.acct_opts, ln.get("account"), width=280)
        side = T.dropdown("", [("D", "借"), ("C", "貸")], ln.get("side") or "D", width=90, filterable=False)
        summ = T.field("", ln.get("summary", ""), width=200)
        ratio = T.field("", str(Decimal(str(ln.get("ratio") or 0)).normalize()), width=90,
                        text_align=ft.TextAlign.RIGHT)
        row = ft.Row([acct, side, summ, ratio], spacing=8)
        row.controls.append(ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color="#E06666",
                                          on_click=lambda e, r=row: (self.rows.controls.remove(r), self.update())))
        row.data = (acct, side, summ, ratio)
        self.rows.controls.append(row)

    def save(self):
        lines = [dict(account=a.value, side=s.value, summary=m.value, ratio=r.value or 0)
                 for a, s, m, r in (row.data for row in self.rows.controls)]
        try:
            for ln in lines:
                Decimal(str(ln["ratio"]))
        except Exception:
            self.ctx.toast("比率要是數字", True)
            return
        tid = self.ctx.guard(self.ctx.books.save_template, self.cur["id"] if self.cur else None, self.name.value,
                             self.vtype.value, self.memo.value, lines, ok="已儲存")
        if tid:
            self.reload()
            self.edit(next((t for t in self.tpls if t["id"] == tid), None))

    def delete(self):
        self.ctx.confirm("刪除常用分錄", "確定要刪除「%s」嗎？" % self.cur["name"],
                         lambda: self.ctx.guard(self.ctx.books.delete_template, self.cur["id"], ok="已刪除")
                         and (self.reload(), self.edit(None)), yes="刪除")
