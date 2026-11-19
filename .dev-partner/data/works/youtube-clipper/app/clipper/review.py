"""コマンド `python -m clipper review <作業フォルダ>` 用。アプリのサーバー（app.py）で、指定した作業のレビュー画面を開く。"""
from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from .app import review_url, serve_app


def serve(workdir: Path, port: int = 8765, open_browser: bool = True, **render_opts):
    """サーバーを作って返す（serve_forever は呼び出し側）。srv.start_url にレビュー画面のURLが入る。"""
    workdir = Path(workdir).resolve()
    last = None
    for p in ([port] if port == 0 else range(port, port + 20)):
        try:
            srv, app = serve_app(p, home=workdir.parent, render_opts=render_opts)
            break
        except OSError as e:
            last = e
    else:
        raise SystemExit(f"空いているポートが見つかりません: {last}")
    wid = app.register(workdir)
    srv.app = app
    srv.start_url = review_url(srv, wid)
    print(f"レビュー画面: {srv.start_url}  （終了は Ctrl+C）")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(srv.start_url)).start()
    return srv
