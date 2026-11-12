"""使用說明：前言（系統導入說明）＋各功能操作說明，每節都能語音朗讀，導入說明可列印成手冊。"""
import flet as ft

from .. import adoption, printing
from ..help_text import GUIDE
from ..voice import speaker
from . import theme as T

ICONS = {"intro": (ft.Icons.WB_SUNNY, "amber"), "quickstart": (ft.Icons.ROCKET_LAUNCH, "rose"),
         "flow": (ft.Icons.ACCOUNT_TREE, "violet"), "home": (ft.Icons.DASHBOARD_ROUNDED, "blue"),
         "voucher_entry": (ft.Icons.EDIT_NOTE, "teal"), "voucher_list": (ft.Icons.MANAGE_SEARCH, "teal"),
         "voucher_review": (ft.Icons.FACT_CHECK, "amber"), "gl_import": (ft.Icons.SYNC_ALT, "teal"), "journal": (ft.Icons.MENU_BOOK, "orange"),
         "ledger": (ft.Icons.LIST_ALT, "orange"), "general_ledger": (ft.Icons.ACCOUNT_TREE, "orange"),
         "cash_book": (ft.Icons.PAYMENTS, "teal"), "partner_ledger": (ft.Icons.HANDSHAKE, "sky"),
         "trial_balance": (ft.Icons.BALANCE, "violet"), "income": (ft.Icons.TRENDING_UP, "violet"),
         "balance_sheet": (ft.Icons.ACCOUNT_BALANCE, "violet"), "cash_flow": (ft.Icons.WATER_DROP, "violet"),
         "ratios": (ft.Icons.PIE_CHART, "violet"), "budget_compare": (ft.Icons.QUERY_STATS, "violet"),
         "accounts": (ft.Icons.ACCOUNT_TREE, "sky"), "templates": (ft.Icons.BOOKMARKS, "sky"),
         "periods": (ft.Icons.LOCK_CLOCK, "orange"), "revaluation": (ft.Icons.PRICE_CHANGE, "orange"),
         "year_end": (ft.Icons.EVENT_AVAILABLE, "orange"), "users": (ft.Icons.ADMIN_PANEL_SETTINGS, "rose"),
         "company": (ft.Icons.BUSINESS, "rose"), "backup": (ft.Icons.BACKUP, "rose"),
         "update": (ft.Icons.SYSTEM_UPDATE, "rose"), "shortcut": (ft.Icons.SHORTCUT, "green"),
         "mobile_link": (ft.Icons.PHONE_ANDROID, "rose"), "mobile_app": (ft.Icons.SMARTPHONE, "teal"),
         # 前言：系統導入
         "adopt_overview": (ft.Icons.MAP, "blue"), "adopt_company": (ft.Icons.STOREFRONT, "teal"),
         "adopt_prepare": (ft.Icons.CHECKLIST, "amber"), "adopt_data": (ft.Icons.TABLE_CHART, "orange"),
         "adopt_setup": (ft.Icons.SETTINGS_SUGGEST, "violet"), "adopt_opening": (ft.Icons.FLAG, "rose"),
         "adopt_parallel": (ft.Icons.COMPARE_ARROWS, "sky"), "adopt_daily": (ft.Icons.TODAY, "green"),
         "adopt_monthly": (ft.Icons.CALENDAR_MONTH, "teal"), "adopt_yearly": (ft.Icons.EVENT_AVAILABLE, "pink"),
         "adopt_tips": (ft.Icons.TIPS_AND_UPDATES, "amber")}

FLOW = [(ft.Icons.RECEIPT, "原始憑證", "slate"), (ft.Icons.EDIT_NOTE, "傳票登錄", "teal"),
        (ft.Icons.VERIFIED, "審核", "amber"), (ft.Icons.DONE_ALL, "過帳", "green"),
        (ft.Icons.MENU_BOOK, "日記簿・分類帳", "orange"), (ft.Icons.INSIGHTS, "財務報表", "violet"),
        (ft.Icons.LOCK_CLOCK, "關帳・年結", "rose")]
ADOPT_FLOW = [(ft.Icons.CHECKLIST, "導入準備", "amber"), (ft.Icons.TABLE_CHART, "資料整理", "orange"),
              (ft.Icons.SETTINGS_SUGGEST, "系統建置", "violet"), (ft.Icons.FLAG, "期初開帳", "rose"),
              (ft.Icons.COMPARE_ARROWS, "平行作業", "sky"), (ft.Icons.TODAY, "正式上線", "green")]

