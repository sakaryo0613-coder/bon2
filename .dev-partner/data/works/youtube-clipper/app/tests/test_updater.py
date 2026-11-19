"""B-013: アプリ内の更新（版の比較・Release の読み取り・ダウンロードの検証・画面）。"""
import hashlib
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from clipper import updater as U
from clipper.app import serve_app

HERE = Path(__file__).resolve().parent


def rel(tag, size=10, digest="", draft=False, pre=False, name="clipper-setup.exe", url="x"):
    return {"tag_name": tag, "draft": draft, "prerelease": pre, "body": "notes", "published_at": "2026-11-19T00:00:00Z",
            "assets": [{"name": name, "size": size, "digest": digest, "browser_download_url": url}]}


def test_versions_and_pick_latest():
    """AC1"""
    assert U.parse_version("0.3.12") == (0, 3, 12) and U.parse_version("dev") == ()
    assert U.is_newer("0.3.12", "0.3.9") and not U.is_newer("0.3.9", "0.3.12")
    assert not U.is_newer("0.3.12", "dev")                 # ソースから動かしているときは出さない
    rs = [rel("clipper-v0.3.5"), rel("clipper-v0.3.12"), rel("clipper-v0.3.99", draft=True),
          rel("clipper-v0.4.0", pre=True), rel("other-v9.9.9"), rel("clipper-v0.3.50", name="readme.txt"),
          rel("clipper-v0.3.7", digest="sha256:ABC")]
    best = U.pick_latest(rs)
    assert best["latest"] == "0.3.12" and best["tag"] == "clipper-v0.3.12"
    assert U.pick_latest([rel("clipper-v0.3.7", digest="sha256:ABC")])["sha256"] == "abc"
    assert U.pick_latest([]) is None


def test_check_cache_and_offline():
    calls = []

    def fetch(url):
        calls.append(url)
        return [rel("clipper-v0.3.12")]
    up = U.Updater(url="u", fetch=fetch, version="0.3.9")
    assert up.check()["available"] and up.check()["latest"] == "0.3.12"
    assert len(calls) == 1                                   # 10分キャッシュ

    def boom(url):
        raise OSError("offline")
    off = U.Updater(url="u", fetch=boom, version="0.3.9").check()
    assert off["available"] is False and "offline" in off["error"]


def _setup_file(tmp_path, data=b"installer-bytes" * 1000):
    f = tmp_path / "clipper-setup.exe"
    f.write_bytes(data)
    return f, hashlib.sha256(data).hexdigest(), len(data)


def test_apply_success_launches_and_exits(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_LOCAL_DIR", str(tmp_path / "local"))
    f, sha, size = _setup_file(tmp_path)
    launched, exited = [], []
    up = U.Updater(url="u", fetch=lambda u: [rel("clipper-v0.3.12", size=size, digest=f"sha256:{sha}", url=str(f))],
                   launcher=launched.append, exit_fn=lambda: exited.append(1), version="0.3.9")
    assert up.apply(wait=True)
    assert up.state["error"] == "" and up.state["phase"] == "restarting"
    assert launched and launched[0].name == "clipper-setup-0.3.12.exe" and launched[0].read_bytes() == f.read_bytes()
    time.sleep(1.3)
    assert exited == [1]                                     # 1秒後に終了


@pytest.mark.parametrize("bad", ["sha", "size"])
def test_apply_rejects_broken_download(tmp_path, monkeypatch, bad):
    """AC3: 壊れていたらインストーラーを起動せず、今の版のまま理由を出す。"""
    monkeypatch.setenv("CLIPPER_LOCAL_DIR", str(tmp_path / "local"))
    f, sha, size = _setup_file(tmp_path)
    digest = "sha256:" + ("0" * 64 if bad == "sha" else sha)
    launched = []
    up = U.Updater(url="u", fetch=lambda u: [rel("clipper-v0.3.12", size=size + (5 if bad == "size" else 0), digest=digest, url=str(f))],
                   launcher=launched.append, exit_fn=lambda: None, version="0.3.9")
    up.apply(wait=True)
    assert not launched and up.state["error"] and up.state["phase"] == ""
    assert not list((tmp_path / "local" / "updates").glob("*.exe"))


def test_no_update_when_latest():
    up = U.Updater(url="u", fetch=lambda u: [rel("clipper-v0.3.9")], version="0.3.9")
    assert up.check()["available"] is False and up.apply() is False


@pytest.mark.skipif(not shutil.which("node"), reason="node がない")
def test_update_banner_ui(tmp_path, monkeypatch):
    """AC2・AC4: 新しい版があるとお知らせが出て、「更新する」で進み具合 → 「更新しています」になる。ホームに今の版が出る。"""
    for k, v in {"CLIPPER_HOME": "home", "CLIPPER_CONFIG_DIR": "cfg", "CLIPPER_LOCAL_DIR": "local"}.items():
        monkeypatch.setenv(k, str(tmp_path / v))
    f, sha, size = _setup_file(tmp_path, b"x" * (3 << 20))
    launched = []
    srv, app = serve_app(0)
    app.updater = U.Updater(url="u", fetch=lambda u: [rel("clipper-v0.3.12", size=size, digest=f"sha256:{sha}", url=str(f))],
                            launcher=launched.append, exit_fn=lambda: None, version="0.3.9")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = subprocess.run(["node", str(HERE / "ui_update.cjs"), f"http://127.0.0.1:{srv.server_address[1]}/"],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        res = json.loads(r.stdout.strip().splitlines()[-1])
        app.updater = U.Updater(url="u", fetch=lambda u: [rel("clipper-v0.3.9")], version="0.3.9")
        r2 = subprocess.run(["node", str(HERE / "ui_update.cjs"), f"http://127.0.0.1:{srv.server_address[1]}/", "none"],
                            capture_output=True, text=True, timeout=120)
        res2 = json.loads(r2.stdout.strip().splitlines()[-1])
    finally:
        srv.shutdown()
    assert res["errors"] == [] and res["ver"] == "v0.3.9"
    assert "v0.3.12" in res["banner"] and "更新しています" in res["after"] and launched
    assert res2["bannerHidden"] is True
