"""系統管理：使用者與權限、公司設定、備份還原、版本更新與捷徑、操作紀錄。"""
import os
import threading
import time

import flet as ft

from .. import APP_NAME, APP_VERSION, maintenance, rocdate
from ..seed import FUNCS, ROLES
from ..settings import data_dir
from . import theme as T

FUNC_ICON = {"BAS": (ft.Icons.FOLDER_SPECIAL, "sky"), "VOU": (ft.Icons.EDIT_NOTE, "teal"),
             "APR": (ft.Icons.FACT_CHECK, "amber"), "LED": (ft.Icons.MENU_BOOK, "orange"),
             "FIN": (ft.Icons.INSIGHTS, "violet"), "CLS": (ft.Icons.EVENT_AVAILABLE, "pink"),
             "SYS": (ft.Icons.ADMIN_PANEL_SETTINGS, "rose")}
LEVELS = [("0", "無"), ("1", "查詢"), ("2", "維護")]


# ====================================================================== 使用者與權限
class Users(ft.Row):
    def __init__(self, ctx):
        self.ctx = ctx
        self.list = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        self.form = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        super().__init__([
            ft.Column([T.page_header(ft.Icons.ADMIN_PANEL_SETTINGS, "使用者與權限", "角色範本＋逐項權限", "rose",
                                     [T.btn("新增", ft.Icons.PERSON_ADD, lambda e: self.edit(None))]),
                       T.card(self.list, expand=True, padding=12)], width=400, spacing=12),
            T.card(self.form, expand=True, padding=20)], expand=True, spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.START)
        self.reload()
        self.edit(None, refresh=False)

    def reload(self):
        self.users = self.ctx.books.users()
        palette = ["#0FA294", "#1E4D8C", "#B45309", "#6D28D9", "#BE123C", "#0369A1"]
        self.list.controls = [ft.Container(ft.Row([
            ft.Container(ft.Text(u["name"][:1], color=ft.Colors.WHITE, weight=ft.FontWeight.W_700), width=40,
                         height=40, border_radius=20, alignment=ft.Alignment.CENTER, bgcolor=palette[i % 6]),
            ft.Column([ft.Text("%s（%s）" % (u["name"], u["uid"]), size=14, weight=ft.FontWeight.W_600),
                       T.muted("最近登入 %s" % T.show(u["last_login"]) if u["last_login"] else "尚未登入", 11)],
                      spacing=0, expand=True),
            T.chip("管理員" if u["is_admin"] else (u["role"] or "自訂"), "rose" if u["is_admin"] else "blue"),
            *([T.chip("停用", "slate")] if not u["active"] else [])], spacing=10),
            padding=10, border_radius=12, bgcolor="#F7F9FC", ink=True, on_click=lambda e, u=u: self.edit(u))
            for i, u in enumerate(self.users)]

    def edit(self, u, refresh=True):
        self.cur = u
        new = u is None
        u = u or {"uid": "", "name": "", "role": "會計人員", "is_admin": 0, "active": 1,
                  "perms": ROLES["會計人員"]}
        self.f_uid = T.field("帳號", u["uid"], read_only=not new, width=200)
        self.f_name = T.field("姓名", u["name"], width=200)
        self.f_role = T.dropdown("角色範本", [(k, k) for k in ROLES], u["role"] if u["role"] in ROLES else None,
                                 width=200, filterable=False, on_select=self.apply_role, blank="自訂")
        self.f_admin = T.switch("系統管理員（擁有全部權限）", u["is_admin"], on_change=lambda e: self.render_perms())
        self.f_active = T.switch("帳號啟用", u["active"])
        self.f_pw = T.field("密碼" if new else "重設密碼（不改請留空）", "", password=True, can_reveal_password=True,
                            width=260)
        self.perm_ctl = {}
        self.perm_box = ft.Column(spacing=6)
        for f, name, desc in FUNCS:
            seg = ft.SegmentedButton(segments=[ft.Segment(value=k, label=t) for k, t in LEVELS],
                                     selected=[str(u["perms"].get(f, 0))], show_selected_icon=False)
            self.perm_ctl[f] = seg
        self.render_perms(refresh=False)
        acts = [T.btn("儲存", ft.Icons.SAVE, lambda e: self.save(new))]
        if not new:
            acts.append(T.btn("刪除帳號", ft.Icons.DELETE_OUTLINE, lambda e: self.delete(), kind="danger"))
        self.form.controls = [
            ft.Row([T.icon_tile(ft.Icons.PERSON_ADD if new else ft.Icons.PERSON, "rose", 44),
                    ft.Text("新增使用者" if new else "修改 %s" % u["name"], size=18, weight=ft.FontWeight.W_700)]),
            ft.Row([self.f_uid, self.f_name, self.f_role], wrap=True), ft.Row([self.f_pw]),
            ft.Row([self.f_admin, self.f_active], spacing=24),
            ft.Text("功能權限", size=15, weight=ft.FontWeight.W_700), self.perm_box, ft.Row(acts, spacing=8)]
        if refresh:
            self.update()

    def render_perms(self, refresh=True):
        admin = self.f_admin.value
        self.perm_box.controls = [ft.Container(ft.Row([
            T.icon_tile(*FUNC_ICON[f], 36),
            ft.Column([ft.Text(name, size=14, weight=ft.FontWeight.W_600), T.muted(desc, 11)], spacing=0,
                      expand=True),
            T.chip("全部", "rose") if admin else self.perm_ctl[f]], spacing=12),
            padding=8, border_radius=12, bgcolor="#F7F9FC") for f, name, desc in FUNCS]
        if refresh:
            self.update()

    def apply_role(self, e):
        perms = ROLES.get(self.f_role.value)
        if perms:
            for f, seg in self.perm_ctl.items():
                seg.selected = [str(perms.get(f, 0))]
            self.f_admin.value = self.f_role.value == "系統管理員"
            self.render_perms()

    def save(self, new):
        perms = {f: int((seg.selected or ["0"])[0]) for f, seg in self.perm_ctl.items()}
        if self.ctx.guard(self.ctx.books.save_user, self.f_uid.value, self.f_name.value, self.f_role.value or "",
                          self.f_admin.value, self.f_active.value, perms, self.f_pw.value or None, new, ok="已儲存"):
            self.reload()
            self.edit(next((u for u in self.users if u["uid"] == self.f_uid.value.strip()), None))

    def delete(self):
        u = self.cur
        self.ctx.confirm("刪除帳號", "確定刪除 %s（%s）？有傳票紀錄的帳號請改為停用。" % (u["name"], u["uid"]),
                         lambda: self.ctx.guard(self.ctx.books.delete_user, u["uid"], ok="已刪除")
                         and (self.reload(), self.edit(None)), yes="刪除")


