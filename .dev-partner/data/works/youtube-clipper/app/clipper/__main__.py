"""コマンドライン。

  python -m clipper run <動画ファイル|URL> [--subs 字幕.srt|.vtt] [--scorer auto|llm|rule] [--credit "出典: ○○"]
  python -m clipper review <作業フォルダ>
  python -m clipper render <作業フォルダ> [--layout band|crop]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import config as C
from .candidates import n_candidates, normalize, rule_candidates, select
from .llm import llm_candidates
from .transcript import load_subs, to_sentences, transcribe_whisper
from .workdir import Workdir, probe_duration


def log(msg: str) -> None:
    print(msg, flush=True)


def is_url(s: str) -> bool:
    return bool(re.match(r"https?://", s))


def download(url: str, wd: Path) -> tuple[Path, Path | None, dict]:
    """yt-dlp で動画と（あれば）日本語字幕を取得する。自分の動画、または切り抜きを許諾された動画にだけ使うこと。"""
    if not shutil.which("yt-dlp"):
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            raise SystemExit("URL から取得するには yt-dlp が必要です: pip install yt-dlp")
        base = [sys.executable, "-m", "yt_dlp"]
    else:
        base = ["yt-dlp"]
    info = json.loads(subprocess.run(base + ["-J", "--no-playlist", url], capture_output=True, text=True, check=True).stdout)
    subprocess.run(base + ["--no-playlist", "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b",
                           "--merge-output-format", "mp4", "-o", str(wd / "source.%(ext)s"),
                           "--write-subs", "--write-auto-subs", "--sub-langs", "ja.*,ja", "--sub-format", "vtt", url],
                   check=True)
    src = next(wd.glob("source.mp4"), None) or next(p for p in wd.glob("source.*") if p.suffix != ".vtt")
    subs = next(iter(sorted(wd.glob("source*.vtt"))), None)
    return src, subs, {"title": info.get("title", ""), "channel": info.get("channel") or info.get("uploader", "")}


def cmd_run(a) -> None:
    t0 = time.time()
    name = re.sub(r"[^\w\-]+", "_", Path(a.input).stem if not is_url(a.input) else a.input.rsplit("=", 1)[-1])[:40]
    wdp = Path(a.workdir or f"{name}.clipper").resolve()
    wdp.mkdir(parents=True, exist_ok=True)
    wd = Workdir(wdp)
    log(f"作業フォルダ: {wdp}")

    meta = {"input": a.input}
    subs = Path(a.subs) if a.subs else None
    if is_url(a.input):
        log("1) 動画を取得中（yt-dlp）…")
        src, auto_subs, info = download(a.input, wdp)
        meta.update(url=a.input, title=info["title"], channel=info["channel"])
        subs = subs or auto_subs
    else:
        src = Path(a.input).resolve()
        if not src.exists():
            raise SystemExit(f"動画が見つかりません: {src}")
        meta["title"] = src.stem
    meta["source"] = str(src)
    meta["duration"] = probe_duration(src)
    meta["credit"] = a.credit or (f"出典: {meta['channel']}" if meta.get("channel") else "")
    wd.write("meta.json", meta)

    if subs:
        log(f"2) 字幕を読み込み: {subs.name}")
        segs = load_subs(subs)
    else:
        log(f"2) 文字起こし中（faster-whisper {a.model}。動画の長さの0.3〜0.5倍ほどかかります）…")
        segs = transcribe_whisper(src, a.model)
    wd.write("segments.json", segs)
    sents = to_sentences(segs)
    wd.write("sentences.json", sents)
    log(f"3) 文に分割: {len(sents)} 文")

    n = a.n or n_candidates(meta["duration"])
    cands = None
    if a.scorer in ("auto", "llm"):
        log(f"4) Claude（{C.LLM_MODEL}）で候補を採点中…")
        raw = llm_candidates(sents, n, meta.get("title", ""), log=log)
        if raw is None and a.scorer == "llm":
            raise SystemExit("Claude で採点できませんでした（--scorer auto ならルール採点に切り替えます）")
        if raw is not None:
            cands = normalize(raw, sents, meta["duration"], n)
            if len(cands) < n:   # 足りない分はルール採点で補う
                rule = rule_candidates(sents, meta["duration"], n * 3)
                cands = select(cands + rule, n)
    if cands is None:
        log("4) ルールで候補を採点中…")
        cands = rule_candidates(sents, meta["duration"], n)
    wd.write("candidates.json", cands)
    wd.init_decisions(cands)
    log(f"   候補 {len(cands)} 件（{time.time() - t0:.1f}秒）")
    for c in cands:
        log(f"   {c['id']} {c['score']:>3}点 {c['start']:7.1f}〜{c['end']:7.1f}s {c['title']}")
    if not a.no_review:
        cmd_review(argparse.Namespace(workdir=str(wdp), port=a.port, no_browser=a.no_browser, layout=a.layout,
                                      font=a.font, band_color=a.band_color))


def cmd_review(a) -> None:
    from .review import serve
    srv = serve(Path(a.workdir), a.port, not a.no_browser, layout=a.layout, font=a.font, band_color=a.band_color)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("終了しました")


def cmd_render(a) -> None:
    wd = Workdir(Path(a.workdir))
    files = wd.render_accepted(layout=a.layout, font=a.font, band_color=a.band_color)
    log(f"{len(files)} 本を書き出しました: {wd.path / 'out'}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="clipper", description="長い動画からショート用の切り抜き候補を作り、選んだものを縦型で書き出す")
    sp = p.add_subparsers(dest="cmd", required=True)

    def render_opts(q):
        q.add_argument("--layout", choices=["band", "crop"], default="band", help="band=上下に帯（既定）/ crop=中央を縦に切り出し")
        q.add_argument("--font", help="字幕フォント名（既定は自動選択）")
        q.add_argument("--band-color", default=C.BAND_COLOR, help="タイトル帯の色（16進, 既定 E11D48）")

    r = sp.add_parser("run", help="取得→文字起こし→候補作成→レビュー画面")
    r.add_argument("input", help="動画ファイル、または自分/許諾済みの動画のURL")
    r.add_argument("--subs", help="既存の字幕（.srt/.vtt）。指定すると文字起こしを省略")
    r.add_argument("--workdir", help="作業フォルダ（既定: <名前>.clipper）")
    r.add_argument("--model", default="small", help="faster-whisper のモデル（small/medium など）")
    r.add_argument("--scorer", choices=["auto", "llm", "rule"], default="auto")
    r.add_argument("--n", type=int, help="候補数（既定: 分数÷5、5〜20）")
    r.add_argument("--credit", help="出典表記（例: 出典: ○○チャンネル）")
    r.add_argument("--port", type=int, default=8765)
    r.add_argument("--no-review", action="store_true", help="レビュー画面を開かない")
    r.add_argument("--no-browser", action="store_true")
    render_opts(r)
    r.set_defaults(func=cmd_run)

    v = sp.add_parser("review", help="レビュー画面を開く")
    v.add_argument("workdir"); v.add_argument("--port", type=int, default=8765); v.add_argument("--no-browser", action="store_true")
    render_opts(v)
    v.set_defaults(func=cmd_review)

    w = sp.add_parser("render", help="採用した候補を書き出す")
    w.add_argument("workdir")
    render_opts(w)
    w.set_defaults(func=cmd_render)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
