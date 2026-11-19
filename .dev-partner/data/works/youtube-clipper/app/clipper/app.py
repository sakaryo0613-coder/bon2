"""アプリのサーバー（標準ライブラリのみ・127.0.0.1 だけで待ち受け）。

画面:
  /                 ホーム（動画を選ぶ → 候補を作る、最近の作業、設定）
  /review?w=<id>    レビュー（採否・伸縮・書き出し）
API:
  GET  /api/home                    最近の作業・設定・実行中の処理
  POST /api/pick      {kind}        Windows 標準のファイル選択画面を出し、選ばれたパスを返す
  POST /api/upload?name=…           ドラッグ＆ドロップされた動画を作業用にコピーする
  POST /api/jobs      {video,subs,credit}   候補づくりを始める
  GET  /api/jobs/<id>               進み具合
  GET  /api/w/<id>/state, POST /api/w/<id>/decision, GET|POST /api/w/<id>/render
  GET  /media/w/<id>/source         動画（Range 対応）
  POST /api/open      {w}           出力フォルダを開く
  POST /api/config    {credit, api_key}
  POST /api/ping                    画面が開いていることの通知（アプリの自動終了に使う）
"""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import paths
from .pipeline import build, workdir_for
from .workdir import Workdir

HERE = Path(__file__).resolve().parent


def page(name: str) -> bytes:
    p = paths.resource(f"clipper/{name}")
    return (p if p.exists() else HERE / name).read_bytes()


def native_pick(kind: str) -> str:
    """Windows 標準のファイル選択画面（tkinter）。キャンセルなら空文字。"""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    if kind == "subs":
        types = [("字幕ファイル", "*.srt *.vtt"), ("すべてのファイル", "*.*")]
        title = "字幕ファイルを選ぶ（YouTube Studio からダウンロードした .srt など）"
    else:
        types = [("動画ファイル", "*.mp4 *.mov *.mkv *.webm *.m4v"), ("すべてのファイル", "*.*")]
        title = "切り抜く動画を選ぶ"
    path = filedialog.askopenfilename(parent=root, title=title, filetypes=types)
    root.destroy()
    return path or ""


def open_folder(p: Path) -> None:
    if paths.IS_WIN:
        os.startfile(str(p))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])


