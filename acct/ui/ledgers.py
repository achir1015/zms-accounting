"""帳簿查詢：日記簿、明細分類帳、總分類帳、現金簿、往來明細。"""
from decimal import Decimal

import flet as ft

from .. import printing, rocdate
from ..books import PARTNER_KINDS
from . import theme as T


class ReportBase(ft.Column):
    """報表畫面共用：標題、條件列（起訖日、含未過帳）、查詢／列印／匯出、結果區。"""
    icon, title, subtitle, tone = ft.Icons.MENU_BOOK, "", "", "amber"
    period = True          # True＝起訖日；False＝只有截止日

    def __init__(self, ctx):
        self.ctx = ctx
        today = rocdate.today()
        self.start = T.date_field("起日", today.replace(month=1, day=1), width=145)
        self.end = T.date_field("迄日" if self.period else "截止日", today, width=145)
        self.unposted = ft.Checkbox(label="含未過帳（試算參考）", value=False)
        self.result = ft.Container(expand=True)
        self.grid = None
        filters = ([self.start] if self.period else []) + [self.end] + self.extra_filters() + [self.unposted]
        # 勾選框在可換行的列裡會佔滿整行，包一層固定寬度
        filters = [ft.Container(c, width=200) if isinstance(c, ft.Checkbox) else c for c in filters]
        self.tools = ft.Row([T.btn("查詢", ft.Icons.SEARCH, lambda e: self.run()),
                             T.btn("列印", ft.Icons.PRINT, lambda e: self.print_(), kind="outline")], spacing=8)
        super().__init__([
            T.page_header(self.icon, self.title, self.subtitle, self.tone, self.header_actions()),
            T.card(ft.Row(filters + [self.tools], wrap=True, spacing=12, run_spacing=10,
                          vertical_alignment=ft.CrossAxisAlignment.CENTER), padding=14),
            self.result], spacing=12, expand=True)
        self.run(refresh=False)

    def extra_filters(self):
        return []

    def header_actions(self):
        return []

    def dates(self):
        return rocdate.read(self.start.value), rocdate.read(self.end.value)

    def run(self, refresh=True):
        try:
            self.build()
        except ValueError as e:
            self.ctx.toast(str(e), True)
            return
        if self.grid is not None and len(self.tools.controls) == 2:
            self.tools.controls.append(self.ctx.export_button(self.grid, self.title))
        if refresh:
            self.update()

    def build(self):
        raise NotImplementedError

    def subtitle_text(self):
        if self.period:
            return "%s 至 %s" % (self.start.value, self.end.value)
        return "截至 %s" % self.end.value

    def print_(self):
        if not self.grid or not self.grid.data_rows:
            self.ctx.toast("沒有資料可以列印", True)
            return
        cols = [(c[0], c[1], c[2] in ("n", "nz")) for c in self.grid.cols]
        rows = [{c[0]: T.show(r.get(c[0]), "" if c[2] in ("status", "vtype") else c[2]) for c in self.grid.cols}
                | {"_cls": r.get("_cls", "")} for r in self.grid.data_rows]
        html = printing.page(self.ctx.books.company().get("name", ""), self.title, self.subtitle_text(),
                             printing.table(cols, rows, lambda r: r.get("_cls", "")))
        printing.write_and_open(html, self.title)


def bold_rows(r):
    if r.get("_cls") in ("total", "sub"):
        return {"weight": ft.FontWeight.W_800, "color": T.PRIMARY}
    if r.get("_cls") == "head":
        return {"weight": ft.FontWeight.W_700}
    return None


