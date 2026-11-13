"""主程式框架：啟動資料庫 → 登入 → 主畫面（左側功能選單、上方工具列、內容區）。"""
import logging
import os
import threading

import flet as ft

from .. import APP_NAME, APP_SHORT, APP_VERSION, rocdate
from ..books import BizError, Books
from ..database import DB, explain_error
from ..dbserver import LocalDatabaseServer
from ..help_text import text_for
from ..reports import Reports
from ..settings import Settings, data_dir
from ..voice import speaker
from . import theme as T

log = logging.getLogger("acct")
if not log.handlers:
    _h = logging.FileHandler(os.path.join(data_dir(), "acct.log"), encoding="utf-8")
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)


def menu():
    """(群組, 圖示, 色調, [(畫面代號, 名稱, 圖示, 權限, 等級)])"""
    I = ft.Icons
    return [
        ("總覽", I.DASHBOARD_ROUNDED, "blue", [("home", "首頁", I.DASHBOARD_ROUNDED, "", 0)]),
        ("傳票作業", I.RECEIPT_LONG, "teal", [
            ("voucher_entry", "傳票登錄", I.EDIT_NOTE, "VOU", 2),
            ("voucher_list", "傳票查詢", I.MANAGE_SEARCH, "VOU", 1),
            ("voucher_review", "審核過帳", I.FACT_CHECK, "APR", 2),
            ("gl_import", "拋轉匯入", I.SYNC_ALT, "VOU", 2)]),
        ("帳簿查詢", I.MENU_BOOK, "amber", [
            ("journal", "日記簿", I.MENU_BOOK, "LED", 1),
            ("ledger", "明細分類帳", I.LIST_ALT, "LED", 1),
            ("general_ledger", "總分類帳", I.ACCOUNT_TREE, "LED", 1),
            ("cash_book", "現金簿", I.PAYMENTS, "LED", 1),
            ("partner_ledger", "往來明細", I.HANDSHAKE, "LED", 1)]),
        ("財務報表", I.INSIGHTS, "violet", [
            ("trial_balance", "試算表", I.BALANCE, "FIN", 1),
            ("income", "損益表", I.TRENDING_UP, "FIN", 1),
            ("balance_sheet", "資產負債表", I.ACCOUNT_BALANCE, "FIN", 1),
            ("cash_flow", "現金流量表", I.WATER_DROP, "FIN", 1),
            ("ratios", "財務比率", I.PIE_CHART, "FIN", 1),
            ("budget_compare", "預算比較", I.QUERY_STATS, "FIN", 1)]),
        ("基本資料", I.FOLDER_SPECIAL, "sky", [
            ("accounts", "會計科目", I.ACCOUNT_TREE, "BAS", 1),
            ("templates", "常用分錄", I.BOOKMARKS, "BAS", 1),
            ("phrases", "摘要片語", I.SHORT_TEXT, "BAS", 1),
            ("departments", "部門", I.APARTMENT, "BAS", 1),
            ("employees", "員工", I.BADGE, "BAS", 1),
            ("customers", "客戶", I.STOREFRONT, "BAS", 1),
            ("vendors", "廠商", I.LOCAL_SHIPPING, "BAS", 1),
            ("projects", "專案", I.WORK_OUTLINE, "BAS", 1),
            ("currencies", "幣別匯率", I.CURRENCY_EXCHANGE, "BAS", 1)]),
        ("期末作業", I.EVENT_AVAILABLE, "orange", [
            ("periods", "期間關帳", I.LOCK_CLOCK, "CLS", 2),
            ("revaluation", "外幣現值調整", I.PRICE_CHANGE, "CLS", 2),
            ("year_end", "年度結帳", I.EVENT_AVAILABLE, "CLS", 2),
            ("budget_edit", "預算編列", I.SAVINGS, "CLS", 2),
            ("ratio_setup", "比率公式", I.FUNCTIONS, "CLS", 2)]),
        ("系統管理", I.ADMIN_PANEL_SETTINGS, "rose", [
            ("users", "使用者與權限", I.ADMIN_PANEL_SETTINGS, "SYS", 2),
            ("company", "公司設定", I.BUSINESS, "SYS", 2),
            ("mobile_link", "手機連線", I.PHONE_ANDROID, "SYS", 2),
            ("backup", "備份與還原", I.BACKUP, "SYS", 2),
            ("update", "版本更新與捷徑", I.SYSTEM_UPDATE, "", 0),
            ("audit", "操作紀錄", I.HISTORY, "SYS", 1)]),
        ("說明", I.HELP_CENTER, "green", [("help", "使用說明", I.HELP_CENTER, "", 0)]),
    ]


