"""字幕・文字起こしの読み込みと、文単位への分割。"""
from __future__ import annotations

import re
from pathlib import Path

from . import config as C

TS = r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"


def _sec(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse_srt(text: str) -> list[dict]:
    segs = []
    for block in re.split(r"\n\s*\n", text.replace("\r", "").strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        for i, l in enumerate(lines):
            m = re.match(TS + r"\s*-->\s*" + TS, l)
            if m:
                g = m.groups()
                body = "".join(x.strip() for x in lines[i + 1:])
                if body:
                    segs.append({"start": _sec(*g[:4]), "end": _sec(*g[4:]), "text": body})
                break
    return segs


def parse_vtt(text: str) -> list[dict]:
    """WebVTT。YouTube の自動字幕（前の行を繰り返すロールアップ形式）にも対応する。"""
    segs, last = [], ""
    for block in re.split(r"\n\s*\n", text.replace("\r", "").strip()):
        lines = block.split("\n")
        for i, l in enumerate(lines):
            m = re.match(TS + r"\s*-->\s*" + TS, l.strip())
            if not m:
                continue
            g = m.groups()
            start, end = _sec(*g[:4]), _sec(*g[4:])
            if end - start < 0.05:      # 表示切り替え用の極短キュー
                break
            body = [re.sub(r"<[^>]+>", "", x).strip() for x in lines[i + 1:]]
            body = [x for x in body if x]
            new = [x for x in body if x != last]
            if new:
                segs.append({"start": start, "end": end, "text": "".join(new)})
                last = body[-1]
            break
    return segs


def load_subs(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    return parse_vtt(text) if path.suffix.lower() == ".vtt" or text.startswith("WEBVTT") else parse_srt(text)


def transcribe_whisper(video: Path, model: str = "small") -> list[dict]:
    """faster-whisper で文字起こし（語ごとの時刻つき）。初回はモデルをダウンロードする。"""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover
        raise SystemExit("faster-whisper が必要です: pip install faster-whisper") from e
    wm = WhisperModel(model, device="cpu", compute_type="int8")
    segments, _info = wm.transcribe(str(video), language="ja", vad_filter=True, word_timestamps=True)
    out = []
    for s in segments:
        words = [{"start": w.start, "end": w.end, "text": w.word} for w in (s.words or [])]
        out.append({"start": s.start, "end": s.end, "text": s.text.strip(), "words": words})
    return out


# ------------------------------------------------------------------ 文に分ける
def _pieces(segs: list[dict]) -> list[dict]:
    """字幕を「句読点で終わる断片」に分け、時刻は文字数で按分する。語の時刻があればそれを使う。"""
    pieces = []
    for s in segs:
        if s.get("words"):
            for w in s["words"]:
                pieces.append({"start": w["start"], "end": w["end"], "text": w["text"]})
            continue
        text = s["text"]
        # 「先生！」のように括弧内の！？は文末ではないので、閉じ括弧ごと同じ断片に含める
        parts = re.findall(rf"[^{C.SENT_END_CHARS}]+[{C.SENT_END_CHARS}]*[」』）)]*(?:\[[^\]]*\])?", text) or [text]
        total = sum(len(p) for p in parts) or 1
        t = s["start"]
        for p in parts:
            d = (s["end"] - s["start"]) * len(p) / total
            pieces.append({"start": t, "end": t + d, "text": p})
            t += d
    return pieces


def _ends_sentence(text: str) -> bool:
    t = re.sub(r"\[[^\]]*\]$", "", text.strip())
    return bool(t) and t[-1] in C.SENT_END_CHARS


def to_sentences(segs: list[dict]) -> list[dict]:
    pieces = _pieces(segs)
    sents, cur = [], None
    for i, p in enumerate(pieces):
        if cur is None:
            cur = dict(p)
        else:
            cur["end"] = p["end"]
            cur["text"] += p["text"]
        nxt = pieces[i + 1] if i + 1 < len(pieces) else None
        gap = (nxt["start"] - p["end"]) if nxt else 99
        if _ends_sentence(cur["text"]) or gap >= C.SENT_GAP or nxt is None:
            cur["text"] = cur["text"].strip()
            sents.append(cur)
            cur = None
    # 短すぎる断片は前の文へ
    merged = []
    for s in sents:
        if merged and (s["end"] - s["start"]) < C.SENT_MIN_DUR and (s["start"] - merged[-1]["end"]) < C.SENT_GAP:
            merged[-1]["end"] = s["end"]
            merged[-1]["text"] += s["text"]
        else:
            merged.append(s)
    for i, s in enumerate(merged):
        s["id"] = i
        s["start"], s["end"] = round(s["start"], 3), round(s["end"], 3)
    return merged
