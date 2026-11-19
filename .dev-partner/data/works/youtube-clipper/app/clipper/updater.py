"""アプリ内の更新（B-013）。

GitHub Releases のうちタグが `clipper-v` で始まる最新版を確認し、新しければインストーラーをダウンロードして
静かに上書きインストールする（/UPDATE=1 のときはインストーラーが最後にアプリを起動し直す）。
アプリが自分でダウンロードしたファイルには、ブラウザの「危険」の印（Mark of the Web）が付かない。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable

from . import paths

RELEASES_API = "https://api.github.com/repos/sakaryo0613-coder/bon2/releases?per_page=20"
TAG_PREFIX = "clipper-v"
ASSET = "clipper-setup.exe"
CACHE_SEC = 600
CHECK_TIMEOUT = 5
DL_TIMEOUT = 60
CHUNK = 1 << 20


def current_version() -> str:
    for p in (paths.resource("clipper/_version.json"), Path(__file__).with_name("_version.json")):
        try:
            return str(json.loads(p.read_text(encoding="utf-8-sig"))["version"])
        except (OSError, ValueError, KeyError):
            continue
    return "dev"


def parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in str(v).lstrip("v").split("."))
    except ValueError:
        return ()


def is_newer(latest: str, current: str) -> bool:
    """ソースから動かしている（dev）ときは更新を出さない（git で更新するため）。"""
    a, b = parse_version(latest), parse_version(current)
    return bool(a) and bool(b) and a > b


def pick_latest(releases: list[dict]) -> dict | None:
    best = None
    for r in releases or []:
        tag = str(r.get("tag_name", ""))
        if not tag.startswith(TAG_PREFIX) or r.get("draft") or r.get("prerelease"):
            continue
        asset = next((a for a in r.get("assets", []) if a.get("name") == ASSET), None)
        if not asset or not parse_version(tag[len(TAG_PREFIX):]):
            continue
        ver = tag[len(TAG_PREFIX):]
        if best is None or parse_version(ver) > parse_version(best["latest"]):
            digest = str(asset.get("digest") or "")
            best = {"latest": ver, "tag": tag, "url": asset.get("browser_download_url"), "size": int(asset.get("size") or 0),
                    "sha256": digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "",
                    "notes": str(r.get("body") or "")[:500], "published": r.get("published_at", "")}
    return best


def _fetch_json(url: str):
    if "://" not in url:                       # テスト用: ファイルのパス
        return json.loads(Path(url).read_text(encoding="utf-8-sig"))
    req = urllib.request.Request(url, headers={"User-Agent": "clipper-updater", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8-sig"))


def _launch_installer(exe: Path) -> None:
    args = [str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/UPDATE=1"]
    flags = 0
    if paths.IS_WIN:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # アプリが終わっても動き続ける
    subprocess.Popen(args, close_fds=True, creationflags=flags)


class Updater:
    def __init__(self, url: str | None = None, fetch: Callable = _fetch_json, launcher: Callable = _launch_installer,
                 exit_fn: Callable | None = None, version: str | None = None):
        self.url = url or os.environ.get("CLIPPER_UPDATE_URL") or RELEASES_API
        self.fetch, self.launcher = fetch, launcher
        self.exit_fn = exit_fn or (lambda: os._exit(0))
        self.version = version or current_version()
        self._cache: tuple[float, dict] | None = None
        self.state = {"running": False, "phase": "", "done": 0, "total": 0, "error": ""}

    def check(self, force: bool = False) -> dict:
        if not force and self._cache and time.time() - self._cache[0] < CACHE_SEC:
            return self._cache[1]
        res = {"current": self.version, "available": False}
        try:
            info = pick_latest(self.fetch(self.url))
            if info:
                res.update(info, available=is_newer(info["latest"], self.version))
        except Exception as e:  # オフラインなど。画面には出さない
            res["error"] = f"{type(e).__name__}: {e}"[:200]
        self._cache = (time.time(), res)
        return res

    # ---------------------------------------------------------- ダウンロードと上書き
    def download(self, info: dict, dest_dir: Path | None = None) -> Path:
        dest_dir = Path(dest_dir or paths.local_data_dir() / "updates")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"clipper-setup-{info['latest']}.exe"
        part = dest.with_suffix(".part")
        self.state.update(phase="download", done=0, total=info.get("size", 0), error="")
        h = hashlib.sha256()
        url = info["url"]
        if "://" not in url:                      # テスト用: ファイルのパス
            src = open(url, "rb")
        else:
            src = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "clipper-updater"}), timeout=DL_TIMEOUT)
        with src, open(part, "wb") as f:
            while True:
                chunk = src.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                self.state["done"] += len(chunk)
        size = part.stat().st_size
        if size == 0 or (info.get("size") and size != info["size"]):
            part.unlink(missing_ok=True)
            raise RuntimeError(f"ダウンロードしたファイルの大きさが合いません（{size} / {info.get('size')} バイト）")
        if info.get("sha256") and h.hexdigest() != info["sha256"]:
            part.unlink(missing_ok=True)
            raise RuntimeError("ダウンロードしたファイルが壊れています（sha256 が一致しません）")
        part.replace(dest)
        return dest

    def apply(self, info: dict | None = None, wait: bool = False) -> bool:
        """更新を始める。成功するとインストーラーを起動し、1秒後にアプリを終了する。失敗したら今の版のまま。"""
        if self.state["running"]:
            return False
        info = info or self.check(force=True)
        if not info.get("available"):
            self.state.update(error="新しい版はありません")
            return False
        self.state.update(running=True, error="")

        def run():
            try:
                exe = self.download(info)
                self.state.update(phase="install")
                self.launcher(exe)
                self.state.update(phase="restarting")
                threading.Timer(1.0, self.exit_fn).start()
            except Exception as e:
                self.state.update(error=str(e)[:300], phase="")
            finally:
                self.state["running"] = False
        t = threading.Thread(target=run, daemon=True)
        t.start()
        if wait:
            t.join()
        return True
