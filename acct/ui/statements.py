"""財務報表：試算表、損益表、資產負債表、現金流量表、財務比率、預算比較。"""
import datetime as dt
from decimal import Decimal

import flet as ft

from .. import rocdate
from ..books import CF_SECTIONS
from ..voice import speaker
from . import theme as T
from .ledgers import ReportBase, bold_rows


def speak_btn(fn):
    return T.btn("朗讀重點", ft.Icons.RECORD_VOICE_OVER, lambda e: fn(), kind="outline")


def say_amount(v):
    v = Decimal(v or 0)
    s = "負 " if v < 0 else ""
    v = abs(v)
    if v >= 100_000_000:
        return s + "%s 億元" % (v / 100_000_000).quantize(Decimal("0.01")).normalize()
    if v >= 10_000:
        return s + "%s 萬元" % (v / 10_000).quantize(Decimal("0.1")).normalize()
    return s + "%s 元" % v.quantize(Decimal("1"))


# ====================================================================== 試算表
class TrialBalance(ReportBase):
    icon, title, subtitle, tone = ft.Icons.BALANCE, "試算表", "期初、本期借貸與期末餘額；借貸合計應相等", "violet"

    def extra_filters(self):
        self.level = T.dropdown("層級", [(4, "明細（4 碼）"), (3, "小類（3 碼）"), (2, "中類（2 碼）"), (1, "大類")], 4,
                                width=150, filterable=False)
        return [self.level]

    def build(self):
        s, e = self.dates()
        tb = self.ctx.reports.trial_balance(s, e, int(self.level.value or 4), self.unposted.value)
        rows = tb["rows"] + [dict(name="合　　計", _cls="total", **tb["total"])]
        self.grid = T.Grid([("code", "代號", "s", 56), ("name", "科目名稱", "s", 200),
                            ("open_d", "期初借餘", "nz", 115), ("open_c", "期初貸餘", "nz", 115),
                            ("debit", "本期借方", "nz", 115), ("credit", "本期貸方", "nz", 115),
                            ("close_d", "期末借餘", "nz", 115), ("close_c", "期末貸餘", "nz", 115)],
                           row_style=bold_rows, on_pick=lambda r: r.get("code") and
                           self.ctx.app.go("ledger", account=r["code"]))
        self.grid.set_rows(rows)
        ok = tb["balanced"]
        banner = T.chip("借貸平衡：期末借餘 %s ＝ 期末貸餘 %s" % (T.amt(tb["total"]["close_d"]),
                                                       T.amt(tb["total"]["close_c"])) if ok else
                        "借貸不平衡！請檢查資料", "green" if ok else "rose",
                        ft.Icons.CHECK_CIRCLE if ok else ft.Icons.ERROR_OUTLINE, 13)
        self.result.content = ft.Column([banner, self.grid], spacing=10, expand=True)


