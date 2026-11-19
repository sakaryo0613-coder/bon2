"""B-008: アプリ（ホーム画面・候補づくりのジョブ・自動終了・二重起動の防止）。"""
import json
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

import pytest

from clipper import launcher, paths
from clipper.app import serve_app

from conftest import SAMPLES

HERE = Path(__file__).resolve().parent


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLIPPER_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("CLIPPER_LOCAL_DIR", str(tmp_path / "local"))
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


def call(port, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def start(**kw):
    srv, app = serve_app(0, **kw)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, app, srv.server_address[1]


def test_job_api_flow(env, sample_video):
    srv, app, port = start()
    try:
        app.picker = lambda kind: str(sample_video) if kind == "video" else str(SAMPLES / "talk_sample.srt")
        assert call(port, "/api/pick", {"kind": "video"})["path"] == str(sample_video)
        job = call(port, "/api/jobs", {"video": str(sample_video), "subs": str(SAMPLES / "talk_sample.srt"), "credit": "出典: X"})
        for _ in range(300):
            j = call(port, f"/api/jobs/{job['id']}")
            if j["done"] or j["error"]:
                break
            time.sleep(0.2)
        assert j["done"] and not j["error"], j
        wid = j["workdir"]
        st = call(port, f"/api/w/{wid}/state")
        assert len(st["clips"]) == 5 and st["meta"]["credit"] == "出典: X"
        home = call(port, "/api/home")
        assert home["recent"][0]["id"] == wid and home["config"]["credit"] == "出典: X"   # 出典は次回の既定値として保存
        # 作業フォルダはホーム（ドキュメント\clipper）の下に作られる
        assert (Path(home["home"]) / wid / "candidates.json").exists()
        # 存在しない動画はエラーを返す
        with pytest.raises(urllib.error.HTTPError) as e:
            call(port, "/api/jobs", {"video": str(env / "nai.mp4")})
        assert e.value.code == 400
    finally:
        srv.shutdown()


def test_pick_failure_is_reported(env):
    """ファイル選択画面を開けない環境でも、落ちずに案内を返す。"""
    srv, app, port = start()
    try:
        def boom(kind):
            raise RuntimeError("no display")
        app.picker = boom
        r = call(port, "/api/pick", {"kind": "video"})
        assert r["path"] == "" and "ドラッグ" in r["error"]
    finally:
        srv.shutdown()


def test_config_saves_api_key(env):
    srv, app, port = start()
    try:
        assert call(port, "/api/home")["config"]["has_api_key"] is False
        call(port, "/api/config", {"api_key": "sk-ant-test"})
        assert paths.load_config()["api_key"] == "sk-ant-test"
        assert call(port, "/api/home")["config"]["has_api_key"] is True
    finally:
        srv.shutdown()
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_idle_shutdown_and_busy(env):
    """AC6: 画面からの通知が途絶えると終了する。処理中は終了しない。"""
    srv, app, port = start(idle_timeout=1.5)
    for _ in range(3):                      # 通知が続いている間は終了しない
        call(port, "/api/ping", {})
        time.sleep(0.8)
    assert not app.stopped
    app.jobs["x"] = {"done": False, "error": ""}   # 処理中を模擬
    app.last_ping = time.time() - 10
    time.sleep(3)
    assert not app.stopped                  # 処理中なので終了しない
    app.jobs["x"]["done"] = True             # 処理が終わり、通知も途絶えている（ここからは画面に問い合わせない）
    for _ in range(40):
        if app.stopped:
            break
        time.sleep(0.2)
    else:
        pytest.fail("通知が途絶えても終了しなかった")


def test_single_instance(env):
    """AC6: 起動中なら find_running がそのポートを返し、2回目の起動は窓を開くだけで終わる。"""
    assert launcher.find_running() is None
    srv, app, port = start()
    try:
        launcher.write_lock(port)
        assert launcher.find_running() == port
        opened = []
        launcher.open_window = opened.append       # 実際に窓は開かない
        assert launcher.main(["--port", "0"]) == 0
        assert opened == [f"http://127.0.0.1:{port}/"]
    finally:
        srv.shutdown()
    launcher.clear_lock(port)
    assert launcher.find_running() is None


@pytest.mark.skipif(not shutil.which("node"), reason="node がない")
def test_home_ui_flow(env, sample_video):
    """AC1・AC2: 起動 →「動画を選ぶ」→「候補を作る」の3操作で候補づくりが始まり、進み具合を経てレビュー画面に進む。"""
    srv, app, port = start()
    app.picker = lambda kind: str(sample_video)
    real_start = app.start_job
    app.start_job = lambda video, subs="", credit="": real_start(video, str(SAMPLES / "talk_sample.srt"), credit)
    try:
        r = subprocess.run(["node", str(HERE / "ui_home.cjs"), f"http://127.0.0.1:{port}/", str(env / "home.png")],
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stderr
        res = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        srv.shutdown()
    assert res["errors"] == []
    assert res["startDisabledBefore"] and res["picked"] == sample_video.name
    assert res["clicks"] == 2                     # 起動（1）＋ 2クリック = 3操作
    assert res["reachedReview"] and res["nClips"] == 5 and res["guideShown"]
    assert any("talk_sample" in t for t in res["recent"])
    shutil.copy(env / "home.png", SAMPLES / ".gen" / "home_after.png")


def test_cli_app_selftest_entry(env, tmp_path):
    """CLI の入口（python -m clipper app ...）が引数をそのままアプリに渡せる（B-008 で argparse の癖により壊れていた）。"""
    import sys
    out = tmp_path / "st"
    r = subprocess.run([sys.executable, "-m", "clipper", "app", "--selftest", str(out)], cwd=str(HERE.parent),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    res = json.loads((out / "selftest.json").read_text(encoding="utf-8"))
    assert res["ok"] and res["checks"]["format"]["ok"]


@pytest.mark.skipif(not shutil.which("node"), reason="node がない")
def test_home_ui_shows_failure(env, tmp_path):
    """失敗したら、アニメーションが止まり、失敗した段階が赤くなり、「もう一度試す」とログの場所が出る（B-004 の実機で「止まって見えた」件）。"""
    bad = tmp_path / "not_a_video.mp4"
    bad.write_text("これは動画ではありません", encoding="utf-8")
    srv, app, port = start()
    app.picker = lambda kind: str(bad)
    try:
        r = subprocess.run(["node", str(HERE / "ui_home_error.cjs"), f"http://127.0.0.1:{port}/"],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        res = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        srv.shutdown()
    assert res["errors"] == []
    assert "うまくいきませんでした" in res["err"] and "clipper.log" in res["err"]
    assert res["animating"] is False and res["failedStage"] and res["retry"] == "もう一度試す"
    assert res["title"] == "候補づくりに失敗しました"


# ---------------------------------------------------------------- B-012: Twitch の URL から
def fake_twitch(sample_video, chat_ok=True, video_error=None):
    """Twitch の取得部分だけを差し替える（URL の判定とエラーの型は本物）。"""
    from types import SimpleNamespace
    from clipper import twitch as T
    from test_candidates import burst_chat
    calls = []

    def fetch_info(url):
        calls.append(("info", url))
        return {"id": "v123", "title": "雑談配信 テスト", "uploader": "テスト配信者", "duration": 368.15}

    def fetch_chat(vid, until=None, progress=None, **kw):
        calls.append(("chat", vid, until))
        if not chat_ok:
            raise T.TwitchError("failed integrity check")
        progress and progress(50.0, "チャットを取得しています（100件）")
        return {"messages": burst_chat(368.15), "method": "persisted/offset", "pages": 3, "notes": []}

    def download_vod(url, dest, progress=None, info=None, **kw):
        calls.append(("video", url))
        if video_error:
            raise T.TwitchError(video_error)
        progress and progress(40.0, "動画を取得しています（10MB）")
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(sample_video, dest / "source.mp4")
        return dest / "source.mp4", info

    return SimpleNamespace(parse_url=T.parse_url, TwitchError=T.TwitchError, fetch_info=fetch_info,
                           fetch_chat=fetch_chat, download_vod=download_vod, calls=calls)


@pytest.fixture
def with_subs(monkeypatch):
    """この環境には文字起こしのモデルがないので、見本の字幕を使わせる（取得から候補までの流れを確かめる）。"""
    import clipper.app as app_mod
    real = app_mod.build
    monkeypatch.setattr(app_mod, "build", lambda video, wdp, subs=None, **kw: real(video, wdp, SAMPLES / "talk_sample.srt", **kw))


def wait_job(port, jid, secs=60):
    for _ in range(secs * 5):
        j = call(port, f"/api/jobs/{jid}")
        if j["done"] or j["error"]:
            return j
        time.sleep(0.2)
    return j


def test_url_job_api_flow(env, sample_video, with_subs):
    """B-012 AC6・AC7（API）: URL から 確認 → チャット → 動画 → 候補。理由にチャットの倍率。出典は配信者名。"""
    srv, app, port = start()
    try:
        app.twitch = tw = fake_twitch(sample_video)
        chk = call(port, "/api/url/check", {"url": "https://www.twitch.tv/videos/123"})
        assert chk["kind"] == "vod" and chk["id"] == "123"
        bad = call(port, "/api/url/check", {"url": "https://clips.twitch.tv/abc"})
        assert bad["kind"] == "clip" and "アーカイブ" in bad["message"]
        with pytest.raises(urllib.error.HTTPError) as e:            # 取り込めない URL は始めない
            call(port, "/api/jobs", {"url": "https://www.youtube.com/watch?v=x"})
        assert e.value.code == 400
        job = call(port, "/api/jobs", {"url": "https://www.twitch.tv/videos/123", "credit": ""})
        assert job["kind"] == "url"
        j = wait_job(port, job["id"])
        assert j["done"] and not j["error"] and not j["warning"], j
        assert [c[0] for c in tw.calls] == ["info", "chat", "video"] and tw.calls[1][2] == 368.15
        st = call(port, f"/api/w/{quote(j['workdir'])}/state")
        assert st["meta"]["platform"] == "twitch" and st["meta"]["credit"] == "出典: テスト配信者"
        assert st["meta"]["title"] == "雑談配信 テスト"
        assert any(c["reasons"][:1] and c["reasons"][0].startswith("チャット ×") for c in st["clips"]), st["clips"]
        wd = Path(call(port, "/api/home")["home"]) / j["workdir"]
        assert (wd / "chat_messages.json").exists() and (wd / "chat.json").exists()
    finally:
        srv.shutdown()


def test_url_job_chat_failure_continues_and_video_failure_explains(env, sample_video, with_subs):
    """B-012 AC7: チャットだけ失敗 → 警告を出して言葉だけで続ける。動画の失敗 → 理由を1文で出す。"""
    srv, app, port = start()
    try:
        app.twitch = fake_twitch(sample_video, chat_ok=False)
        j = wait_job(port, call(port, "/api/jobs", {"url": "https://www.twitch.tv/videos/123"})["id"])
        assert j["done"] and "言葉だけで採点" in j["warning"]
        st = call(port, f"/api/w/{quote(j['workdir'])}/state")
        assert not any(r.startswith("チャット") for c in st["clips"] for r in c["reasons"])
        app.twitch = fake_twitch(sample_video, video_error="アーカイブが見つかりません。期限（通常7〜60日）が過ぎて消えたか、非公開にされた可能性があります")
        j = wait_job(port, call(port, "/api/jobs", {"url": "https://www.twitch.tv/videos/124"})["id"])
        assert j["error"].startswith("アーカイブが見つかりません") and not j["done"]
    finally:
        srv.shutdown()


def test_home_ui_url_flow(env, sample_video, with_subs):
    """B-012 AC6（画面）: URL を貼る → 「候補を作る」の2操作で、段階が順に出てレビュー画面に進む。"""
    srv, app, port = start()
    app.twitch = fake_twitch(sample_video)
    try:
        r = subprocess.run(["node", str(HERE / "ui_home_url.cjs"), f"http://127.0.0.1:{port}/", str(env / "home_url.png")],
                           capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, r.stderr
        res = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        srv.shutdown()
    assert res["errors"] == []
    assert res["badMsg"] and "クリップ" in res["badMsg"] and res["startDisabledOnBad"] is True
    assert "videos/987" in res["okMsg"] and res["clicks"] == 2
    assert res["stgKeys"] == ["chat", "fetch", "model", "transcribe", "candidates"], res   # URL のときの段階の表示
    assert "fetch" in res["stagesSeen"], res
    assert res["startHiddenDuringJob"] and res["jobInView"], res      # 処理中の表示がファーストビューに出る
    assert res["reachedReview"] and res["chatReason"]
