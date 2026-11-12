"""手機連線服務：電腦版開啟後，手機 App 透過這個 API 使用會計資料。

* 手機不直接連資料庫；每個請求都在電腦端用該使用者的帳號與權限執行 Books／Reports 的方法。
* 登入：POST /api/login {uid, pw} → token；之後 POST /api/call {obj, method, args, kwargs}，標頭 Authorization: Bearer token
* 每次呼叫都重新讀取使用者狀態與權限（電腦端停用帳號或改權限，立即生效）。
* 登入失敗太多次會暫時封鎖該來源；工作階段閒置 12 小時失效。
"""
import inspect
import logging
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import APP_NAME, APP_VERSION, wire
from .books import BizError, Books
from .reports import Reports

log = logging.getLogger("acct")
SESSION_IDLE = 12 * 3600
FAIL_LIMIT, FAIL_WINDOW = 8, 15 * 60
API_VERSION = 1

# 不開放給手機的方法
DENY = {"login", "logout", "create_first_admin", "log", "db"}


def allowed_methods(cls):
    out = set()
    for name, fn in inspect.getmembers(cls):
        if name.startswith("_") or name in DENY or not callable(fn):
            continue
        out.add(name)
    return out


BOOKS_METHODS = allowed_methods(Books)
REPORTS_METHODS = allowed_methods(Reports)