class App:
    def __init__(self, home: Path | None = None, render_opts: dict | None = None, idle_timeout: float | None = None):
        self.home = Path(home or paths.home_dir())
        self.home.mkdir(parents=True, exist_ok=True)
        self.render_opts = render_opts or {}
        self.idle_timeout = idle_timeout
        self.last_ping = time.time()
        self.jobs: dict[str, dict] = {}
        self.extra: dict[str, Path] = {}
        self.wds: dict[str, Workdir] = {}
        self.picker = native_pick        # テストで差し替える
        self.opener = open_folder        # テストで差し替える
        self.lock = threading.Lock()
        self.server: ThreadingHTTPServer | None = None
        self.stopped = False

    # ------------------------------------------------------------ 作業フォルダ
    def register(self, path: Path) -> str:
        path = Path(path).resolve()
        wid = path.name
        if wid in self.extra and self.extra[wid] != path:
            wid = f"{path.name}-{abs(hash(str(path))) % 10000}"
        self.extra[wid] = path
        return wid

    def workdirs(self) -> dict[str, Path]:
        found = {p.name: p for p in self.home.glob("*.clipper") if (p / "candidates.json").exists()}
        found.update({k: v for k, v in self.extra.items() if (v / "candidates.json").exists()})
        return found

    def wd(self, wid: str) -> Workdir:
        p = self.workdirs().get(wid)
        if not p:
            raise KeyError(wid)
        if wid not in self.wds or self.wds[wid].path != p:
            self.wds[wid] = Workdir(p)
        return self.wds[wid]

    def recent(self) -> list[dict]:
        out = []
        for wid, p in self.workdirs().items():
            w = self.wd(wid)
            dec = w.read("decisions.json", {"clips": {}})["clips"]
            meta = w.meta
            out.append({"id": wid, "title": meta.get("title", wid), "duration": meta.get("duration", 0),
                        "updated": (p / "decisions.json").stat().st_mtime if (p / "decisions.json").exists() else 0,
                        "n": len(dec), "accepted": sum(1 for d in dec.values() if d["status"] == "accepted"),
                        "pending": sum(1 for d in dec.values() if d["status"] == "pending"),
                        "outputs": len(list((p / "out").glob("*.mp4"))) if (p / "out").exists() else 0})
        return sorted(out, key=lambda r: -r["updated"])

    # ------------------------------------------------------------ 候補づくり
    def start_job(self, video: str, subs: str = "", credit: str = "") -> dict:
        vid = Path(video)
        if not vid.exists():
            raise FileNotFoundError(f"動画が見つかりません: {video}")
        if subs and not Path(subs).exists():
            raise FileNotFoundError(f"字幕ファイルが見つかりません: {subs}")
        jid = uuid.uuid4().hex[:8]
        wdp = workdir_for(vid, self.home)
        job = {"id": jid, "stage": "prepare", "pct": 0, "message": "準備しています", "done": False, "error": "",
               "workdir": wdp.name, "started": time.time(), "video": vid.name}
        self.jobs[jid] = job

        def progress(stage, pct, msg):
            job.update(stage=stage, pct=round(float(pct), 1), message=msg)

        def run():
            try:
                build(vid, wdp, Path(subs) if subs else None, credit=credit, progress=progress, log=lambda *a: None)
                job["workdir"] = self.register(wdp)
                job["done"] = True
            except Exception as e:  # 画面にそのまま出し、詳細はログに残す
                job["error"] = f"{type(e).__name__}: {e}"
                job["trace"] = traceback.format_exc()[-2000:]
                import logging
                logging.getLogger("clipper").error("job %s failed (%s): %s\n%s", jid, vid.name, job["error"], job["trace"])
        threading.Thread(target=run, daemon=True).start()
        return job

    def busy(self) -> bool:
        return (any(not j["done"] and not j["error"] for j in self.jobs.values())
                or any(w.progress["running"] for w in self.wds.values()))

    # ------------------------------------------------------------ 自動終了
    def watchdog(self):
        while self.server:
            time.sleep(1)
            if self.idle_timeout and time.time() - self.last_ping > self.idle_timeout and not self.busy():
                self.stopped = True
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body: bytes, ctype: str, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, code=200):
            self._send(json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8", code)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def _wid(self, part: str) -> str:
            return unquote(part)

        def do_GET(self):
            u = urlparse(self.path)
            parts = [p for p in u.path.split("/") if p]
            app.last_ping = time.time()
            try:
                if u.path in ("/", "/index.html"):
                    return self._send(page("home.html"), "text/html; charset=utf-8")
                if u.path == "/review":
                    return self._send(page("review.html"), "text/html; charset=utf-8")
                if u.path == "/api/home":
                    cfg = paths.load_config()
                    return self._json({"recent": app.recent(), "home": str(app.home), "log": str(paths.local_data_dir() / "clipper.log"),
                                       "config": {"credit": cfg.get("credit", ""), "has_api_key": bool(cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY"))},
                                       "jobs": [j for j in app.jobs.values() if not j["done"] and not j["error"]]})
                if parts[:2] == ["api", "jobs"] and len(parts) == 3:
                    j = app.jobs.get(parts[2])
                    return self._json({k: v for k, v in j.items() if k != "trace"} if j else {"error": "unknown job"}, 200 if j else 404)
                if parts[:2] == ["api", "w"] and len(parts) == 4:
                    w = app.wd(self._wid(parts[2]))
                    if parts[3] == "state":
                        return self._json(w.state())
                    if parts[3] == "render":
                        return self._json(w.progress)
                if parts[:2] == ["media", "w"] and len(parts) == 4 and parts[3] == "source":
                    return self._media(app.wd(self._wid(parts[2])).source())
                return self._json({"error": "not found"}, 404)
            except KeyError:
                return self._json({"error": "作業が見つかりません"}, 404)

        def do_POST(self):
            u = urlparse(self.path)
            parts = [p for p in u.path.split("/") if p]
            app.last_ping = time.time()
            try:
                if u.path == "/api/ping":
                    return self._json({"ok": True})
                if u.path == "/api/pick":
                    kind = self._body().get("kind", "video")
                    try:
                        return self._json({"path": app.picker(kind)})
                    except Exception as e:   # 画面のない環境など。ドラッグ＆ドロップを案内する
                        return self._json({"path": "", "error": f"ファイルを選ぶ画面を開けませんでした（{type(e).__name__}）。動画をこの枠にドラッグしてください。"})
                if u.path == "/api/upload":
                    return self._upload(parse_qs(u.query).get("name", ["video.mp4"])[0])
                if u.path == "/api/jobs":
                    b = self._body()
                    if b.get("credit") is not None:
                        cfg = paths.load_config(); cfg["credit"] = b["credit"]; paths.save_config(cfg)
                    return self._json(app.start_job(b.get("video", ""), b.get("subs", ""), b.get("credit", "")))
                if u.path == "/api/open":
                    w = app.wd(self._body()["w"])
                    out = w.path / "out"
                    out.mkdir(exist_ok=True)
                    app.opener(out)
                    return self._json({"ok": True, "path": str(out)})
                if u.path == "/api/config":
                    b = self._body(); cfg = paths.load_config()
                    for k in ("credit", "api_key"):
                        if k in b:
                            cfg[k] = b[k]
                    paths.save_config(cfg)
                    if b.get("api_key"):
                        os.environ["ANTHROPIC_API_KEY"] = b["api_key"]
                    return self._json({"ok": True})
                if parts[:2] == ["api", "w"] and len(parts) == 4:
                    w = app.wd(self._wid(parts[2]))
                    if parts[3] == "decision":
                        b = self._body()
                        try:
                            return self._json(w.update(b["id"], b))
                        except KeyError:
                            return self._json({"error": "unknown id"}, 400)
                    if parts[3] == "render":
                        if w.progress["running"]:
                            return self._json({"ok": False, "error": "書き出し中です"}, 409)
                        threading.Thread(target=self._render_bg, args=(w,), daemon=True).start()
                        return self._json({"ok": True})
                return self._json({"error": "not found"}, 404)
            except KeyError:
                return self._json({"error": "作業が見つかりません"}, 404)
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, 400)

        def _render_bg(self, w: Workdir):
            try:
                w.render_accepted(**app.render_opts)
            except Exception:
                pass  # 内容は progress["error"] に入る

        def _upload(self, name: str):
            n = int(self.headers.get("Content-Length") or 0)
            safe = "".join(ch for ch in Path(name).name if ch not in '\\/:*?"<>|') or "video.mp4"
            dst = app.home / "_uploads" / safe
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(dst, "wb") as f:
                left = n
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            return self._json({"path": str(dst)})

        def _media(self, path: Path):
            size = path.stat().st_size
            ctype = mimetypes.guess_type(path.name)[0] or "video/mp4"
            rng = self.headers.get("Range")
            start, end = 0, size - 1
            if rng and rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                start = int(a) if a else max(0, size - int(b))
                end = min(int(b) if (a and b) else size - 1, size - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                try:
                    while left > 0:
                        chunk = f.read(min(1 << 20, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
    return H


def serve_app(port: int = 0, home: Path | None = None, idle_timeout: float | None = None,
              render_opts: dict | None = None) -> tuple[ThreadingHTTPServer, App]:
    app = App(home, render_opts, idle_timeout)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    app.server = srv
    if idle_timeout:
        threading.Thread(target=app.watchdog, daemon=True).start()
    return srv, app


def review_url(srv: ThreadingHTTPServer, wid: str) -> str:
    return f"http://127.0.0.1:{srv.server_address[1]}/review?w={quote(wid)}"
