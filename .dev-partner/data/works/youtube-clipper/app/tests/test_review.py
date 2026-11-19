"""AC9: レビュー画面の操作（採用・却下・伸縮・タイトル編集）が保存され、画面から書き出しまで通る。"""
import csv
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from clipper.__main__ import main
from clipper.review import serve

from conftest import SAMPLES

HERE = Path(__file__).resolve().parent


@pytest.mark.skipif(not shutil.which("node"), reason="node がない")
def test_review_flow(sample_video, tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_LOCAL_DIR", str(tmp_path / "local"))
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    wd = tmp_path / "demo.clipper"
    main(["run", str(sample_video), "--subs", str(SAMPLES / "talk_sample.srt"), "--workdir", str(wd),
          "--scorer", "rule", "--credit", "出典: サンプルチャンネル", "--no-review"])
    srv = serve(wd, port=0, open_browser=False)
    opened = []
    srv.app.opener = opened.append
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = srv.start_url
        r = subprocess.run(["node", str(HERE / "ui_review.cjs"), url, str(tmp_path / "after.png")],
                           capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, r.stderr
        res = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        srv.shutdown()

    assert res["errors"] == []
    assert res["afterAccept"] == "c02"                                   # 採用後は次の未判断へ
    assert res["c03"]["after"][1] == res["c03"]["before"][1] + 1         # ＋次の文
    assert res["minDurAfterShrink"] >= 20                                # 20秒未満には縮まない
    assert res["statuses"] == {"c01": "accepted", "c02": "accepted", "c03": "accepted", "c04": "pending", "c05": "rejected"}
    assert res["titles"]["c04"] == "朝5時起きを1か月続けた結果"
    assert "完了" in res["ptext"]
    # 初回ガイド（AC3）と「フォルダを開く」（AC5）
    assert len(res["guideSteps"]) == 4 and res["guideClosed"] and res["guideAfterReload"] and res["guideReopened"]
    assert res["openVisible"] and opened and opened[0] == wd.resolve() / "out"

    dec = json.loads((wd / "decisions.json").read_text(encoding="utf-8"))   # 画面の操作がファイルに残っている
    assert dec["clips"]["c05"]["status"] == "rejected" and dec["clips"]["c04"]["title"] == "朝5時起きを1か月続けた結果"
    outs = sorted((wd / "out").glob("*.mp4"))
    assert len(outs) == 3
    rows = list(csv.DictReader(open(wd / "out" / "clips.csv", encoding="utf-8-sig")))
    assert [r["file"] for r in rows] == [p.name for p in outs] and all("出典: サンプルチャンネル" in r["description"] for r in rows)
    shutil.copy(tmp_path / "after.png", SAMPLES / ".gen" / "review_after.png")