def client_ip(peer, headers):
    """來源 IP：經 Cloudflare 通道進來的請求都來自本機，才採信 Cloudflare 提供的真實 IP 標頭
    （區網直接連線不採信標頭，避免偽造來繞過登入封鎖）。"""
    if peer in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
        real = headers.get("Cf-Connecting-Ip") or (headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return real or peer
    return peer


def public_user(u):
    return {k: v for k, v in (u or {}).items() if k != "pw_hash"}


class Session:
    def __init__(self, books):
        self.books = books
        self.reports = Reports(books)
        self.seen = time.time()


class ApiServer:
    def __init__(self, db, port=8765, host="0.0.0.0"):
        self.db = db
        self.port = port
        self.host = host
        self.sessions = {}
        self.fails = {}
        self.lock = threading.Lock()
        self.httpd = None
        self.thread = None
        self.requests = 0

    # ---------------------------------------------------------------- 啟停
    def start(self):
        if self.httpd:
            return
        api = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ZMSAccounting"

            def log_message(self, fmt, *a):
                pass

            def _send(self, code, obj):
                body = wire.dumps(obj)
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path.rstrip("/") in ("", "/api/ping"):
                    return self._send(200, api.ping())
                self._send(404, {"error": "not found"})

            def do_POST(self):
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 20 * 1024 * 1024:
                        return self._send(413, {"error": "資料太大"})
                    body = wire.loads(self.rfile.read(n) or b"{}")
                    ip = client_ip(self.client_address[0], self.headers)
                    if self.path == "/api/login":
                        code, out = api.login(body, ip)
                    elif self.path == "/api/call":
                        tok = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
                        code, out = api.call(tok, body)
                    elif self.path == "/api/tts":
                        tok = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
                        code, out = api.tts(tok, body)
                    elif self.path == "/api/logout":
                        tok = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
                        code, out = api.logout(tok)
                    else:
                        code, out = 404, {"error": "not found"}
                except Exception as e:
                    log.exception("api")
                    code, out = 500, {"error": "伺服器錯誤：%s" % e}
                finally:
                    api.db.close()           # 每個請求用完就關閉此執行緒的資料庫連線
                self._send(code, out)

        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        log.info("api: listening on %s:%s", self.host, self.port)

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
            self.sessions.clear()
            log.info("api: stopped")

    @property
    def running(self):
        return self.httpd is not None

    # ---------------------------------------------------------------- 處理
    def ping(self):
        comp = ""
        try:
            comp = (Books(self.db).company() or {}).get("name", "")
        except Exception:
            pass
        finally:
            self.db.close()
        return {"app": APP_NAME, "version": APP_VERSION, "api": API_VERSION, "company": comp}

    def _blocked(self, key, limit=FAIL_LIMIT):
        now = time.time()
        with self.lock:
            lst = [t for t in self.fails.get(key, []) if now - t < FAIL_WINDOW]
            self.fails[key] = lst
            return len(lst) >= limit

    def login(self, body, ip):
        uid_key = "uid:" + str(body.get("uid", "")).strip().lower()
        if self._blocked(ip) or self._blocked(uid_key, FAIL_LIMIT + 4):
            return 429, {"error": "登入失敗次數太多，請 15 分鐘後再試"}
        b = Books(self.db)
        try:
            b.login(body.get("uid", ""), body.get("pw", ""))
        except BizError as e:
            with self.lock:
                now = time.time()
                self.fails.setdefault(ip, []).append(now)
                self.fails.setdefault(uid_key, []).append(now)   # 同一帳號從不同 IP 猜密碼也會被擋
            return 401, {"error": str(e)}
        b.log("mobile_login", b.uid, ip)
        tok = secrets.token_urlsafe(32)
        with self.lock:
            self._expire()
            self.sessions[tok] = Session(b)
        return 200, {"token": tok, "user": public_user(b.user), "perms": b.perms, "server": self.ping()}

    def logout(self, tok):
        with self.lock:
            s = self.sessions.pop(tok, None)
        if s:
            s.books.log("mobile_logout", s.books.uid)
        return 200, {"ok": True}

    def tts(self, tok, body):
        """手機的「朗讀重點」：由電腦產生語音 MP3 傳回（手機不必安裝語音套件）。"""
        with self.lock:
            ok = tok in self.sessions
        if not ok:
            return 401, {"error": "連線已逾時，請重新登入", "relogin": True}
        import base64

        from .voice import Speaker
        text = str(body.get("text", ""))[:1500]
        path = Speaker._neural(text) if text else ""
        if not path:
            return 200, {"biz": "電腦端無法產生語音（需要網路）"}
        with open(path, "rb") as f:
            return 200, {"mp3": base64.b64encode(f.read()).decode("ascii")}

    def _expire(self):
        now = time.time()
        for t in [t for t, s in self.sessions.items() if now - s.seen > SESSION_IDLE]:
            self.sessions.pop(t, None)

    def call(self, tok, body):
        with self.lock:
            s = self.sessions.get(tok)
            if s and time.time() - s.seen > SESSION_IDLE:
                self.sessions.pop(tok, None)
                s = None
        if not s:
            return 401, {"error": "連線已逾時，請重新登入", "relogin": True}
        s.seen = time.time()
        b = s.books
        # 每次都重新讀取使用者狀態與權限
        u = self.db.row("SELECT * FROM users WHERE uid=%s", (b.uid,))
        if not u or not u["active"]:
            with self.lock:
                self.sessions.pop(tok, None)
            return 401, {"error": "帳號已停用", "relogin": True}
        b.user = u
        b.perms = {r["func"]: r["lvl"] for r in self.db.rows("SELECT func, lvl FROM user_perms WHERE uid=%s",
                                                              (u["uid"],))}
        obj, method = body.get("obj"), body.get("method", "")
        allowed = BOOKS_METHODS if obj == "books" else REPORTS_METHODS if obj == "reports" else set()
        if method not in allowed:
            return 403, {"error": "不允許的操作：%s" % method}
        target = b if obj == "books" else s.reports
        self.requests += 1
        try:
            result = getattr(target, method)(*body.get("args", []), **body.get("kwargs", {}))
            return 200, {"result": result, "user": public_user(b.user), "perms": b.perms}
        except (BizError, ValueError) as e:
            return 200, {"biz": str(e)}


def lan_addresses():
    """這台電腦在區域網路上的 IP（給手機連線用）。"""
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips, key=lambda x: (not x.startswith("192.168."), x))
