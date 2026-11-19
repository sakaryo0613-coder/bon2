"""動画から候補を作るまでの一連の処理。コマンド（run）とアプリ（ホーム画面）の両方から使う。

progress(stage, pct, message) を段階ごとに呼ぶ。stage は次のいずれか:
  prepare（準備）→ model（文字起こしモデルの取得・初回のみ）→ transcribe（文字起こし）→ candidates（候補づくり）→ done
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable

from . import config as C
from .candidates import annotate_chat, n_candidates, normalize, rule_candidates, select
from .llm import llm_candidates
from .transcript import load_subs, to_sentences, transcribe_whisper
from .workdir import Workdir, probe_duration

Progress = Callable[[str, float, str], None]


def _noop(stage: str, pct: float, msg: str) -> None:
    pass


def workdir_for(video: Path, base: Path) -> Path:
    """動画名から作業フォルダ名を決める（同名があれば連番）。"""
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", video.stem)[:40] or "video"
    p = base / f"{name}.clipper"
    i = 2
    while p.exists() and (p / "candidates.json").exists():
        p = base / f"{name}_{i}.clipper"
        i += 1
    return p


def build(video: Path, workdir: Path, subs: Path | None = None, credit: str = "", scorer: str = "auto",
          model: str = "small", n: int | None = None, meta_extra: dict | None = None,
          progress: Progress = _noop, log=print, download_root: Path | None = None, language: str = "ja",
          chat: list[dict] | None = None) -> Workdir:
    """chat: Twitch などのチャット [{t, text}]（あれば盛り上がりを採点に使う。B-012）"""
    t0 = time.time()
    video = Path(video).resolve()
    if not video.exists():
        raise FileNotFoundError(f"動画が見つかりません: {video}")
    workdir.mkdir(parents=True, exist_ok=True)
    wd = Workdir(workdir)
    progress("prepare", 0, "動画を確認しています")
    meta = {"input": str(video), "source": str(video), "title": video.stem, **(meta_extra or {})}
    meta["duration"] = probe_duration(video)
    meta["credit"] = credit or (f"出典: {meta['channel']}" if meta.get("channel") else "")
    wd.write("meta.json", meta)

    if subs:
        progress("transcribe", 0, f"字幕を読み込んでいます（{Path(subs).name}）")
        segs = load_subs(Path(subs))
    else:
        def tp(pct, msg):
            progress("transcribe" if pct >= 0 else "model", max(pct, 0), msg)
        segs = transcribe_whisper(video, model, progress=tp, download_root=download_root, duration=meta["duration"],
                                  language=language)
    progress("transcribe", 100, "文字起こしが終わりました")
    wd.write("segments.json", segs)
    sents = to_sentences(segs)
    wd.write("sentences.json", sents)
    log(f"文に分割: {len(sents)} 文")

    sig = None
    if chat:
        from .twitch import ChatSignal
        sig = ChatSignal(chat, meta["duration"])
        wd.write("chat.json", {"count": len(sig), "series": sig.series()})
        log(f"チャット: {len(sig)} 件")
    n = n or n_candidates(meta["duration"])
    cands = None
    if scorer in ("auto", "llm"):
        progress("candidates", 10, f"Claude（{C.LLM_MODEL}）で候補を採点しています")
        raw = llm_candidates(sents, n, meta.get("title", ""), log=log, chat=sig)
        if raw is None and scorer == "llm":
            raise RuntimeError("Claude で採点できませんでした")
        if raw is not None:
            cands = normalize(raw, sents, meta["duration"], n)
            if len(cands) < n:   # 足りない分はルール採点で補う
                cands = select(cands + rule_candidates(sents, meta["duration"], n * 3, chat=sig), n)
    if cands is None:
        progress("candidates", 50, "ルールで候補を採点しています")
        cands = rule_candidates(sents, meta["duration"], n, chat=sig)
    annotate_chat(cands, sig)
    wd.write("candidates.json", cands)
    wd.init_decisions(cands)
    log(f"候補 {len(cands)} 件（{time.time() - t0:.1f}秒）")
    progress("done", 100, f"候補を {len(cands)} 本作りました")
    return wd