# ====================================================================== 損益表
class Income(ReportBase):
    icon, title, subtitle, tone = ft.Icons.TRENDING_UP, "損益表", "營業收入 → 毛利 → 營業淨利 → 本期淨利", "violet"

    def extra_filters(self):
        self.dept = T.dropdown("部門", self.ctx.books.options("departments"), "", width=150, blank="全公司",
                               filterable=False)
        self.compare = ft.Checkbox(label="與去年同期比較", value=False)
        return [self.dept, self.compare]

    def header_actions(self):
        return [speak_btn(self.speak)]

    def build(self):
        s, e = self.dates()
        cmp_ = None
        if self.compare.value:
            cmp_ = (s.replace(year=s.year - 1), e.replace(year=e.year - 1) if not (e.month == 2 and e.day == 29)
                    else dt.date(e.year - 1, 2, 28))
        self.res = r = self.ctx.reports.income_statement(s, e, self.dept.value or "", self.unposted.value, cmp_)
        rows = []
        for ln in r["lines"]:
            k = ln["kind"]
            name = ln["name"] if k != "item" else "　　%s %s" % (ln["code"], ln["name"])
            rows.append(dict(name=name, amount=ln.get("amount"), pct=None if ln.get("pct") is None else
                             "%.1f%%" % ln["pct"], compare=ln.get("compare"),
                             _cls={"head": "head", "sub": "sub", "total": "total"}.get(k, "")))
        cols = [("name", "項　　目", "s", 300), ("amount", "本期金額", "n", 150), ("pct", "占營收 %", "s", 90)]
        if cmp_:
            cols.append(("compare", "去年同期", "n", 150))
        self.grid = T.Grid(cols, row_style=bold_rows)
        self.grid.set_rows(rows)
        net = r["net"]
        kpis = T.kpis([T.kpi("營業收入", T.amt(r["revenue"]), ft.Icons.STOREFRONT, "blue"),
                       T.kpi("營業毛利", T.amt(r["gross"]), ft.Icons.SAVINGS, "teal"),
                       T.kpi("營業淨利", T.amt(r["operating"]), ft.Icons.WORK_OUTLINE, "amber"),
                       T.kpi("本期淨利", T.amt(net), ft.Icons.EMOJI_EVENTS, "green" if net >= 0 else "rose")],
                      spacing=12)
        self.result.content = ft.Column([kpis, self.grid], spacing=12, expand=True)

    def speak(self):
        r = getattr(self, "res", None)
        if not r:
            return
        txt = "%s至%s，營業收入%s，營業毛利%s，營業淨利%s，本期%s%s。" % (
            self.start.value, self.end.value, say_amount(r["revenue"]), say_amount(r["gross"]),
            say_amount(r["operating"]), "淨利" if r["net"] >= 0 else "淨損", say_amount(abs(r["net"])))
        if r["revenue"]:
            txt += "淨利率百分之%.1f。" % (r["net"] / r["revenue"] * 100)
        speaker.say(txt.replace("/", "年", 1).replace("/", "月", 1))
        self.ctx.toast("🔊 朗讀中…")