def build_screen(sid, ctx, **kw):
    from . import admin, closing, dashboard, glimport_view, helpview, ledgers, masters, statements, vouchers
    table = {
        "home": dashboard.Dashboard, "voucher_entry": vouchers.VoucherEntry, "voucher_list": vouchers.VoucherList,
        "voucher_review": vouchers.Review, "journal": ledgers.Journal, "ledger": ledgers.Ledger,
        "general_ledger": ledgers.GeneralLedger, "cash_book": ledgers.CashBook,
        "partner_ledger": ledgers.PartnerLedger, "trial_balance": statements.TrialBalance,
        "income": statements.Income, "balance_sheet": statements.BalanceSheet, "cash_flow": statements.CashFlow,
        "ratios": statements.Ratios, "budget_compare": statements.BudgetCompare, "accounts": masters.Accounts,
        "templates": masters.Templates, "periods": closing.Periods, "revaluation": closing.Revaluation,
        "year_end": closing.YearEnd, "budget_edit": closing.BudgetEdit, "ratio_setup": closing.RatioSetup,
        "users": admin.Users, "company": admin.Company, "backup": admin.Backup, "update": admin.Update,
        "mobile_link": admin.MobileLink, "gl_import": glimport_view.GLImport,
        "audit": admin.Audit, "help": helpview.Help,
    }
    if sid in table:
        return table[sid](ctx, **kw)
    return masters.MasterList(ctx, sid)


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.st = Settings.load()
        self.server = None
        self.db = None
        self.books = None
        self.reports = None
        self.ctx = None
        self.current = "home"
        self.expanded = {"總覽", "傳票作業"}
        self.update_info = None
        self.mobile = False
        self.api = None              # 電腦版：手機連線服務
        self.client = None           # 手機版：連到電腦的用戶端
        self.server_info = None

    # ================================================================ 啟動
    def start(self):
        p = self.page
        p.title = APP_NAME
        p.fonts = {"NotoSansTC": "fonts/NotoSansTC-VF.ttf"}
        from . import textscale
        textscale.install(p)                      # Windows 文字大小 210% 之類：限制放大倍數，免得字被切掉
        p.theme = ft.Theme(color_scheme_seed=T.PRIMARY, font_family="NotoSansTC", 
                             text_theme=textscale.text_theme(T.TEXT))
        p.theme_mode = ft.ThemeMode.LIGHT
        p.bgcolor = T.BG
        p.padding = 0
        p.spacing = 0
        from . import mobile
        if mobile.is_mobile(p):
            self.mobile = True
            mobile.start(self)
            return
        try:
            p.window.width, p.window.height = 1440, 900
            p.window.min_width, p.window.min_height = 1180, 700
            p.window.icon = "icon.ico"
            p.window.prevent_close = True
            p.window.on_event = self._on_window
        except Exception:
            pass
        self.splash()

    def splash(self, msg="正在啟動會計資料庫…"):
        p = self.page
        self.status = ft.Text(msg, size=15, color="#DCE6F5")
        self.ring = ft.ProgressRing(color=T.GOLD, width=34, height=34, stroke_width=3)
        self.retry = ft.Row([T.btn("資料庫設定", ft.Icons.STORAGE, lambda e: self.db_settings(), kind="accent"),
                             T.btn("重試", ft.Icons.REFRESH, lambda e: self.splash(), bgcolor="#2B5BA0")],
                            visible=False, alignment=ft.MainAxisAlignment.CENTER)
        p.controls.clear()
        p.add(ft.Container(ft.Column([
            ft.Image(src="icon.png", width=108, height=108),
            ft.Text(APP_NAME, size=30, weight=ft.FontWeight.W_800, color=ft.Colors.WHITE),
            ft.Text("複式簿記 · 傳票過帳 · 財務報表", size=14, color="#9FB6D8"),
            ft.Container(height=10), self.ring, self.status, self.retry],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=10),
            expand=True, alignment=ft.Alignment.CENTER,
            gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                                       colors=[T.SIDEBAR_TOP, "#1E4D8C", "#0F766E"])))
        p.update()
        p.run_thread(self._boot)

    def _boot(self):
        try:
            log.info("boot mode=%s port=%s bin=%s", self.st.mode, self.st.port, self.st.mariadb_bin)
            if self.st.mode == "embedded":
                self.server = LocalDatabaseServer(self.st)
                self.server.start()
                # macOS 按 ⌘Q 或程式被結束時不一定會觸發視窗關閉事件 → 程式結束時一律停止資料庫
                import atexit
                atexit.register(self.shutdown)
                try:
                    import signal
                    signal.signal(signal.SIGTERM, lambda *a: (self.shutdown(), os._exit(0)))
                except Exception:
                    pass
            self.db = DB(self.st)
            self.db.prepare()
            self.st.save()
            self.books = Books(self.db)
            self.reports = Reports(self.books)
            self.ctx = T.Ctx(self)
            if self.st.extra.get("api_enabled"):
                try:
                    self.start_api()
                except Exception:
                    log.exception("api autostart")
            if self.st.extra.get("tunnel_enabled"):
                import threading as _t
                _t.Thread(target=self._autostart_tunnel, daemon=True).start()
            self.login()
        except Exception as e:
            log.exception("boot")
            self.ring.visible = False
            self.status.value = "資料庫啟動失敗：\n%s" % (explain_error(e) if self.st.mode == "server" else e)
            self.status.color = "#FFC9C9"
            self.retry.visible = True
            self.page.update()

    # ================================================================ 登入
    def login(self):
        p = self.page
        first = not self.books.has_users()
        uid = T.field("帳號", self.st.last_user or ("admin" if first else ""), width=320,
                      prefix_icon=ft.Icons.PERSON_OUTLINE)
        name = T.field("您的姓名", "系統管理員", width=320, visible=first, prefix_icon=ft.Icons.BADGE_OUTLINED)
        pw = T.field("密碼", "", width=320, password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK_OUTLINE,
                     autofocus=bool(uid.value))
        pw2 = T.field("再輸入一次密碼", "", width=320, password=True, visible=first, prefix_icon=ft.Icons.LOCK_OUTLINE)
        msg = ft.Text("", color=T.DANGER, size=13)

        def go(e=None):
            try:
                if first:
                    if pw.value != pw2.value:
                        raise BizError("兩次輸入的密碼不一樣")
                    self.books.create_first_admin(uid.value, name.value, pw.value)
                self.books.login(uid.value, pw.value)
            except BizError as ex:
                msg.value = str(ex)
                p.update()
                return
            self.st.last_user = self.books.uid
            self.st.save()
            self.main()

        pw.on_submit = go
        pw2.on_submit = go
        dev = os.environ.get("ACCT_DEV_LOGIN")          # 開發測試用：帳號:密碼，自動登入並開啟網址指定的畫面
        if dev and not first:
            u, _, w = dev.partition(":")
            self.books.login(u, w)
            self.main()
            route = (p.route or "").strip("/") or os.environ.get("ACCT_DEV_ROUTE", "")
            if route and self.find(route):
                self.go(route)
            return
        comp = self.books.company().get("name") or ""
        features = [(ft.Icons.EDIT_NOTE, "teal", "傳票登錄", "收、支、轉帳傳票，借貸自動檢核"),
                    (ft.Icons.FACT_CHECK, "amber", "審核過帳", "製單與審核分離，權限分級"),
                    (ft.Icons.INSIGHTS, "violet", "財務報表", "試算、損益、資產負債、現金流量"),
                    (ft.Icons.RECORD_VOICE_OVER, "green", "語音說明", "每一頁都能聽操作說明")]
        left = ft.Container(ft.Column([
            ft.Row([ft.Image(src="icon.png", width=64, height=64),
                    ft.Column([ft.Text("資料助秘", size=16, color="#9FB6D8"),
                               ft.Text(APP_SHORT, size=28, weight=ft.FontWeight.W_800, color=ft.Colors.WHITE)],
                              spacing=0)], spacing=14),
            ft.Container(height=24),
            ft.Text("讓每一筆帳，都清清楚楚。", size=22, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE),
            muted_light("單一公司的總帳會計：從傳票到財務報表，一次完成。"),
            ft.Container(height=20),
            *[ft.Container(ft.Row([T.icon_tile(ic, tone, 42), ft.Column([
                ft.Text(t, size=15, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE), muted_light(s, 12)],
                spacing=0)], spacing=14), padding=ft.Padding.symmetric(vertical=6))
              for ic, tone, t, s in features],
            ft.Container(expand=True),
            muted_light("v%s　系統開發：吳玉柱 先生 與 Claude AI Opus 5.5" % APP_VERSION, 11)],
            spacing=6), expand=5, padding=48,
            gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                                       colors=[T.SIDEBAR_TOP, "#1E4D8C", "#0F766E"]))
        form = ft.Column([
            T.icon_tile(ft.Icons.LOCK_PERSON, "blue", 60, radius=18),
            ft.Text("建立系統管理員" if first else "歡迎回來", size=26, weight=ft.FontWeight.W_800, color=T.TEXT),
            T.muted("第一次使用，請設定管理員帳號與密碼（至少 6 個字）" if first else (comp or "請登入以繼續")),
            ft.Container(height=6), uid, name, pw, pw2, msg,
            ft.FilledButton("建立並登入" if first else "登入", icon=ft.Icons.LOGIN, width=320, height=48,
                            on_click=go, bgcolor=T.PRIMARY,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12))),
            ft.Row([T.btn("資料庫設定", ft.Icons.STORAGE, lambda e: self.db_settings(), kind="ghost"),
                    T.btn("聽說明", ft.Icons.VOLUME_UP, lambda e: speaker.say_help("quickstart",
                                                                                 text_for("quickstart")[1]),
                          kind="ghost")], alignment=ft.MainAxisAlignment.CENTER, width=320),
            T.muted("資料庫：%s" % ("本機內建（自動啟動）" if self.st.mode == "embedded" else
                                  "%s:%s" % (self.st.host, self.st.port)), 11)],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12, tight=True)
        p.controls.clear()
        p.add(ft.Row([left, ft.Container(form, expand=4, alignment=ft.Alignment.CENTER, bgcolor=T.BG)],
                     expand=True, spacing=0))
        p.update()
        log.info("ui: login shown (first=%s)", first)

    # ================================================================ 主畫面
    def allowed(self, func, lvl):
        return not func or self.books.can(func, lvl)

    def main(self):
        p = self.page
        from . import mobile
        hide = mobile.DESKTOP_ONLY if self.mobile else set()
        self.groups = [(g, ic, tone, [it for it in items if self.allowed(it[3], it[4]) and it[0] not in hide])
                       for g, ic, tone, items in menu()]
        self.groups = [g for g in self.groups if g[3]]
        if self.mobile and T.MOBILE:
            self.expanded = set()
            mobile.main(self)
            return
        self.sidebar = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)
        u = self.books.user
        avatar = ft.Container(ft.Text(u["name"][:1], color=ft.Colors.WHITE, weight=ft.FontWeight.W_700),
                              width=36, height=36, border_radius=18, bgcolor=T.ACCENT, alignment=ft.Alignment.CENTER)
        side = ft.Container(ft.Column([
            ft.Container(ft.Row([ft.Image(src="icon.png", width=40, height=40),
                                 ft.Column([ft.Text("資料助秘", size=11, color="#9FB6D8"),
                                            ft.Text(APP_SHORT, size=17, weight=ft.FontWeight.W_800,
                                                    color=ft.Colors.WHITE, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)], spacing=0, expand=True)],
                                 spacing=10),
                         padding=ft.Padding.only(left=18, right=10, top=18, bottom=14)),
            ft.Divider(color="#2A4A78", height=1),
            ft.Container(self.sidebar, expand=True, padding=ft.Padding.symmetric(horizontal=10, vertical=8)),
            ft.Divider(color="#2A4A78", height=1),
            ft.Container(ft.Row([avatar, ft.Column([
                ft.Text(u["name"], color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.W_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(("系統管理員" if u["is_admin"] else u["role"]) or "使用者", color="#9FB6D8", size=11,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)],
                spacing=0, expand=True),
                ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, icon_color="#C9D6EA", items=[
                    ft.PopupMenuItem("變更密碼", icon=ft.Icons.KEY, on_click=lambda e: self.change_password()),
                    ft.PopupMenuItem("登出", icon=ft.Icons.LOGOUT, on_click=lambda e: self.logout())] +
                    ([ft.PopupMenuItem("更換會計電腦", icon=ft.Icons.LINK, on_click=lambda e: self._switch_server())]
                     if self.mobile else []))],
                spacing=10), padding=14)], spacing=0),
            width=248, gradient=ft.LinearGradient(begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
                                                 colors=[T.SIDEBAR_TOP, T.SIDEBAR_BOTTOM]))
        self.crumb = ft.Row(spacing=6)
        self.speak_btn = T.btn("本頁說明", ft.Icons.VOLUME_UP, lambda e: self.speak_page(), kind="outline")
        self.update_banner = ft.Container(visible=False)
        top = ft.Container(ft.Row([
            self.crumb, ft.Container(expand=True), self.update_banner,
            T.chip(rocdate.show(rocdate.today()), "slate", ft.Icons.CALENDAR_TODAY),
            self.speak_btn,
            ft.IconButton(ft.Icons.HELP_OUTLINE, icon_color=T.PRIMARY, tooltip="使用說明",
                          on_click=lambda e: self.go("help"))], spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=24, vertical=12), bgcolor=T.CARD,
            border=ft.Border.only(bottom=ft.BorderSide(1, T.LINE)))
        self.body = ft.Container(expand=True, padding=ft.Padding.only(left=24, right=24, top=18, bottom=14))
        p.controls.clear()
        layout = ft.Row([side, ft.Column([top, self.body], expand=True, spacing=0)], expand=True, spacing=0)
        p.add(ft.SafeArea(layout, expand=True) if self.mobile else layout)
        self.go("home")
        if self.mobile:                              # iPad：資料在電腦上，更新檢查走手機版的方式
            from . import mobile
            p.run_thread(mobile.check_update, self)
        else:
            threading.Thread(target=self._check_update, daemon=True).start()

    def _switch_server(self):
        from . import mobile
        mobile.switch_server(self)

    def render_sidebar(self):
        items = []
        for g, ic, tone, entries in self.groups:
            if len(entries) == 1:
                items.append(self._side_item(entries[0], tone, top=True))
                continue
            open_ = g in self.expanded
            items.append(ft.Container(
                ft.Row([ft.Icon(ic, size=18, color="#8FA9CF"),
                        ft.Text(g, size=13, color="#B7C8E2", weight=ft.FontWeight.W_600, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Icon(ft.Icons.EXPAND_MORE if open_ else ft.Icons.CHEVRON_RIGHT, size=18, color="#7F98BF")],
                       spacing=10),
                padding=ft.Padding.only(left=12, right=8, top=10, bottom=6), border_radius=8,
                on_click=lambda e, g=g: self.toggle_group(g)))
            if open_:
                items += [self._side_item(it, tone) for it in entries]
        self.sidebar.controls = items

    def _side_item(self, it, tone, top=False):
        sid, title, icon = it[0], it[1], it[2]
        sel = sid == self.current
        bg, fg = T.TONES[tone]
        return ft.Container(
            ft.Row([ft.Container(ft.Icon(icon, size=17, color=fg if sel else "#C9D6EA"), width=30, height=30,
                                 border_radius=9, alignment=ft.Alignment.CENTER,
                                 bgcolor=bg if sel else "#22FFFFFF"),
                    ft.Text(title, size=14, color=ft.Colors.WHITE if sel else "#D5E0F0", expand=True, tooltip=title,
                            weight=ft.FontWeight.W_700 if sel else ft.FontWeight.W_500, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)], spacing=12),
            padding=ft.Padding.only(left=12 if top else 22, right=8, top=6, bottom=6), border_radius=10,
            bgcolor="#2E5A93" if sel else None, ink=True, on_click=lambda e, s=sid: self.go(s),
            border=ft.Border.only(left=ft.BorderSide(3, T.GOLD)) if sel else None)

    def toggle_group(self, g):
        self.expanded ^= {g}
        self.render_sidebar()
        self.page.update()

    def find(self, sid):
        for g, ic, tone, entries in self.groups:
            for it in entries:
                if it[0] == sid:
                    return g, tone, it
        return None

    def go(self, sid, **kw):
        found = self.find(sid)
        if not found:
            self.ctx.toast("您沒有使用此功能的權限", True)
            return
        g, tone, it = found
        speaker.stop()
        self.current = sid
        self.expanded.add(g)
        self.crumb.controls = [T.icon_tile(it[2], tone, 32, radius=9), T.muted(g, 14),
                               ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=T.MUTED),
                               ft.Text(it[1], size=15, weight=ft.FontWeight.W_700, color=T.TEXT)]
        self.render_sidebar()
        if self.mobile and T.MOBILE:
            from . import mobile
            self.title.value = it[1]
            self.page.run_task(mobile.close_drawer, self.page)
            try:
                self.page.pop_dialog()           # 從彈出視窗按「修改／開啟」時先關閉視窗
            except Exception:
                pass
        try:
            content = build_screen(sid, self.ctx, **kw)
            if self.mobile and T.MOBILE:
                T.mobilize(content)
                content = ft.Column([content], scroll=ft.ScrollMode.AUTO, expand=True)
            self.body.content = content
        except Exception as e:
            log.exception("screen %s", sid)
            self.body.content = T.empty_state(ft.Icons.ERROR_OUTLINE, "畫面載入失敗", str(e))
        self.page.update()

    def speak_page(self):
        if speaker.playing():
            speaker.stop()
            return
        title, text = text_for(self.current)
        speaker.say_help(self.current, text)
        self.ctx.toast("🔊 正在播放：%s" % title)

    # ================================================================ 版本更新提示
    def _check_update(self):
        from ..maintenance import check_update
        try:
            info = check_update()
        except Exception as e:
            log.info("update check: %s", e)
            return
        if not info or info["version"] == self.st.skipped_version:
            return
        self.update_info = info
        self.update_banner.content = ft.Container(
            ft.Row([ft.Icon(ft.Icons.SYSTEM_UPDATE, color=ft.Colors.WHITE, size=16),
                    ft.Text("有新版本 v%s" % info["version"], color=ft.Colors.WHITE, size=13,
                            weight=ft.FontWeight.W_600)], spacing=6, tight=True),
            bgcolor=T.ACCENT, border_radius=20, padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            on_click=lambda e: self.go("update"), tooltip="按這裡更新")
        self.update_banner.visible = True
        try:
            self.page.update()
        except Exception:
            pass

    # ================================================================ 帳號
    def change_password(self):
        c = self.ctx
        old = T.field("目前密碼", "", password=True, can_reveal_password=True)
        new = T.field("新密碼（至少 6 個字）", "", password=True, can_reveal_password=True)
        new2 = T.field("再輸入一次新密碼", "", password=True, can_reveal_password=True)

        def save(e):
            if new.value != new2.value:
                c.toast("兩次輸入的新密碼不一樣", True)
                return
            if c.guard(self.books.change_password, old.value, new.value, ok="密碼已變更"):
                c.close()
        c.dialog("變更密碼", ft.Column([old, new, new2], tight=True, spacing=12),
                 [T.btn("取消", kind="ghost", on_click=lambda e: c.close()), T.btn("儲存", ft.Icons.SAVE, save)],
                 icon=ft.Icons.KEY, width=380)

    def logout(self):
        speaker.stop()
        self.books.logout()
        self.current = "home"
        if self.mobile:
            from . import mobile
            self.page.drawer = None
            mobile.login(self)
            return
        self.login()

    # ================================================================ 資料庫設定
    def db_settings(self):
        p, st = self.page, self.st
        mode = ft.RadioGroup(value=st.mode, content=ft.Column([
            ft.Radio(value="embedded", label="本機內建資料庫（建議；程式自動啟動與停止）"),
            ft.Radio(value="server", label="連到既有的 MariaDB 伺服器（公司伺服器或另一台電腦）")], spacing=0))
        host = T.field("伺服器位址", st.host if st.mode == "server" else "127.0.0.1", width=220)
        port = T.field("連接埠", str(st.port if st.mode == "server" else 3306), width=110)
        user = T.field("帳號", st.user if st.mode == "server" else "", width=170)
        pw = T.field("密碼", st.password if st.mode == "server" else "", width=220, password=True,
                     can_reveal_password=True)
        dbn = T.field("資料庫名稱", st.database, width=220)
        box = ft.Column([ft.Row([host, port]), ft.Row([user, pw]), dbn], visible=st.mode == "server", spacing=12)
        msg = ft.Text("", size=13, selectable=True)

        def on_mode(e):
            box.visible = mode.value == "server"
            p.update()
        mode.on_change = on_mode

        def test(e):
            from ..database import try_connect
            ok, text = try_connect(host.value.strip(), port.value or 3306, user.value.strip(), pw.value,
                                   dbn.value.strip() or "zms_accounting")
            msg.value, msg.color = text, T.SUCCESS if ok else T.DANGER
            p.update()

        def save(e):
            if mode.value == "server":
                if st.mode == "embedded":
                    st.extra["embedded_password"] = st.password
                try:
                    st.port = int(port.value or 3306)
                except ValueError:
                    msg.value, msg.color = "連接埠要是數字", T.DANGER
                    p.update()
                    return
                st.mode, st.host, st.user, st.password = "server", host.value.strip(), user.value.strip(), pw.value
                st.database = dbn.value.strip() or "zms_accounting"
            elif st.mode != "embedded":
                fresh = Settings()
                st.mode, st.host, st.user, st.port = "embedded", "127.0.0.1", "root", fresh.port
                st.password = st.extra.get("embedded_password") or Settings.load().password
                st.database = dbn.value.strip() or "zms_accounting"
            st.save()
            p.pop_dialog()
            self.shutdown()
            self.splash()

        T.Ctx.dialog(self, "資料庫設定", ft.Column([mode, box, msg], tight=True, spacing=12),
                     [T.btn("取消", kind="ghost", on_click=lambda e: p.pop_dialog()),
                      T.btn("測試連線", ft.Icons.WIFI_TETHERING, test, kind="outline"),
                      T.btn("儲存並重新連線", ft.Icons.SAVE, save)], icon=ft.Icons.STORAGE, width=560)

    # ================================================================ 關閉
    async def _on_window(self, e):
        if str(getattr(e, "type", "")).lower().endswith("close"):
            self.shutdown()
            await self.page.window.destroy()

    # ================================================================ 手機連線服務（電腦版）
    def start_api(self):
        from ..api import ApiServer
        if self.api and self.api.running:
            return
        self.api = ApiServer(self.db, port=int(self.st.extra.get("api_port") or 8765))
        self.api.start()

    def stop_api(self):
        self.stop_tunnel()
        if self.api:
            self.api.stop()
            self.api = None

    def _autostart_tunnel(self):
        try:
            self.start_tunnel()
        except Exception:
            log.exception("tunnel autostart")

    # ---- 外出連線（Cloudflare 通道）
    def start_tunnel(self, progress=None):
        from ..tunnel import Tunnel
        self.start_api()
        x = self.st.extra
        if getattr(self, "tunnel", None) and self.tunnel.running:
            return self.tunnel.url
        self.tunnel = Tunnel(self.api.port, x.get("tunnel_mode") or "quick", x.get("tunnel_token", ""),
                             x.get("tunnel_url", ""))
        url = self.tunnel.start(progress=progress)
        log.info("tunnel: %s %s", self.tunnel.mode, url)
        return url

    def stop_tunnel(self):
        t = getattr(self, "tunnel", None)
        if t:
            t.stop()
            self.tunnel = None
            log.info("tunnel: stopped")

    def shutdown(self):
        speaker.stop()
        try:
            self.stop_api()
        except Exception:
            pass
        try:
            if self.books and self.books.user:
                self.books.logout()
            if self.db:
                self.db.close()
        except Exception:
            pass
        if self.server:
            self.server.stop()
            self.server = None
            log.info("shutdown: database stopped")


def muted_light(text, size=13):
    return ft.Text(text, size=size, color="#A9BDDB")


def main(page: ft.Page):
    App(page).start()
