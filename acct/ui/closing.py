"""期末作業：期間關帳、外幣現值調整、年度結帳、預算編列、比率公式。"""
from decimal import Decimal

import flet as ft

from .. import rocdate
from ..books import money
from . import theme as T


def year_picker(value, on_select, span=(5, 1)):
    y = rocdate.today().year
    return T.dropdown("年度", [(i, "%d 年" % (i - 1911)) for i in range(y - span[0], y + span[1] + 1)], value,
                      width=130, on_select=on_select, filterable=False)


# ====================================================================== 期間關帳
class Periods(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.year = rocdate.today().year
        self.grid = ft.Row(wrap=True, spacing=14, run_spacing=14)
        super().__init__([
            T.page_header(ft.Icons.LOCK_CLOCK, "期間關帳", "關帳後該月份不能新增或修改傳票", "orange",
                          [year_picker(self.year, self.on_year)]),
            ft.Container(self.grid, expand=True)], spacing=14, expand=True, scroll=ft.ScrollMode.AUTO)
        self.load(refresh=False)

    def on_year(self, e):
        self.year = int(e.control.value)
        self.load()

    def load(self, refresh=True):
        tiles = []
        for p in self.ctx.books.periods(self.year):
            closed = bool(p["closed"])
            tone = "slate" if closed else ("amber" if p["pending"] else "green")
            bg, fg = T.TONES[tone]
            status = "已關帳" if closed else ("%d 張未過帳" % p["pending"] if p["pending"] else "可關帳")
            tiles.append(ft.Container(ft.Column([
                ft.Row([T.icon_tile(ft.Icons.LOCK if closed else ft.Icons.LOCK_OPEN, tone, 44),
                        ft.Column([ft.Text("%d 月" % int(p["ym"][4:]), size=20, weight=ft.FontWeight.W_800),
                                   T.muted("%d 年" % (self.year - 1911), 12)], spacing=0)], spacing=12),
                ft.Text(status, size=13, color=fg, weight=ft.FontWeight.W_700),
                T.muted("傳票 %d 張%s" % (p["vouchers"], "　%s 關帳" % p["closed_by"] if closed else ""), 12),
                T.btn("重新開帳" if closed else "關帳", ft.Icons.LOCK_OPEN if closed else ft.Icons.LOCK,
                      lambda e, ym=p["ym"], c=closed: self.toggle(ym, c), kind="outline" if closed else "primary")],
                spacing=8), width=210, padding=16, bgcolor=T.CARD, border_radius=18,
                border=ft.Border.all(1.5, fg if not closed else T.LINE)))
        self.grid.controls = tiles
        if refresh:
            self.update()

    def toggle(self, ym, closed):
        def go():
            if self.ctx.guard(self.ctx.books.close_period, ym, not closed,
                              ok="%s 已%s" % (rocdate.ym_show(ym), "重新開帳" if closed else "關帳")):
                self.load()
        if closed:
            self.ctx.confirm("重新開帳", "重新開帳後 %s 的傳票可以再異動，確定嗎？" % rocdate.ym_show(ym), go,
                             yes="重新開帳")
        else:
            go()


# ====================================================================== 外幣現值調整
class Revaluation(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.date = T.date_field("評價日", rocdate.month_last(rocdate.today()), width=160)
        self.grid = T.Grid([("code", "科目", "s", 60), ("name", "名稱", "s", 160), ("currency", "幣別", "s", 50),
                            ("fx", "外幣餘額", "n", 120), ("rate", "最新匯率", "s", 90), ("value", "現值", "n", 130),
                            ("book", "帳面金額", "n", 130), ("diff", "調整差額", "n", 120)],
                           empty="沒有外幣科目（可在會計科目設定外幣）")
        super().__init__([
            T.page_header(ft.Icons.PRICE_CHANGE, "外幣現值調整", "以最新匯率重估外幣科目，差額列兌換損益", "orange"),
            T.card(ft.Row([self.date, T.btn("試算", ft.Icons.CALCULATE, lambda e: self.preview()),
                           T.btn("更新匯率", ft.Icons.CURRENCY_EXCHANGE, lambda e: ctx.app.go("currencies"),
                                 kind="outline"),
                           ft.Container(expand=True),
                           T.btn("產生調整傳票", ft.Icons.NOTE_ADD, lambda e: self.make(), kind="accent")]),
                   padding=14),
            self.grid], spacing=12, expand=True)
        self.preview(refresh=False)

    def preview(self, refresh=True):
        try:
            rows = self.ctx.books.revaluation_preview(self.date.value)
        except ValueError as e:
            self.ctx.toast(str(e), True)
            return
        for r in rows:
            r["rate"] = str(r["rate"].normalize())
        self.grid.set_rows(rows)
        if refresh:
            self.update()

    def make(self):
        vid = self.ctx.guard(self.ctx.books.revaluation_voucher, self.date.value)
        if vid:
            v = self.ctx.books.voucher(vid)
            self.ctx.toast("已產生調整傳票 %s，請到審核過帳處理" % v["v_no"])
            self.ctx.app.go("voucher_entry", vid=vid)


# ====================================================================== 年度結帳
class YearEnd(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.year = rocdate.today().year - (1 if rocdate.today().month <= 3 else 0)
        self.info = ft.Column(spacing=10)
        super().__init__([
            T.page_header(ft.Icons.EVENT_AVAILABLE, "年度結帳", "損益科目結轉累積盈虧，新年度從零開始", "orange",
                          [year_picker(self.year, self.on_year)]),
            T.card(self.info, padding=22)], spacing=14, expand=True, scroll=ft.ScrollMode.AUTO)
        self.load(refresh=False)

    def on_year(self, e):
        self.year = int(e.control.value)
        self.load()

    def load(self, refresh=True):
        b, r = self.ctx.books, self.ctx.reports
        s, e = rocdate.fiscal_year_range(self.year, int(b.company().get("fiscal_start_month") or 1))
        closed = b.year_closed(self.year)
        inc = r.income_statement(s, e)
        pending = len(b.find_vouchers(s, e, status=0, limit=9999)) + len(b.find_vouchers(s, e, status=1, limit=9999))
        steps = [
            ("所有傳票都已過帳", pending == 0, "尚有 %d 張未過帳" % pending if pending else "完成"),
            ("已做期末調整（折舊、外幣、應計項目）", None, "請自行確認"),
            ("已核對試算表平衡", r.trial_balance(s, e)["balanced"], "平衡" if r.trial_balance(s, e)["balanced"]
             else "不平衡"),
        ]
        rows = []
        for t, ok, note in steps:
            icon = ft.Icons.CHECK_CIRCLE if ok else (ft.Icons.HELP_OUTLINE if ok is None else ft.Icons.CANCEL)
            color = T.SUCCESS if ok else (T.WARN if ok is None else T.DANGER)
            rows.append(ft.Row([ft.Icon(icon, color=color), ft.Text(t, size=14, expand=True), T.muted(note, 13)]))
        self.info.controls = [
            T.kpis([T.kpi("會計期間", "%s～%s" % (rocdate.show(s), rocdate.show(e)), ft.Icons.DATE_RANGE, "slate"),
                    T.kpi("本年度淨利（損）", T.amt(inc["net"]), ft.Icons.TRENDING_UP,
                          "green" if inc["net"] >= 0 else "rose"),
                    T.kpi("結帳狀態", "已結帳" if closed else "未結帳",
                          ft.Icons.LOCK if closed else ft.Icons.LOCK_OPEN, "slate" if closed else "amber")],
                   spacing=12),
            ft.Text("結帳前檢查", size=16, weight=ft.FontWeight.W_700), *rows, ft.Divider(),
            T.muted("執行後會在 %s 產生一張已過帳的「結帳傳票」，把收入、成本、費用科目的餘額結轉到 3351 累積盈虧。" %
                    rocdate.show(e), 13),
            ft.Row([T.btn("取消結帳", ft.Icons.UNDO, lambda e: self.reopen(), kind="outline") if closed else
                    T.btn("執行年度結帳", ft.Icons.EVENT_AVAILABLE, lambda e: self.close(), kind="accent")])]
        if refresh:
            self.update()

    def close(self):
        def go():
            r = self.ctx.guard(self.ctx.books.year_end_close, self.year)
            if r:
                self.ctx.toast("%d 年度結帳完成，本期%s %s" % (self.year - 1911, "淨利" if r[1] >= 0 else "淨損",
                                                        T.amt(abs(r[1]))))
                self.load()
        self.ctx.confirm("年度結帳", "確定要執行 %d 年度結帳嗎？" % (self.year - 1911), go, yes="結帳", danger=False)

    def reopen(self):
        self.ctx.confirm("取消結帳", "將刪除 %d 年度的結帳傳票，確定嗎？" % (self.year - 1911),
                         lambda: self.ctx.guard(self.ctx.books.year_end_reopen, self.year, ok="已取消結帳")
                         and self.load(), yes="取消結帳")


# ====================================================================== 預算編列
class BudgetEdit(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.year = rocdate.today().year
        self.dept = T.dropdown("部門", ctx.books.options("departments"), "", width=160, blank="全公司",
                               filterable=False, on_select=lambda e: self.load())
        self.table = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)
        self.fields = {}
        super().__init__([
            T.page_header(ft.Icons.SAVINGS, "預算編列", "輸入各損益科目全年預算，自動平均分配到 12 個月", "orange",
                          [year_picker(self.year, self.on_year, (1, 2)), self.dept,
                           T.btn("儲存預算", ft.Icons.SAVE, lambda e: self.save())]),
            T.card(self.table, expand=True, padding=14)], spacing=12, expand=True)
        self.load(refresh=False)

    def on_year(self, e):
        self.year = int(e.control.value)
        self.load()

    def load(self, refresh=True):
        accts = self.ctx.books.budget_sheet(self.year, self.dept.value or "")
        cur = {a["code"]: a["total"] for a in accts if a["total"]}
        self.fields = {}
        rows = [ft.Row([T.muted("科目", 12, width=280), T.muted("全年預算", 12, width=160),
                        T.muted("每月約", 12, width=120)])]
        for a in accts:
            per = ft.Text(T.amt((cur.get(a["code"]) or 0) / 12), width=120, size=13, color=T.MUTED)
            f = T.money_field("", cur.get(a["code"]), width=160)

            def changed(e, per=per):
                try:
                    per.value = T.amt((money(e.control.value) / 12).quantize(Decimal("1")))
                except Exception:
                    per.value = ""
                per.update()
            f.on_change = changed
            self.fields[a["code"]] = f
            rows.append(ft.Row([ft.Text("%s %s" % (a["code"], a["name"]), width=280, size=13), f, per]))
        self.table.controls = rows
        if refresh:
            self.update()

    def save(self):
        data = {k: (f.value or "0") for k, f in self.fields.items()}
        self.ctx.guard(self.ctx.books.save_budget, self.year, self.dept.value or "", data, ok="預算已儲存")


# ====================================================================== 比率公式
class RatioSetup(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.list = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        super().__init__([
            T.page_header(ft.Icons.FUNCTIONS, "財務比率公式", "B(代號)＝期末餘額　P(代號)＝期間發生額　NI＝本期淨利　EQ＝權益合計",
                          "orange", [T.btn("新增比率", ft.Icons.ADD, lambda e: self.edit(None))]),
            T.card(self.list, expand=True, padding=14)], spacing=12, expand=True)
        self.load(refresh=False)

    def load(self, refresh=True):
        rows = self.ctx.books.ratio_rows()
        self.list.controls = [ft.Container(ft.Row([
            T.icon_tile(ft.Icons.FUNCTIONS, "orange", 36),
            ft.Column([ft.Text("%s（%s）" % (r["name"], r["unit"]), size=14, weight=ft.FontWeight.W_700),
                       ft.Text(r["formula"], size=13, color=T.PRIMARY, font_family="Consolas"),
                       T.muted(r["memo"], 12)], spacing=1, expand=True),
            ft.IconButton(ft.Icons.EDIT, on_click=lambda e, r=r: self.edit(r)),
            ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color="#E06666", on_click=lambda e, r=r: self.delete(r))]),
            padding=10, border_radius=12, bgcolor="#F7F9FC") for r in rows]
        if refresh:
            self.update()

    def edit(self, r):
        c = self.ctx
        r = r or {"id": None, "name": "", "formula": "", "unit": "%", "memo": "", "sort": 99}
        name = T.field("比率名稱", r["name"])
        formula = T.field("公式", r["formula"], hint_text="例：(B(11)+B(12)) / B(21) * 100")
        unit = T.dropdown("單位", [("%", "%"), ("次", "次"), ("倍", "倍"), ("元", "元")], r["unit"], width=120,
                          filterable=False)
        memo = T.field("說明", r["memo"])

        def save(e):
            if c.guard(c.books.save_ratio, r["id"], name.value, formula.value, unit.value, memo.value,
                       ok="已儲存"):
                c.close()
                self.load()
        c.dialog("財務比率", ft.Column([name, formula, ft.Row([unit]), memo], tight=True, spacing=12),
                 [T.btn("取消", kind="ghost", on_click=lambda e: c.close()), T.btn("儲存", ft.Icons.SAVE, save)],
                 icon=ft.Icons.FUNCTIONS, tone="orange")

    def delete(self, r):
        def go():
            if self.ctx.guard(self.ctx.books.delete_ratio, r["id"]):
                self.load()
        self.ctx.confirm("刪除比率", "確定刪除「%s」？" % r["name"], go, yes="刪除")