class Journal(ReportBase):
    icon, title, subtitle, tone = ft.Icons.MENU_BOOK, "日記簿", "依日期與傳票號碼列出每一筆分錄", "amber"

    def build(self):
        s, e = self.dates()
        self.start.value = rocdate.show(s)
        if s.month == e.month and s.year == e.year:
            pass
        rows = self.ctx.reports.journal(s, e, self.unposted.value)
        last = None
        for r in rows:
            if r["v_no"] == last:
                r["v_no_show"], r["date_show"] = "", None
            else:
                r["v_no_show"], r["date_show"] = r["v_no"], r["v_date"]
            last = r["v_no"]
            r["acct"] = "%s %s" % (r["account"], r["account_name"] or "")
        self.grid = T.Grid([("date_show", "日期", "d", 82), ("v_no_show", "傳票號碼", "s", 96),
                            ("acct", "會計科目", "s", 200), ("summary", "摘要", "s", 240),
                            ("debit", "借方", "nz", 110), ("credit", "貸方", "nz", 110), ("partner", "往來", "s", 80)],
                           totals=("debit", "credit"))
        self.grid.set_rows(rows)
        self.result.content = self.grid


class Ledger(ReportBase):
    icon, title, subtitle, tone = ft.Icons.LIST_ALT, "明細分類帳", "科目期初、逐筆交易與累計餘額", "amber"

    def __init__(self, ctx, account="1113"):
        self._acct0 = account
        super().__init__(ctx)

    def extra_filters(self):
        b = self.ctx.books
        opts = [(a["code"], "%s %s" % (a["code"], a["name"])) for a in b.accounts(active_only=True)]
        self.account = T.dropdown("科目（可選統制科目）", opts, self._acct0, width=280)
        self.pkind = T.dropdown("往來類別", list(PARTNER_KINDS.items()), "", width=120, blank="不限", filterable=False,
                                on_select=self.on_kind)
        self.partner = T.dropdown("往來對象", [], "", width=200, blank="全部")
        return [self.account, self.pkind, self.partner]

    def on_kind(self, e):
        kind = self.pkind.value
        src = {"C": "customers", "V": "vendors", "E": "employees"}.get(kind)
        self.partner.options = [ft.DropdownOption(key="", text="全部")] + (
            [ft.DropdownOption(key=k, text=t) for k, t in self.ctx.books.options(src)] if src else [])
        self.partner.value = ""
        self.update()

    def build(self):
        s, e = self.dates()
        code = self.account.value or "1113"
        led = self.ctx.reports.ledger(code, s, e, self.unposted.value, self.pkind.value or "",
                                      self.partner.value or "")
        rows = [dict(v_date=s, summary="期初餘額", balance=led["opening"], _cls="head")]
        for r in led["rows"]:
            r["acct"] = "%s %s" % (r["account"], r["account_name"] or "")
            rows.append(r)
        rows.append(dict(summary="本期合計", debit=led["debit"], credit=led["credit"], balance=led["closing"],
                         _cls="total"))
        cols = [("v_date", "日期", "d", 82), ("v_no", "傳票號碼", "s", 96)]
        if len(code) < 4:
            cols.append(("acct", "科目", "s", 160))
        cols += [("summary", "摘要", "s", 240), ("partner", "往來", "s", 80), ("debit", "借方", "nz", 110),
                 ("credit", "貸方", "nz", 110), ("balance", "餘額", "n", 120)]
        self.grid = T.Grid(cols, row_style=bold_rows)
        self.grid.set_rows(rows)
        a = self.ctx.books.account(code)
        kpis = T.kpis([T.kpi("期初餘額", T.amt(led["opening"]), ft.Icons.FLAG, "slate"),
                       T.kpi("本期借方", T.amt(led["debit"]), ft.Icons.ARROW_DOWNWARD, "blue"),
                       T.kpi("本期貸方", T.amt(led["credit"]), ft.Icons.ARROW_UPWARD, "teal"),
                       T.kpi("期末餘額", T.amt(led["closing"]), ft.Icons.ACCOUNT_BALANCE_WALLET, "amber",
                             sub="%s 餘額" % ("借" if (a or {}).get("nature", "D") == "D" else "貸"))], spacing=12)
        self.result.content = ft.Column([kpis, self.grid], spacing=12, expand=True)

    def subtitle_text(self):
        a = self.ctx.books.account(self.account.value or "")
        return "%s %s　%s" % (self.account.value, a["name"] if a else "", super().subtitle_text())