# ====================================================================== 公司設定
class Company(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        c = ctx.books.company()
        self.name = T.field("公司名稱", c.get("name"), width=360)
        self.tax = T.field("統一編號", c.get("tax_id"), width=160)
        self.owner = T.field("負責人", c.get("owner"), width=160)
        self.phone = T.field("電話", c.get("phone"), width=200)
        self.addr = T.field("地址", c.get("address"), width=540)
        self.fsm = T.dropdown("會計年度起始月", [(m, "%d 月" % m) for m in range(1, 13)], c.get("fiscal_start_month") or 1,
                              width=180, filterable=False)
        self.auto = T.switch("即時過帳：傳票存檔即過帳（小型公司、單人記帳適用）", c.get("auto_post"))
        self.sep = T.switch("製單與審核分離：製單人不能審核自己的傳票（內部控制建議開啟）", c.get("separate_approver"))
        super().__init__([
            T.page_header(ft.Icons.BUSINESS, "公司設定", "單一公司的基本資料與記帳規則", "rose"),
            T.card(ft.Column([
                ft.Row([T.icon_tile(ft.Icons.APARTMENT, "blue", 36), ft.Text("基本資料", size=16,
                                                                           weight=ft.FontWeight.W_700)]),
                ft.Row([self.name, self.tax, self.owner], wrap=True), ft.Row([self.phone, self.fsm], wrap=True),
                self.addr, ft.Divider(),
                ft.Row([T.icon_tile(ft.Icons.RULE, "amber", 36), ft.Text("記帳規則", size=16,
                                                                       weight=ft.FontWeight.W_700)]),
                self.auto, self.sep,
                ft.Row([T.btn("儲存", ft.Icons.SAVE, lambda e: self.save())])], spacing=14), padding=22)],
            spacing=14, expand=True, scroll=ft.ScrollMode.AUTO)

    def save(self):
        self.ctx.guard(self.ctx.books.save_company, name=self.name.value, tax_id=self.tax.value,
                       owner=self.owner.value, phone=self.phone.value, address=self.addr.value,
                       fiscal_start_month=int(self.fsm.value or 1), auto_post=int(self.auto.value),
                       separate_approver=int(self.sep.value), ok="公司設定已儲存")


# ====================================================================== 備份與還原
class Backup(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        st = ctx.app.st
        self.msg = T.muted("", 13)
        self.busy = ft.ProgressRing(width=22, height=22, visible=False)
        info = [("資料庫", "本機內建 MariaDB（連接埠 %s）" % st.port if st.mode == "embedded" else
                 "%s:%s" % (st.host, st.port)), ("資料庫名稱", st.database), ("資料夾", data_dir())]
        super().__init__([
            T.page_header(ft.Icons.BACKUP, "備份與還原", "建議每週備份，並另存到隨身碟或雲端硬碟", "rose"),
            ft.Row([
                action_card(ft.Icons.CLOUD_DOWNLOAD, "teal", "立即備份", "把全部會計資料壓縮成 .sql.gz 檔",
                            T.btn("選擇位置並備份", ft.Icons.BACKUP, self.backup, kind="accent")),
                action_card(ft.Icons.RESTORE, "rose", "從備份還原", "用備份檔覆蓋目前所有資料（無法復原）",
                            T.btn("選擇備份檔", ft.Icons.UPLOAD_FILE, self.restore, kind="danger")),
                action_card(ft.Icons.FOLDER_OPEN, "sky", "資料資料夾", "設定檔、資料庫與紀錄檔所在位置",
                            T.btn("開啟資料夾", ft.Icons.FOLDER_OPEN, lambda e: T.open_file(data_dir()),
                                  kind="outline"))], spacing=14),
            ft.Row([self.busy, self.msg]),
            T.card(ft.Column([ft.Row([T.muted(k, 13, width=90), ft.Text(v, size=13, selectable=True)])
                              for k, v in info], spacing=8), padding=18)], spacing=14, expand=True)

    async def backup(self, e):
        name = "會計備份_%s.sql.gz" % time.strftime("%Y%m%d_%H%M")
        path = await self.ctx.save_as(name, "gz")
        if not path:
            return
        if path.endswith(".gz") and not path.endswith(".sql.gz"):
            path = path[:-3] + ".sql.gz"
        self.busy.visible, self.msg.value = True, "備份中…"
        self.update()
        try:
            size = maintenance.backup(self.ctx.app.st, path)
            self.ctx.books.log("backup", os.path.basename(path))
            self.msg.value = "備份完成：%s（%.1f KB）" % (path, size / 1024)
            self.ctx.toast("備份完成")
        except Exception as ex:
            self.msg.value = str(ex)
            self.ctx.toast(str(ex), True)
        self.busy.visible = False
        self.update()

    async def restore(self, e):
        files = await ft.FilePicker().pick_files(dialog_title="選擇備份檔", allowed_extensions=["gz", "sql"])
        if not files:
            return
        path = files[0].path

        def go():
            self.busy.visible, self.msg.value = True, "還原中，請勿關閉程式…"
            self.update()
            try:
                maintenance.restore(self.ctx.app.st, path)
                self.ctx.books.log("restore", os.path.basename(path))
                self.ctx.toast("還原完成，請重新登入")
                self.ctx.app.logout()
            except Exception as ex:
                self.msg.value = str(ex)
                self.ctx.toast(str(ex), True)
                self.busy.visible = False
                self.update()
        self.ctx.confirm("從備份還原", "目前所有資料將被「%s」覆蓋，確定嗎？建議先備份目前資料。" % os.path.basename(path),
                         go, yes="還原")


def action_card(icon, tone, title, desc, button):
    return T.card(ft.Column([T.icon_tile(icon, tone, 52, radius=16), ft.Text(title, size=17,
                                                                         weight=ft.FontWeight.W_700),
                             T.muted(desc, 12), ft.Container(height=4), button], spacing=8), expand=True,
                  padding=20)


# ====================================================================== 版本更新與捷徑
class Update(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.status = ft.Column(spacing=10)
        self.bar = ft.ProgressBar(value=0, visible=False, color=T.ACCENT, bgcolor="#E6F4F1", bar_height=8,
                                  border_radius=4)
        super().__init__([
            T.page_header(ft.Icons.SYSTEM_UPDATE, "版本更新與捷徑", "程式開啟時會自動檢查新版本", "rose"),
            ft.Row([
                T.card(ft.Column([
                    ft.Row([ft.Image(src="icon.png", width=64, height=64),
                            ft.Column([ft.Text(APP_NAME, size=18, weight=ft.FontWeight.W_800),
                                       T.chip("目前版本 v%s" % APP_VERSION, "blue", ft.Icons.VERIFIED)], spacing=6)],
                           spacing=14),
                    self.status, self.bar,
                    ft.Row([T.btn("檢查更新", ft.Icons.REFRESH, lambda e: self.check())])], spacing=14),
                    expand=True, padding=22),
                T.card(ft.Column([
                    T.icon_tile(ft.Icons.SHORTCUT, "teal", 52, radius=16),
                    ft.Text("桌面捷徑", size=17, weight=ft.FontWeight.W_700),
                    T.muted("安裝時已建立桌面與開始功能表捷徑；如果不見了，按下面按鈕重建。", 12),
                    T.btn("重建桌面捷徑", ft.Icons.DESKTOP_WINDOWS, lambda e: self.shortcut(), kind="accent")],
                    spacing=10), width=340, padding=22)], spacing=14, vertical_alignment=ft.CrossAxisAlignment.START),
            T.card(ft.Column([ft.Text("系統資訊", size=15, weight=ft.FontWeight.W_700),
                              T.muted("系統開發：吳玉柱 先生 與 Claude AI Opus 5.5", 13),
                              T.muted("資料庫：MariaDB　介面：Flet　語音：微軟神經語音／Windows 內建語音", 13)],
                             spacing=6), padding=18)], spacing=14, expand=True, scroll=ft.ScrollMode.AUTO)
        info = ctx.app.update_info
        if info:
            self.show_info(info, refresh=False)
        else:
            self.status.controls = [T.muted("按「檢查更新」查詢是否有新版本。", 13)]

    def check(self):
        self.status.controls = [ft.Row([ft.ProgressRing(width=18, height=18), T.muted("檢查中…")])]
        self.update()

        def work():
            try:
                info = maintenance.check_update()
            except Exception as ex:
                self.status.controls = [ft.Row([ft.Icon(ft.Icons.WIFI_OFF, color=T.WARN),
                                                ft.Text("無法連線更新伺服器：%s" % ex, size=13, color=T.WARN)])]
                self.update()
                return
            if not info:
                self.status.controls = [ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=T.SUCCESS),
                                                ft.Text("已是最新版本", size=14, color=T.SUCCESS)])]
                self.update()
                return
            self.ctx.app.update_info = info
            self.show_info(info)
        self.ctx.page.run_thread(work)

    def show_info(self, info, refresh=True):
        notes = (info["notes"] or "").strip()[:900]
        self.status.controls = [
            ft.Row([T.icon_tile(ft.Icons.NEW_RELEASES, "green", 36),
                    ft.Text("有新版本 v%s" % info["version"], size=16, weight=ft.FontWeight.W_700, color=T.SUCCESS)]),
            ft.Container(ft.Text(notes or "（無更新說明）", size=13, selectable=True), bgcolor="#F7F9FC",
                         border_radius=10, padding=12),
            ft.Row([T.btn("下載並安裝", ft.Icons.DOWNLOAD, lambda e: self.install(info), kind="accent"),
                    T.btn("略過此版本", ft.Icons.SKIP_NEXT, lambda e: self.skip(info), kind="ghost")])]
        if refresh:
            self.update()

    def skip(self, info):
        self.ctx.app.st.skipped_version = info["version"]
        self.ctx.app.st.save()
        self.ctx.app.update_banner.visible = False
        self.ctx.toast("已略過 v%s" % info["version"])
        self.ctx.page.update()

    def install(self, info):
        if not info.get("name"):
            T.open_file(info["page"] or info["url"])
            return
        self.bar.visible, self.bar.value = True, 0
        self.update()

        def work():
            try:
                def prog(x):
                    self.bar.value = x
                    self.bar.update()
                path = maintenance.download(info["url"], prog)
            except Exception as ex:
                self.ctx.toast("下載失敗：%s" % ex, True)
                return
            self.ctx.books.log("update", info["version"])
            self.ctx.toast("下載完成，即將關閉程式並安裝新版…")
            time.sleep(1.2)
            maintenance.launch_installer(path)
            self.ctx.app.shutdown()
            self.ctx.page.run_task(self.ctx.page.window.destroy)
        self.ctx.page.run_thread(work)

    def shortcut(self):
        self.ctx.guard(maintenance.create_desktop_shortcut, ok="桌面捷徑已建立")