# 目錄：(群組標題, [(代號, 標題)])
TOC = [("前言：系統導入說明", [(s["key"], s["title"]) for s in adoption.SECTIONS]),
       ("功能操作說明", [(k, t) for k, t, _ in GUIDE])]
ORDER = [k for _, items in TOC for k, _ in items]


def section(key):
    """回傳 (標題, 區塊, 朗讀文字)"""
    if key in adoption.BY_KEY:
        s = adoption.BY_KEY[key]
        return s["title"], s["blocks"], adoption.spoken(s)
    title, text = next((t, x) for k, t, x in GUIDE if k == key)
    return title, [("p", p) for p in text.replace("。", "。\n").split("\n") if p.strip()], text


class Help(ft.Row):
    def __init__(self, ctx):
        self.ctx = ctx
        self.sec = ORDER[0]
        self.toc = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)
        self.banner = ft.Container()
        self.body = ft.Column(spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
        super().__init__([T.card(self.toc, width=300, padding=12),
                          ft.Column([self.banner, T.card(self.body, expand=True, padding=26)], expand=True,
                                    spacing=14)], expand=True, spacing=14, data="split",
                         vertical_alignment=ft.CrossAxisAlignment.START)
        self.show(self.sec, refresh=False)

    def flow(self, steps, title, extra=None):
        items = []
        for i, (icon, text, tone) in enumerate(steps):
            if i:
                items.append(ft.Icon(ft.Icons.ARROW_FORWARD_ROUNDED, color="#94A3B8", size=20))
            items.append(ft.Column([T.icon_tile(icon, tone, 46, radius=14), ft.Text(text, size=12,
                                                                                weight=ft.FontWeight.W_600)],
                                   horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6))
        return T.card(ft.Column([ft.Row([ft.Text(title, size=15, weight=ft.FontWeight.W_700, expand=True),
                                         *(extra or [])]),
                                 ft.Row(items, alignment=ft.MainAxisAlignment.SPACE_AROUND,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True)], spacing=10),
                      padding=16)

    def show(self, key, refresh=True):
        self.sec = key
        adopt = key in adoption.BY_KEY
        toc = []
        for group, items in TOC:
            toc.append(ft.Container(ft.Text(group, size=12, weight=ft.FontWeight.W_700, color=T.MUTED),
                                    padding=ft.Padding.only(left=8, top=10, bottom=4)))
            for k, t in items:
                sel = k == key
                toc.append(ft.Container(ft.Row([
                    T.icon_tile(*ICONS.get(k, (ft.Icons.ARTICLE, "slate")), 30, radius=9),
                    ft.Text(t, size=13, weight=ft.FontWeight.W_700 if sel else ft.FontWeight.W_500, expand=True,
                            color=T.PRIMARY if sel else T.TEXT)], spacing=10),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=6), border_radius=10,
                    bgcolor="#E3EDFF" if sel else None, ink=True, on_click=lambda e, k=k: self.show(k)))
        self.toc.controls = toc
        self.banner.content = (self.flow(ADOPT_FLOW, "系統導入六階段（以祥和貿易為例）",
                                         [T.btn("列印導入手冊", ft.Icons.PRINT, lambda e: print_manual(self.ctx),
                                                kind="outline")])
                               if adopt else self.flow(FLOW, "會計作業流程"))
        title, blocks, spoken = section(key)
        icon, tone = ICONS.get(key, (ft.Icons.ARTICLE, "slate"))
        n = ORDER.index(key)
        self.body.controls = [
            ft.Row([T.icon_tile(icon, tone, 56, radius=16),
                    ft.Column([T.muted("前言・第 %d 節" % (n + 1) if adopt else "操作說明", 12),
                               ft.Text(title, size=23, weight=ft.FontWeight.W_800)], spacing=0, expand=True),
                    T.btn("朗讀", ft.Icons.VOLUME_UP, lambda e: speaker.say_help(key, spoken), kind="accent"),
                    T.btn("停止", ft.Icons.STOP_CIRCLE, lambda e: speaker.stop(), kind="outline")]),
            *[render(b, tone) for b in blocks],
            ft.Divider(),
            ft.Row([T.btn("上一節", ft.Icons.CHEVRON_LEFT, lambda e: self.step(-1), kind="ghost"),
                    ft.Container(expand=True),
                    *([T.btn("前往此功能", ft.Icons.OPEN_IN_NEW, lambda e: self.ctx.app.go(key), kind="outline")]
                      if not adopt and self.ctx.app.find(key) and key != "help" else []),
                    T.btn("下一節", ft.Icons.CHEVRON_RIGHT, lambda e: self.step(1), kind="ghost")])]
        if refresh:
            speaker.stop()
            self.update()

    def step(self, d):
        self.show(ORDER[(ORDER.index(self.sec) + d) % len(ORDER)])


