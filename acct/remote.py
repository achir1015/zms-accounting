"""手機端：用與電腦版相同介面（Books／Reports）透過 API 存取會計資料。

畫面程式只要拿到 RemoteBooks／RemoteReports，就和電腦版一樣呼叫 ctx.books.xxx()。
權限判斷（can／level／need）在手機端先做一次（決定選單），電腦端每次呼叫再嚴格檢查一次。
"""
import urllib.error
import urllib.request

from . import APP_ID, wire
from .books import BizError
from .seed import FUNC_NAMES


class ConnectionLost(BizError):
    pass


class Client:
    def __init__(self, url):
        url = (url or "").strip().rstrip("/")
        if url and "://" not in url:
            url = "http://" + url
        if url.count(":") == 1 and url.startswith("http://"):
            url += ":8765"                       # 只輸入 IP 時補上預設連接埠
        self.url = url
        self.token = ""
        self.on_relogin = None

    def _post(self, path, body, timeout=25):
        req = urllib.request.Request(self.url + path, data=wire.dumps(body), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": APP_ID,
                                              "Authorization": "Bearer " + self.token})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return wire.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                out = wire.loads(e.read())
            except Exception:
                out = {"error": "HTTP %s" % e.code}
            if out.get("relogin") and self.on_relogin:
                self.on_relogin(out.get("error"))
            raise BizError(out.get("error") or "HTTP %s" % e.code)
        except (urllib.error.URLError, OSError) as e:
            raise ConnectionLost("連不到會計電腦（%s）。請確認電腦已開啟會計系統的手機連線、網路正常。" %
                                 getattr(e, "reason", e))

    def ping(self, timeout=6):
        req = urllib.request.Request(self.url + "/api/ping", headers={"User-Agent": APP_ID})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return wire.loads(r.read())
        except Exception as e:
            raise ConnectionLost("連不到 %s：%s" % (self.url, getattr(e, "reason", e)))

    def tts(self, text):
        import base64
        out = self._post("/api/tts", {"text": text}, timeout=30)
        if "biz" in out:
            raise BizError(out["biz"])
        return base64.b64decode(out["mp3"])

    def call(self, obj, method, args, kwargs):
        out = self._post("/api/call", {"obj": obj, "method": method, "args": list(args), "kwargs": kwargs})
        if "biz" in out:
            raise BizError(out["biz"])
        return out


class RemoteBooks:
    def __init__(self, client: Client):
        self._c = client
        self.user = None
        self.perms = {}
        self.server = {}

    # ----- 與 Books 相同的登入／權限介面（本地判斷，電腦端會再檢查）
    @property
    def uid(self):
        return self.user["uid"] if self.user else ""

    def has_users(self):
        return True                               # 手機不能建立第一位管理員

    def login(self, uid, pw):
        out = self._c._post("/api/login", {"uid": (uid or "").strip(), "pw": pw or ""})
        self._c.token = out["token"]
        self.user, self.perms, self.server = out["user"], out["perms"], out.get("server", {})
        return self.user

    def logout(self):
        if self._c.token:
            try:
                self._c._post("/api/logout", {}, timeout=5)
            except Exception:
                pass
        self._c.token = ""
        self.user, self.perms = None, {}

    def level(self, func):
        if not self.user:
            return 0
        if self.user.get("is_admin"):
            return 2
        return int(self.perms.get(func, 0))

    def can(self, func, lvl=1):
        return self.level(func) >= lvl

    def need(self, func, lvl=2):
        if not self.can(func, lvl):
            raise BizError("您沒有「%s」的%s權限" % (FUNC_NAMES.get(func, func), "維護" if lvl >= 2 else "查詢"))

    @staticmethod
    def apply_template(tpl, amount):
        from .books import Books
        return Books.apply_template(tpl, amount)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def remote(*args, **kwargs):
            out = self._c.call("books", name, args, kwargs)
            self.user, self.perms = out.get("user", self.user), out.get("perms", self.perms)
            return out["result"]
        return remote


class RemoteReports:
    def __init__(self, client: Client):
        self._c = client

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **kw: self._c.call("reports", name, a, kw)["result"]
