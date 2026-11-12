"""首頁：關鍵數字、十二個月收支趨勢、快捷功能、待處理傳票。"""
import datetime as dt
from decimal import Decimal

import flet as ft

from .. import rocdate
from . import theme as T


class Dashboard(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        b, app = ctx.books, ctx.app
        d = ctx.reports.dashboard()
        comp = b.company()
        hour = dt.datetime.now().hour
        hello = "早安" if hour < 11 else "午安" if hour < 18 else "晚安"
        net = d["month_net"]

        hero = ft.Container(ft.Row([
            ft.Column([
                ft.Text("%s，%s" % (hello, b.user["name"]), size=26, weight=ft.FontWeight.W_800,
                        color=ft.Colors.WHITE),
                ft.Text(comp.get("name") or "", size=15, color="#CFE0F7"),
                ft.Container(height=6),
                ft.Row([hero_chip(ft.Icons.PENDING_ACTIONS, "待處理傳票 %d 張" % d["pending"]),
                        hero_chip(ft.Icons.CALENDAR_MONTH, rocdate.ym_show(rocdate.ym(rocdate.today())))],
                       spacing=10)], spacing=2, expand=True),
            ft.Image(src="icon.png", width=96, height=96, opacity=0.95)]),
            padding=26, border_radius=20,
            gradient=ft.LinearGradient(begin=ft.Alignment.CENTER_LEFT, end=ft.Alignment.CENTER_RIGHT,
                                       colors=[T.PRIMARY_DARK, T.PRIMARY, "#178A8F"]),
            shadow=ft.BoxShadow(blur_radius=24, spread_radius=-8, color="#551E4D8C", offset=ft.Offset(0, 10)))

        kpis = T.kpis([
            T.kpi("現金及銀行存款", T.amt(d["cash"]), ft.Icons.ACCOUNT_BALANCE_WALLET, "teal",
                  on_click=lambda e: app.go("cash_book")),
            T.kpi("應收款項", T.amt(d["receivable"]), ft.Icons.CALL_RECEIVED, "sky",
                  on_click=lambda e: app.go("partner_ledger")),
            T.kpi("應付款項", T.amt(d["payable"]), ft.Icons.CALL_MADE, "amber",
                  on_click=lambda e: app.go("partner_ledger")),
            T.kpi("本月損益", T.amt(net), ft.Icons.TRENDING_UP if net >= 0 else ft.Icons.TRENDING_DOWN,
                  "green" if net >= 0 else "rose", sub="本月收入 %s" % T.amt(d["month_revenue"]),
                  on_click=lambda e: app.go("income"))])

        quick = [("收入傳票", ft.Icons.ADD_CARD, "green", lambda e: app.go("voucher_entry", v_type="收")),
                 ("支出傳票", ft.Icons.REQUEST_QUOTE, "rose", lambda e: app.go("voucher_entry", v_type="支")),
                 ("轉帳傳票", ft.Icons.SWAP_HORIZ, "blue", lambda e: app.go("voucher_entry", v_type="轉")),
                 ("審核過帳", ft.Icons.FACT_CHECK, "amber", lambda e: app.go("voucher_review")),
                 ("試算表", ft.Icons.BALANCE, "violet", lambda e: app.go("trial_balance")),
                 ("損益表", ft.Icons.TRENDING_UP, "teal", lambda e: app.go("income")),
                 ("資產負債表", ft.Icons.ACCOUNT_BALANCE, "sky", lambda e: app.go("balance_sheet")),
                 ("使用說明", ft.Icons.RECORD_VOICE_OVER, "pink", lambda e: app.go("help"))]
        quick_tiles = ft.Row([quick_tile(t, ic, tone, fn) for t, ic, tone, fn in quick
                              if app.find(_sid_of(t))], wrap=True, spacing=12, run_spacing=12)

        chart = T.card(ft.Column([
            ft.Row([T.icon_tile(ft.Icons.AUTO_GRAPH, "violet", 36), ft.Text("近 12 個月收支", size=17,
                                                                          weight=ft.FontWeight.W_700),
                    ft.Container(expand=True), legend("收入", "#3B82F6"), legend("支出", "#F59E0B")], spacing=10),
            bars(d["months"])], spacing=14), expand=3)

        pending = b.find_vouchers(status=0, limit=6) + b.find_vouchers(status=1, limit=6)
        plist = ft.Column([pending_row(v, lambda e, vid=v["id"]: app.go("voucher_list", focus=vid))
                           for v in pending[:8]] or [T.empty_state(ft.Icons.TASK_ALT, "目前沒有待處理的傳票")],
                          spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
        todo = T.card(ft.Column([
            ft.Row([T.icon_tile(ft.Icons.PENDING_ACTIONS, "amber", 36),
                    ft.Text("待審核／待過帳", size=17, weight=ft.FontWeight.W_700)], spacing=10),
            plist], spacing=12), expand=2, height=330)

        super().__init__([
            hero, kpis,
            ft.Row([ft.Text("快捷功能", size=17, weight=ft.FontWeight.W_700, color=T.TEXT)]), quick_tiles,
            T.split(chart, todo, spacing=16)],
            spacing=18, scroll=ft.ScrollMode.AUTO, expand=True)


def _sid_of(title):
    return {"收入傳票": "voucher_entry", "支出傳票": "voucher_entry", "轉帳傳票": "voucher_entry",
            "審核過帳": "voucher_review", "試算表": "trial_balance", "損益表": "income",
            "資產負債表": "balance_sheet", "使用說明": "help"}[title]


def hero_chip(icon, text):
    return ft.Container(ft.Row([ft.Icon(icon, size=15, color=ft.Colors.WHITE), ft.Text(text, size=12,
                                                                                    color=ft.Colors.WHITE)],
                               spacing=6, tight=True), bgcolor="#33FFFFFF", border_radius=20,
                        padding=ft.Padding.symmetric(horizontal=12, vertical=5))


def quick_tile(title, icon, tone, on_click):
    return ft.Container(ft.Column([T.icon_tile(icon, tone, 48, radius=14),
                                   ft.Text(title, size=13, weight=ft.FontWeight.W_600, color=T.TEXT)],
                                  horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                        width=118, padding=ft.Padding.symmetric(vertical=16), bgcolor=T.CARD, border_radius=16,
                        border=ft.Border.all(1, T.LINE), on_click=on_click, ink=True,
                        shadow=ft.BoxShadow(blur_radius=14, spread_radius=-6, color="#1A1E3A5F",
                                            offset=ft.Offset(0, 4)))


def legend(text, color):
    return ft.Row([ft.Container(width=12, height=12, bgcolor=color, border_radius=3), T.muted(text, 12)],
                  spacing=5, tight=True)


def bars(months, h=190):
    top = max([Decimal(1)] + [abs(m["revenue"]) for m in months] + [abs(m["expense"]) for m in months])
    cols = []
    for m in months:
        rv, ex = max(m["revenue"], 0), max(m["expense"], 0)
        cols.append(ft.Column([
            ft.Row([ft.Container(width=12, height=max(2, float(rv / top) * h), bgcolor="#3B82F6",
                                 border_radius=ft.BorderRadius.only(top_left=4, top_right=4),
                                 tooltip="收入 %s" % T.amt(m["revenue"])),
                    ft.Container(width=12, height=max(2, float(ex / top) * h), bgcolor="#F59E0B",
                                 border_radius=ft.BorderRadius.only(top_left=4, top_right=4),
                                 tooltip="支出 %s" % T.amt(m["expense"]))],
                   spacing=3, vertical_alignment=ft.CrossAxisAlignment.END),
            T.muted(m["label"], 11)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4,
            alignment=ft.MainAxisAlignment.END))
    return ft.Container(ft.Row(cols, alignment=ft.MainAxisAlignment.SPACE_AROUND,
                               vertical_alignment=ft.CrossAxisAlignment.END), height=h + 26,
                        border=ft.Border.only(bottom=ft.BorderSide(1, T.LINE)))


def pending_row(v, on_click):
    return ft.Container(ft.Row([
        T.chip(v["v_type"], T.VTYPE_TONE.get(v["v_type"], "slate")),
        ft.Column([ft.Text(v["v_no"], size=13, weight=ft.FontWeight.W_600),
                   T.muted((v["memo"] or rocdate.show(v["v_date"]))[:18], 11)], spacing=0, expand=True),
        ft.Text(T.amt(v["total"]), size=13, weight=ft.FontWeight.W_600), T.status_chip(v["status"])], spacing=10),
        padding=ft.Padding.symmetric(horizontal=10, vertical=6), border_radius=10, bgcolor="#F7F9FC",
        on_click=on_click, ink=True)