# ====================================================================== 資產負債表
class BalanceSheet(ReportBase):
    icon, title, subtitle, tone = ft.Icons.ACCOUNT_BALANCE, "資產負債表", "資產 ＝ 負債 ＋ 權益", "violet"
    period = False

    def header_actions(self):
        return [speak_btn(self.speak)]

    def build(self):
        d = rocdate.read(self.end.value)
        self.res = bs = self.ctx.reports.balance_sheet(d, self.unposted.value)
        flat = []
        panels = []
        for side in bs["sides"]:
            flat.append(dict(name=side["name"], _cls="head"))
            blocks = []
            for it in side["items"]:
                flat.append(dict(name="　" + it["name"], _cls="head"))
                lines = [ft.Row([ft.Text(it["name"], size=14, weight=ft.FontWeight.W_700, expand=True),
                                 ft.Text(T.amt(it["amount"], paren=True), size=14, weight=ft.FontWeight.W_700)])]
                for dt_ in it["details"]:
                    flat.append(dict(name="　　%s %s" % (dt_["code"], dt_["name"]), amount=dt_["amount"]))
                    lines.append(ft.Row([ft.Text("%s %s" % (dt_["code"], dt_["name"]), size=13, color="#475569",
                                                 expand=True),
                                         ft.Text(T.amt(dt_["amount"], paren=True), size=13, color="#475569")]))
                flat.append(dict(name="　%s合計" % it["name"], amount=it["amount"], _cls="sub"))
                blocks.append(ft.Container(ft.Column(lines, spacing=3), padding=ft.Padding.only(bottom=8),
                                           border=ft.Border.only(bottom=ft.BorderSide(1, "#EEF1F5"))))
            flat.append(dict(name="%s總計" % side["name"], amount=side["total"], _cls="total"))
            tone = {"1": "blue", "2": "rose", "3": "teal"}[side["code"]]
            bg, fg = T.TONES[tone]
            panels.append((side["code"], ft.Column([
                ft.Container(ft.Row([ft.Text(side["name"], size=16, weight=ft.FontWeight.W_800, color=fg,
                                             expand=True),
                                     ft.Text(T.amt(side["total"], paren=True), size=16, weight=ft.FontWeight.W_800,
                                             color=fg)]), bgcolor=bg, border_radius=10, padding=10),
                *blocks], spacing=8)))
        self.grid = T.Grid([("name", "項　　目", "s", 300), ("amount", "金額", "n", 150)], row_style=bold_rows)
        self.grid.set_rows(flat)
        p = dict(panels)
        ok = bs["balanced"]
        check = T.chip("資產 %s ＝ 負債 %s ＋ 權益 %s" % (T.amt(bs["assets"]), T.amt(bs["liabilities"]),
                                                   T.amt(bs["equity"])) if ok else "不平衡，請檢查開帳與傳票",
                       "green" if ok else "rose", ft.Icons.CHECK_CIRCLE if ok else ft.Icons.ERROR_OUTLINE, 13)
        if T.MOBILE:
            self.result.content = ft.Column([check, T.card(p["1"], padding=14),
                                             T.card(ft.Column([p["2"], ft.Container(height=8), p["3"]]), padding=14)],
                                            spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
            return
        self.result.content = ft.Column([check, ft.Row([
            T.card(ft.Column([p["1"]], scroll=ft.ScrollMode.AUTO), expand=True),
            T.card(ft.Column([p["2"], ft.Container(height=8), p["3"]], scroll=ft.ScrollMode.AUTO), expand=True)],
            spacing=14, expand=True, vertical_alignment=ft.CrossAxisAlignment.START)], spacing=10, expand=True)

    def speak(self):
        bs = getattr(self, "res", None)
        if bs:
            speaker.say("截至%s，資產總額%s，負債總額%s，權益總額%s。負債比率百分之%.1f。" % (
                self.end.value.replace("/", "年", 1).replace("/", "月", 1) + "日", say_amount(bs["assets"]),
                say_amount(bs["liabilities"]), say_amount(bs["equity"]),
                (bs["liabilities"] / bs["assets"] * 100) if bs["assets"] else 0))


# ====================================================================== 現金流量表
class CashFlow(ReportBase):
    icon, title, subtitle, tone = ft.Icons.WATER_DROP, "現金流量表", "直接法：依對方科目歸類營業、投資、籌資活動", "violet"

    def build(self):
        s, e = self.dates()
        cf = self.ctx.reports.cash_flow(s, e, self.unposted.value)
        flat, cards = [], []
        tones = {"OP": ("teal", ft.Icons.STOREFRONT), "INV": ("amber", ft.Icons.BUSINESS),
                 "FIN": ("violet", ft.Icons.ACCOUNT_BALANCE)}
        for k in ("OP", "INV", "FIN"):
            sec = cf["sections"][k]
            flat.append(dict(name="%s之現金流量" % CF_SECTIONS[k], _cls="head"))
            for it in sec["items"]:
                flat.append(dict(name="　%s %s" % (it["code"], it["name"]), amount=it["amount"]))
            flat.append(dict(name="%s淨現金流入（出）" % CF_SECTIONS[k], amount=sec["total"], _cls="sub"))
            tone, icon = tones[k]
            cards.append(T.kpi(CF_SECTIONS[k], T.amt(sec["total"]), icon, tone))
        flat += [dict(name="本期現金淨增（減）", amount=cf["net"], _cls="total"),
                 dict(name="開帳或其他調整", amount=cf["other"]),
                 dict(name="期初現金及約當現金", amount=cf["opening"]),
                 dict(name="期末現金及約當現金", amount=cf["closing"], _cls="total")]
        self.grid = T.Grid([("name", "項　　目", "s", 340), ("amount", "金額", "n", 150)], row_style=bold_rows)
        self.grid.set_rows(flat)
        self.result.content = ft.Column([T.kpis(cards + [T.kpi("期末現金", T.amt(cf["closing"]),
                                                               ft.Icons.ACCOUNT_BALANCE_WALLET, "green",
                                                               sub="期初 %s" % T.amt(cf["opening"]))], spacing=12),
                                         self.grid], spacing=12, expand=True)


# ====================================================================== 財務比率
class Ratios(ReportBase):
    icon, title, subtitle, tone = ft.Icons.PIE_CHART, "財務比率分析", "償債能力、獲利能力與經營效率", "violet"

    def header_actions(self):
        return [T.btn("設定公式", ft.Icons.FUNCTIONS, lambda e: self.ctx.app.go("ratio_setup"), kind="ghost")]

    def build(self):
        s, e = self.dates()
        rows = self.ctx.reports.ratios(s, e, self.unposted.value)
        tiles = []
        palette = ["blue", "teal", "amber", "violet", "green", "sky", "rose", "orange", "pink", "slate"]
        for i, r in enumerate(rows):
            v = r["value"]
            r["show"] = r["error"] or ("%s %s" % ("{:,.2f}".format(v), r["unit"]))
            bar = None
            if v is not None and r["unit"] == "%":
                bar = ft.ProgressBar(value=max(0.0, min(1.0, float(v) / 200 if "流動" in r["name"] or "速動" in
                                                        r["name"] else float(v) / 100)),
                                     color=T.TONES[palette[i % 10]][1], bgcolor="#EEF1F5", bar_height=6,
                                     border_radius=3)
            tiles.append(ft.Container(ft.Column([
                ft.Row([T.icon_tile(ft.Icons.INSIGHTS, palette[i % 10], 36),
                        ft.Text(r["name"], size=15, weight=ft.FontWeight.W_700, expand=True)]),
                ft.Text(r["show"], size=24, weight=ft.FontWeight.W_800,
                        color=T.DANGER if r["error"] else T.TEXT),
                *([bar] if bar else []),
                T.muted(r["memo"], 12), T.muted(r["formula"], 10)], spacing=6),
                width=290, padding=16, bgcolor=T.CARD, border_radius=16, border=ft.Border.all(1, T.LINE)))
        self.grid = T.Grid([("name", "比率", "s", 140), ("show", "數值", "s", 120), ("formula", "公式", "s", 300),
                            ("memo", "說明", "s", 300)])
        self.grid.set_rows(rows)
        self.result.content = ft.Column([ft.Row(tiles, wrap=True, spacing=14, run_spacing=14)],
                                        scroll=ft.ScrollMode.AUTO, expand=True)


# ====================================================================== 預算比較
class BudgetCompare(ReportBase):
    icon, title, subtitle, tone = ft.Icons.QUERY_STATS, "預算比較", "累計預算與實際數、差異與達成率", "violet"
    period = False

    def extra_filters(self):
        y = rocdate.today().year
        self.year = T.dropdown("年度", [(i, "%d 年" % (i - 1911)) for i in range(y - 3, y + 2)], y, width=120,
                               filterable=False)
        self.month = T.dropdown("累計至", [(m, "%d 月" % m) for m in range(1, 13)], rocdate.today().month, width=110,
                                filterable=False)
        self.dept = T.dropdown("部門", self.ctx.books.options("departments"), "", width=150, blank="全公司",
                               filterable=False)
        self.end.visible = False
        return [self.year, self.month, self.dept]

    def build(self):
        rows = self.ctx.reports.budget_compare(int(self.year.value), int(self.month.value), self.dept.value or "")
        for r in rows:
            r["rate"] = "" if r["pct"] is None else "%.1f%%" % r["pct"]
        self.grid = T.Grid([("code", "代號", "s", 60), ("name", "科目", "s", 200), ("budget", "累計預算", "n", 130),
                            ("actual", "實際數", "n", 130), ("diff", "差異", "n", 130), ("rate", "達成率", "s", 90)],
                           totals=("budget", "actual"), empty="此年度尚未編列預算（期末作業 → 預算編列）")
        self.grid.set_rows(rows)
        self.result.content = self.grid

    def subtitle_text(self):
        return "%d 年 1～%s 月" % (int(self.year.value) - 1911, self.month.value)
