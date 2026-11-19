"""レビュー画面のローカルサーバー（標準ライブラリのみ）。127.0.0.1 だけで待ち受ける。"""
from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .workdir import Workdir

HTML = Path(__file__).with_name("review.html")


def make_handler(wd: Workdir, render_opts: dict):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # 静かにする
            pass

        def _json(self, data, code=200):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = HTML.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/state":
                self._json(wd.state())
            elif self.path == "/api/render":
                self._json(wd.progress)
            elif self.path.startswith("/media/source"):
                self._media(wd.source())
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.path == "/api/decision":
                b = self._body()
                try:
                    self._json(wd.update(b["id"], b))
                except KeyError:
                    self._json({"error": "unknown id"}, 400)
            elif self.path == "/api/render":
                if wd.progress["running"]:
                    return self._json({"ok": False, "error": "書き出し中です"}, 409)
                threading.Thread(target=self._render_bg, daemon=True).start()
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, 404)

        def _render_bg(self):
            try:
                wd.render_accepted(**render_opts)
            except Exception:
                pass  # エラー内容は progress["error"] に入る

        def _media(self, path: Path):
            """動画を Range 対応で返す（シークに必要）。"""
            size = path.stat().st_size
            ctype = mimetypes.guess_type(path.name)[0] or "video/mp4"
            rng = self.headers.get("Range")
            start, end = 0, size - 1
            if rng and rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                start = int(a) if a else max(0, size - int(b))
                end = int(b) if (a and b) else size - 1
                end = min(end, size - 1)
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
                except (BrokenPipeError, ConnectionResetError):
                    pass
    return H


def serve(workdir: Path, port: int = 8765, open_browser: bool = True, **render_opts) -> ThreadingHTTPServer:
    wd = Workdir(workdir)
    for p in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), make_handler(wd, render_opts))
            break
        except OSError:
            continue
    else:
        raise SystemExit("空いているポートが見つかりません")
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"レビュー画面: {url}  （終了は Ctrl+C）")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    return srv
