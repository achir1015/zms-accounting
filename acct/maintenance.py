"""備份還原、版本更新、桌面捷徑。"""
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from . import APP_ID, APP_NAME, APP_VERSION, GITHUB_REPO

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# ================================================================ 備份／還原
def _tool(st, names):
    ext = ".exe" if os.name == "nt" else ""
    for n in names:
        p = os.path.join(st.mariadb_bin or "", n + ext)
        if st.mariadb_bin and os.path.isfile(p):
            return p
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    raise RuntimeError("找不到 MariaDB 工具程式：%s" % "／".join(names))


def _conn_args(st):
    return ["-h", st.host, "-P", str(st.port), "-u", st.user, "--default-character-set=utf8mb4"]


def backup(st, path):
    exe = _tool(st, ["mariadb-dump", "mysqldump"])
    p = subprocess.Popen([exe] + _conn_args(st) + ["--single-transaction", "--routines", st.database],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, MYSQL_PWD=st.password),
                         creationflags=NO_WINDOW)
    with gzip.open(path, "wb") as f:
        shutil.copyfileobj(p.stdout, f)
    err = p.stderr.read().decode("utf-8", "replace")
    if p.wait() != 0:
        os.remove(path)
        raise RuntimeError("備份失敗：" + err)
    return os.path.getsize(path)


def restore(st, path):
    exe = _tool(st, ["mariadb", "mysql"])
    p = subprocess.Popen([exe] + _conn_args(st) + [st.database], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=dict(os.environ, MYSQL_PWD=st.password), creationflags=NO_WINDOW)
    opener = gzip.open if path.lower().endswith(".gz") else open
    with opener(path, "rb") as f:
        shutil.copyfileobj(f, p.stdin)
    p.stdin.close()
    err = p.stderr.read().decode("utf-8", "replace")
    if p.wait() != 0:
        raise RuntimeError("還原失敗：" + err)


# ================================================================ 版本更新（GitHub Releases）
def _ver(s):
    out = []
    for part in (s or "0").lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    return tuple(out + [0] * (3 - len(out)))


def asset_suffix():
    if os.name == "nt":
        return "-Setup-"
    if sys.platform == "darwin":
        return ".dmg"
    return ""


def _latest_via_page(timeout):
    """GitHub API 有匿名次數限制（每小時 60 次／每個網路）；改從發佈頁的轉址取得最新版號（無次數限制）。"""
    req = urllib.request.Request("https://github.com/%s/releases/latest" % GITHUB_REPO, method="HEAD",
                                 headers={"User-Agent": APP_ID})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        final = r.geturl()                       # …/releases/tag/v1.2.3
    tag = final.rstrip("/").rsplit("/", 1)[-1]
    if "/tag/" not in final or not tag:
        raise RuntimeError("找不到發佈版本")
    ver = tag.lstrip("vV")
    assets = []
    if os.name == "nt":
        name = "%s-Setup-%s.exe" % (APP_ID, ver)
        assets = [dict(name=name, size=0, browser_download_url="https://github.com/%s/releases/download/%s/%s"
                       % (GITHUB_REPO, tag, name))]
    return dict(tag_name=tag, body="（更新內容請按「前往發佈頁」查看）", assets=assets, html_url=final)


def check_update(timeout=8):
    """回傳 None（已是最新）或 dict(version, notes, url, size, name)。"""
    req = urllib.request.Request("https://api.github.com/repos/%s/releases/latest" % GITHUB_REPO,
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": APP_ID})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rel = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code not in (403, 429):
            raise
        rel = _latest_via_page(timeout)
    tag = rel.get("tag_name", "")
    if _ver(tag) <= _ver(APP_VERSION):
        return None
    suffix = asset_suffix()
    asset = next((a for a in rel.get("assets", []) if suffix and suffix in a["name"]
                  and a["name"].lower().endswith((".exe", ".dmg"))), None)
    return dict(version=tag.lstrip("vV"), notes=rel.get("body") or "", url=asset["browser_download_url"] if asset
                else rel.get("html_url"), size=asset["size"] if asset else 0, name=asset["name"] if asset else "",
                page=rel.get("html_url"))


def download(url, progress=None):
    d = os.path.join(tempfile.gettempdir(), APP_ID + "-update")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, url.rsplit("/", 1)[-1])
    req = urllib.request.Request(url, headers={"User-Agent": APP_ID})
    with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress and total:
                progress(got / total)
    return path


def launch_installer(path):
    """Windows：靜默安裝新版（安裝程式會關閉本程式、更新後自動重新開啟）。"""
    if os.name == "nt":
        subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1"],
                         creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        subprocess.Popen(["open", path])


# ================================================================ 桌面捷徑
def create_desktop_shortcut():
    if os.name != "nt":
        raise RuntimeError("目前只支援 Windows 建立捷徑")
    exe = sys.executable if getattr(sys, "frozen", False) else None
    if not exe:
        raise RuntimeError("開發模式沒有執行檔，請在安裝版使用此功能")
    ps = ("$d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; "
          "$s=$w.CreateShortcut((Join-Path $d '%s.lnk')); $s.TargetPath='%s'; $s.WorkingDirectory='%s'; "
          "$s.IconLocation='%s,0'; $s.Description='%s'; $s.Save()"
          % (APP_NAME, exe, os.path.dirname(exe), exe, APP_NAME))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                       creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "建立捷徑失敗")