def render(b, tone):
    kind = b[0]
    fg = T.TONES[tone][1]
    if kind == "p":
        return ft.Text(b[1], size=15, color="#334155", selectable=True)
    if kind == "steps":
        return ft.Column([ft.Row([
            ft.Container(ft.Text(str(i), color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.W_700), width=28,
                         height=28, border_radius=14, bgcolor=fg, alignment=ft.Alignment.CENTER),
            ft.Text(s, size=15, color="#334155", expand=True, selectable=True)],
            vertical_alignment=ft.CrossAxisAlignment.START, spacing=12) for i, s in enumerate(b[1], 1)], spacing=10)
    if kind == "check":
        return ft.Column([ft.Row([ft.Icon(ft.Icons.CHECK_BOX_OUTLINED, color=T.SUCCESS, size=20),
                                  ft.Text(s, size=14, color="#334155", expand=True, selectable=True)],
                                 vertical_alignment=ft.CrossAxisAlignment.START, spacing=10) for s in b[1]],
                         spacing=6)
    if kind == "tip":
        return ft.Container(ft.Row([ft.Icon(ft.Icons.LIGHTBULB, color=T.WARN),
                                    ft.Text(b[1], size=14, color="#92400E", expand=True, selectable=True)],
                                   vertical_alignment=ft.CrossAxisAlignment.START, spacing=10),
                            bgcolor="#FFF7E6", border_radius=12, padding=14, border=ft.Border.all(1, "#FCD9A0"))
    if kind == "table":
        head, rows = b[1], b[2]
        nums = [all(_numeric(r[i]) for r in rows if r[i]) and any(r[i] for r in rows) for i in range(len(head))]
        return ft.Container(ft.Row([ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h, weight=ft.FontWeight.W_700, size=13), numeric=nums[i])
                     for i, h in enumerate(head)],
            rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(c, size=13, selectable=True,
                                                        weight=ft.FontWeight.W_700 if r[0].startswith("合") else None))
                                    for c in r]) for r in rows],
            heading_row_color="#EEF3FA", heading_row_height=38, data_row_min_height=34, data_row_max_height=60,
            column_spacing=22, border=ft.Border.all(1, T.LINE), border_radius=10,
            horizontal_lines=ft.BorderSide(0.6, "#EDF1F6"))], scroll=ft.ScrollMode.AUTO))
    return ft.Text(str(b))


def _numeric(s):
    return s.replace(",", "").replace(".", "").isdigit()


def print_manual(ctx):
    """把導入說明（前言）輸出成可列印的手冊。"""
    from html import escape as esc
    parts = []
    for i, s in enumerate(adoption.SECTIONS, 1):
        h = "<h2>%d. %s</h2>" % (i, esc(s["title"]))
        for b in s["blocks"]:
            if b[0] == "p":
                h += "<p>%s</p>" % esc(b[1])
            elif b[0] == "steps":
                h += "<ol>%s</ol>" % "".join("<li>%s</li>" % esc(x) for x in b[1])
            elif b[0] == "check":
                h += "<ul class='chk'>%s</ul>" % "".join("<li>☐ %s</li>" % esc(x) for x in b[1])
            elif b[0] == "tip":
                h += "<div class='tip'>💡 %s</div>" % esc(b[1])
            elif b[0] == "table":
                cols = [(str(j), c, _numeric(b[2][0][j]) if b[2] and b[2][0][j] else False)
                        for j, c in enumerate(b[1])]
                h += printing.table(cols, [{str(j): v for j, v in enumerate(r)} | {"_t": r[0]} for r in b[2]],
                                    lambda r: "total" if r["_t"].startswith("合") else "")
        parts.append("<section>%s</section>" % h)
    css = ("<style>h2{color:#1e4d8c;border-bottom:2px solid #dbe5f3;padding-bottom:4px;margin-top:26px}"
           "p,li{line-height:1.75;font-size:13.5px}ol li{margin:4px 0}.chk{list-style:none;padding-left:6px}"
           ".tip{background:#fff7e6;border:1px solid #fcd9a0;border-radius:8px;padding:8px 12px;color:#92400e;"
           "margin:8px 0}section{page-break-inside:auto}</style>")
    html = printing.page(ctx.books.company().get("name", ""), "系統導入說明手冊",
                         "從人工作業到正式使用 — 以%s為例" % adoption.COMPANY, css + "".join(parts))
    printing.write_and_open(html, "導入說明手冊")
