"""資料助秘之一般公司會計 — 程式進入點。

桌面版：python main.py
伺服器模式（不開視窗，只提供資料庫與手機連線）：python main.py --server [--port 8765]
網頁預覽（測試用）：設定環境變數 ACCT_WEB_PORT=8560 後執行。
"""
import os
import sys

if "--server" in sys.argv:
    from acct.headless import run
    port = sys.argv[sys.argv.index("--port") + 1] if "--port" in sys.argv else None
    run(port)
    sys.exit(0)

import flet as ft  # noqa: E402

from acct.settings import resource_dir  # noqa: E402
from acct.ui.shell import main  # noqa: E402

if __name__ == "__main__":
    if getattr(sys, "frozen", False) and os.name == "nt":
        # 讓工作列顯示本程式的圖示（而不是 Python／Flet 的）
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ZMS.Accounting")
        except Exception:
            pass
    assets = os.path.join(resource_dir(), "assets")
    port = os.environ.get("ACCT_WEB_PORT")
    if port:
        ft.run(main, view=None, port=int(port), host="127.0.0.1", assets_dir=assets)
    else:
        ft.run(main, assets_dir=assets)