class GeneralLedger(ReportBase):
    icon, title, subtitle, tone = ft.Icons.ACCOUNT_TREE, "總分類帳", "各科目期初、本期借貸與期末餘額", "amber"

    def extra_filters(self):
        self.level = T.dropdown("彙總層級", [(4, "明細科目（4 碼）"), (3, "小類（3 碼）"), (2, "中類（2 碼）"),
                                         (1, "大類（1 碼）")], 4, width=180, filterable=False)
        return [self.level]

    def build(self):
        s, e = self.dates()
        rows = self.ctx.reports.general_ledger(s, e, int(self.level.value or 4), self.unposted.value)
        self.grid = T.Grid([("code", "代號", "s", 60), ("name", "科目名稱", "s", 220), ("opening", "期初餘額", "n", 130),
                            ("debit", "本期借方", "nz", 130), ("credit", "本期貸方", "nz", 130),
                            ("closing", "期末餘額", "n", 130)], totals=("debit", "credit"),
                           on_pick=lambda r: self.ctx.app.go("ledger", account=r["code"]))
        self.grid.set_rows(rows)
        self.result.content = ft.Column([T.muted("點選科目可以查看明細分類帳", 12), self.grid], spacing=6, expand=True)


class CashBook(ReportBase):
    icon, title, subtitle, tone = ft.Icons.PAYMENTS, "現金簿", "現金、零用金、銀行存款的收支與餘額", "teal"

    def build(self):
        s, e = self.dates()
        books = self.ctx.reports.cash_book(s, e, self.unposted.value)
        rows = []
        cards = []
        for bk in books:
            rows.append(dict(summary="【%s %s】期初餘額" % (bk["code"], bk["name"]), balance=bk["opening"], _cls="head"))
            for r in bk["rows"]:
                r["income"], r["expense"] = r["debit"], r["credit"]
                rows.append(r)
            rows.append(dict(summary="%s 小計" % bk["name"], income=bk["debit"], expense=bk["credit"],
                             balance=bk["closing"], _cls="sub"))
            cards.append(T.kpi(bk["name"], T.amt(bk["closing"]), ft.Icons.ACCOUNT_BALANCE_WALLET, "teal",
                               sub="收 %s　支 %s" % (T.amt(bk["debit"]), T.amt(bk["credit"]))))
        self.grid = T.Grid([("v_date", "日期", "d", 82), ("v_no", "傳票號碼", "s", 96), ("summary", "摘要", "s", 260),
                            ("other", "對方科目", "s", 170), ("income", "收入", "nz", 110), ("expense", "支出", "nz", 110),
                            ("balance", "餘額", "n", 120)], row_style=bold_rows)
        self.grid.set_rows(rows)
        self.result.content = ft.Column([T.kpis(cards[:4], spacing=12), self.grid], spacing=12, expand=True)


class PartnerLedger(ReportBase):
    icon, title, subtitle, tone = ft.Icons.HANDSHAKE, "往來明細", "客戶應收、廠商應付、員工借支餘額", "sky"
    period = False

    def extra_filters(self):
        self.kind = T.dropdown("往來類別", list(PARTNER_KINDS.items()), "C", width=140, filterable=False)
        return [self.kind]

    def build(self):
        d = rocdate.read(self.end.value)
        rows = self.ctx.reports.partner_balances(self.kind.value or "C", d, self.unposted.value)
        for r in rows:
            r["acct"] = "%s %s" % (r["account"], r["account_name"])
            r["debit"], r["credit"] = Decimal(r["d"] or 0), Decimal(r["c"] or 0)
        self.grid = T.Grid([("code", "代號", "s", 90), ("name", "名稱", "s", 200), ("acct", "科目", "s", 180),
                            ("debit", "借方累計", "n", 120), ("credit", "貸方累計", "n", 120),
                            ("balance", "餘額", "n", 130)], totals=("balance",),
                           on_pick=lambda r: self.drill(r))
        self.grid.set_rows(rows)
        self.result.content = ft.Column([T.muted("點選一列可查看該往來對象的明細分類帳", 12), self.grid], spacing=6,
                                        expand=True)

    def drill(self, r):
        app = self.ctx.app
        app.go("ledger", account=r["account"])
        led = app.body.content
        led.pkind.value = self.kind.value
        led.on_kind(None)
        led.partner.value = r["code"]
        led.run()
