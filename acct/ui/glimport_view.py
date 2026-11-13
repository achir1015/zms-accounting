"""拋轉匯入：匯入「資料助秘之一般公司進銷存」與「資料助秘之一般公司人事薪資差勤」的拋轉檔，查看與取消匯入紀錄。"""
import json

import flet as ft

from .. import rocdate
from . import theme as T


class GLImport(ft.Column):
    def __init__(self, ctx):
        self.ctx = ctx
        self.grid = T.Grid([("batch_no", "拋轉批次", "s", 130), ("company_name", "來源公司", "s", 170),
                            ("period", "交易期間", "s", 170), ("voucher_count", "傳票張數", "s", 70),
                            ("total", "借貸金額", "n", 120), ("voucher_nos", "傳票號碼", "s", 220),
                            ("imported_by", "匯入人", "s", 80), ("at", "匯入時間", "s", 140), ("st", "狀態", "s", 90)],
                           on_pick=self.detail, empty="尚未匯入任何拋轉批次")
        tip = T.card(ft.Row([T.icon_tile(ft.Icons.SYNC_ALT, "teal", 44), ft.Column([
            ft.Text("兩種方式把進銷存、人事薪資的交易轉成傳票", size=15, weight=ft.FontWeight.W_700, color=T.TEXT),
            T.muted("① 在進銷存或人事薪資差勤的「會計拋轉」匯出拋轉檔（.zmsgl）→ 在這裡按「匯入拋轉檔」。"
                    "② 這台電腦打開「系統管理 → 手機連線」服務後，兩套系統都可以直接傳送，結果也會列在下面。", 12),
            T.muted("匯入的傳票是「未審核」，摘要前有 [進銷存] 或 [人事薪資]，請到審核過帳確認；同一批次不會重複匯入。"
                    "缺少的明細科目、客戶、廠商、部門會自動建立。", 12)], spacing=2, expand=True)], spacing=14),
            padding=14)
        super().__init__([T.page_header(ft.Icons.SYNC_ALT, "拋轉匯入（進銷存／人事薪資）",
                                        "匯入一般公司進銷存、人事薪資差勤系統產生的傳票", "teal",
                                        [T.btn("匯入拋轉檔", ft.Icons.UPLOAD_FILE, self.pick)]),
                          tip, self.grid], spacing=12, expand=True)
        self.load(refresh=False)

    def load(self, refresh=True):
        rows = self.ctx.books.gl_imports()
        for r in rows:
            r["period"] = "%s～%s" % (rocdate.show(r["date_from"]), rocdate.show(r["date_to"]))
            r["at"] = rocdate.show(r["imported_at"].date()) + r["imported_at"].strftime(" %H:%M")
            r["st"] = "已匯入" if r["status"] == 1 else "已取消"
            r["voucher_count"] = str(r["voucher_count"])
        self.grid.set_rows(rows)
        if refresh:
            self.update()

    async def pick(self, e):
        files = await ft.FilePicker().pick_files(dialog_title="選擇拋轉檔（進銷存／人事薪資）", allowed_extensions=["zmsgl", "json"],
                                                 with_data=T.MOBILE)
        if not files:
            return
        f = files[0]
        try:
            raw = f.bytes if f.bytes else open(f.path, "rb").read()
            data = json.loads(raw.decode("utf-8-sig"))
        except Exception as ex:
            self.ctx.toast("檔案讀取失敗：%s" % ex, True)
            return
        self.preview(data)

    def preview(self, data, allow_other=False):
        c = self.ctx
        try:
            pv = c.books.preview_gl_batch(data, allow_other_company=allow_other)
        except Exception as ex:
            msg = str(ex)
            if "不同" in msg and not allow_other:
                c.confirm("公司不同", msg + "\n\n確定這份拋轉檔要記到本公司的帳上嗎？",
                          lambda: self.preview(data, True), yes="仍要匯入")
                return
            c.toast(msg, True)
            return
        rows = [dict(date=v["date"], ref=v["ref"], v_type=v["v_type"], memo=v["memo"], total=v["total"])
                for v in pv["vouchers"]]
        g = T.Grid([("date", "日期", "d", 90), ("v_type", "類別", "vtype", 50), ("memo", "摘要", "s", 330),
                    ("total", "金額", "n", 110)], height=300)
        g.set_rows(rows)
        made = pv["created"]
        extra = []
        for k, title in (("accounts", "會自動新增科目"), ("partners", "會自動新增往來對象"), ("departments", "會自動新增部門")):
            if made[k]:
                extra.append(T.muted("%s：%s" % (title, "、".join(made[k][:12]) + ("…" if len(made[k]) > 12 else "")), 12))
        head = ft.Column([
            ft.Text("%s　批次 %s" % (pv.get("source") or "拋轉檔", pv.get("batch_no", "")), size=14,
                    weight=ft.FontWeight.W_700),
            T.muted("來源公司：%s　交易期間：%s～%s" % ((pv.get("company") or {}).get("name", ""),
                                                 _show(pv.get("date_from")), _show(pv.get("date_to"))), 12),
            ft.Row([T.chip("%d 張傳票" % pv["count"], "teal"), T.chip("借貸合計 %s" % T.amt(pv["total"]), "blue")]),
            *extra], spacing=4, tight=True)

        def go(e):
            res = c.guard(c.books.import_gl_batch, data, allow_other_company=allow_other)
            if res:
                c.close()
                nos = res.get("voucher_nos") or []
                c.toast("已匯入 %d 張傳票（%s）" % (len(nos), "%s～%s" % (nos[0], nos[-1]) if nos else ""))
                self.load()
        c.dialog("匯入拋轉檔", ft.Column([head, g], tight=True, spacing=10),
                 [T.btn("取消", kind="ghost", on_click=lambda e: c.close()),
                  T.btn("確定匯入", ft.Icons.DOWNLOAD_DONE, go)], icon=ft.Icons.SYNC_ALT, tone="teal", width=680)

    def detail(self, r):
        c = self.ctx
        made = json.loads(r.get("created_info") or "{}") if r.get("created_info") else {}
        lines = [T.muted("來源：%s　%s" % (r["source"], r["company_name"]), 13),
                 T.muted("交易期間：%s　傳票：%s（%s 張）" % (r["period"], r["voucher_nos"], r["voucher_count"]), 13),
                 T.muted("匯入：%s %s" % (r["imported_by"], r["at"]), 13)]
        for k, title in (("accounts", "自動新增科目"), ("partners", "自動新增往來"), ("departments", "自動新增部門")):
            if made.get(k):
                lines.append(T.muted("%s：%s" % (title, "、".join(made[k])), 12))
        actions = [T.btn("關閉", kind="ghost", on_click=lambda e: c.close())]
        if r["status"] == 1:
            def cancel():
                if c.guard(c.books.cancel_gl_import, r["batch_uid"], ok="已取消匯入並刪除該批傳票；請到來源系統（進銷存／人事薪資）取消拋轉"):
                    self.load()
            actions.insert(0, T.btn("取消匯入（刪除這批傳票）", ft.Icons.DELETE_OUTLINE,
                                    lambda e: (c.close(), c.confirm(
                                        "取消匯入", "會刪除這批 %s 張未審核傳票。已審核或過帳的傳票要先退回。確定嗎？"
                                        % r["voucher_count"], cancel)), kind="danger"))
        c.dialog("拋轉批次 %s" % r["batch_no"], ft.Column(lines, tight=True, spacing=6), actions,
                 icon=ft.Icons.SYNC_ALT, tone="teal", width=560)


def _show(v):
    try:
        return rocdate.show(rocdate.read(v)) if v else ""
    except ValueError:
        return str(v or "")