# ====================================================================== 操作紀錄
ACTIONS = {"login": "登入", "logout": "登出", "login_fail": "登入失敗", "password": "變更密碼",
           "voucher_new": "新增傳票", "voucher_edit": "修改傳票", "voucher_delete": "刪除傳票",
           "voucher_approve": "審核", "voucher_return": "退回", "voucher_post": "過帳", "voucher_unpost": "取消過帳",
           "voucher_void": "作廢", "period_close": "關帳", "period_reopen": "重新開帳", "year_close": "年度結帳",
           "year_reopen": "取消年度結帳", "user_save": "儲存使用者", "user_delete": "刪除使用者", "company": "公司設定",
           "account_save": "儲存科目", "account_delete": "刪除科目", "master_save": "儲存基本資料",
           "master_delete": "刪除基本資料", "template_save": "儲存常用分錄", "template_delete": "刪除常用分錄",
           "backup": "備份", "restore": "還原", "update": "版本更新", "budget_save": "儲存預算"}


class Audit(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.user = T.dropdown("使用者", [(u["uid"], u["name"]) for u in ctx.books.users()], "", width=180,
                               blank="全部", filterable=False, on_select=lambda e: self.load())
        self.grid = T.Grid([("at", "時間", "s", 150), ("uid", "使用者", "s", 90), ("act", "動作", "s", 110),
                            ("target", "對象", "s", 140), ("detail", "內容", "s", 380)])
        super().__init__([T.page_header(ft.Icons.HISTORY, "操作紀錄", "最近 1000 筆，供內部稽核", "rose",
                                        [self.user, ctx.export_button(self.grid, "操作紀錄")]),
                          self.grid], spacing=12, expand=True)
        self.load(refresh=False)

    def load(self, refresh=True):
        rows = self.ctx.books.audit(1000, self.user.value or "")
        for r in rows:
            r["act"] = ACTIONS.get(r["action"], r["action"])
            r["at"] = rocdate.show(r["at"].date()) + r["at"].strftime(" %H:%M:%S")
        self.grid.set_rows(rows)
        if refresh:
            self.update()


_ = threading
