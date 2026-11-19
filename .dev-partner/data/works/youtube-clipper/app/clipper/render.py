"""縦型（1080×1920）の書き出し。タイトル帯・字幕・出典表記は ASS 字幕で描く。"""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config as C

BUNSETSU_END = "はがをにでとのもへやたてるいくしだらばどねよ"   # 文節の終わりになりやすいひらがな
KINSOKU_HEAD = "、。，．・：；？！!?」』）)ーぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ…"


BUNDLED_FONT = ("BIZ UDPGothic", "BIZUDPGothic-Bold.ttf")   # OFL。どの環境でも同じ見た目にするため同梱


def bundled_font_file() -> Path | None:
    from .paths import fonts_dir
    f = fonts_dir() / BUNDLED_FONT[1]
    return f if f.exists() else None


def pick_font(override: str | None = None) -> str:
    if override:
        return override
    if bundled_font_file():
        return BUNDLED_FONT[0]
    if shutil.which("fc-list"):
        out = subprocess.run(["fc-list", ":lang=ja", "family"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout
        fams = {f.strip() for line in out.splitlines() for f in line.split(",")}
        for f in C.FONT_CANDIDATES:
            if f in fams:
                return f
    return {"Darwin": "Hiragino Sans", "Windows": "Yu Gothic UI"}.get(platform.system(), "Noto Sans CJK JP")


def clean_text(t: str) -> str:
    t = re.sub(r"\[笑\]", "（笑）", t)
    t = re.sub(r"\[[^\]]*\]", "", t)          # [音楽] [拍手] などは消す
    return t.strip()


def _is_kanji_or_kata(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff" or "\u30a0" <= ch <= "\u30ff"


def _split2(s: str, width: int) -> list[str]:
    """2行に分ける。行の長さを揃えつつ、読点の後やかな→漢字の切れ目で改行する（行頭禁則つき）。"""
    if len(s) <= width:
        return [s]
    best, best_cost = None, 1e9
    for p in range(max(1, len(s) - width), min(width, len(s) - 1) + 1):
        if s[p] in KINSOKU_HEAD:
            continue
        a, b = s[p - 1], s[p]
        cost = abs(p - len(s) / 2)
        if s[:p].count("「") > s[:p].count("」"):
            cost += 2            # かぎ括弧の途中で改行しない
        if a in "、。！？":
            cost -= 10
        elif a == "っ":
            cost += 5            # 促音の直後で切ることはない（「よかっ|た」）
        elif a in BUNSETSU_END and (_is_kanji_or_kata(b) or b.isdigit()):
            cost -= 4            # 助詞・活用語尾の後ろで漢字/カタカナが始まる = 文節の切れ目
        elif _is_kanji_or_kata(a) and "\u3040" <= b <= "\u309f":
            cost += 3            # 漢字→ひらがな は送りがなの途中（「続|けた」）
        elif _is_kanji_or_kata(a) and _is_kanji_or_kata(b):
            cost += 2            # 熟語の途中（「結|果」）
        if cost < best_cost:
            best, best_cost = p, cost
    if best is None:
        best = width
    return [s[:best], s[best:]]


def wrap(text: str, width: int, max_lines: int) -> list[list[str]]:
    """日本語を折り返して「画面（ページ）」のリストにする。1画面は最大 max_lines 行。"""
    cap = width * max_lines
    pages, rest = [], text
    while rest:
        if len(rest) <= cap:
            chunk, rest = rest, ""
        else:   # 1画面に収まらない → 収まる範囲の最後の読点で区切る（なければ上限で）
            cut = max((i + 1 for i, ch in enumerate(rest[:cap]) if ch in "、。！？" and i + 1 >= cap // 2), default=cap)
            while cut < len(rest) and rest[cut] in KINSOKU_HEAD:
                cut -= 1
            chunk, rest = rest[:cut], rest[cut:]
        pages.append(_split2(chunk, width) if max_lines >= 2 else [chunk[:width]])
    return pages or [[""]]


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(t: str) -> str:
    return t.replace("\\", "＼").replace("{", "｛").replace("}", "｝")


def build_ass(clip: dict, sents: list[dict], font: str, credit: str = "", layout: str = "band") -> str:
    dur = clip["end"] - clip["start"]
    title_lines = wrap(clean_text(clip["title"]), C.TITLE_LINE_CHARS, C.TITLE_LINES)[0]
    band_cy = C.BAND_Y + C.BAND_H // 2 if layout == "band" else C.SAFE_TOP + 150
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {C.OUT_W}
PlayResY: {C.OUT_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{font},{C.TITLE_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{0 if layout == "band" else 5},0,5,{C.SAFE_X},{C.SAFE_X},0,1
Style: Sub,{font},{C.SUB_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{C.SUB_OUTLINE},0,8,{C.SAFE_X},{C.SAFE_X},0,1
Style: Credit,{font},{C.CREDIT_SIZE},&H40FFFFFF,&H40FFFFFF,&H80000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,9,{C.SAFE_X},{C.SAFE_X},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = [f"Dialogue: 1,{_ts(0)},{_ts(dur)},Title,,0,0,0,,{{\\pos(540,{band_cy})}}" + "\\N".join(_esc(l) for l in title_lines)]
    if credit:
        ev.append(f"Dialogue: 1,{_ts(0)},{_ts(dur)},Credit,,0,0,0,,{{\\pos({C.OUT_W - C.SAFE_X},{C.CREDIT_Y})}}{_esc(credit)}")
    sub_y = C.SUB_Y if layout == "band" else 1180
    for s in sents[clip["start_sid"]:clip["end_sid"] + 1]:
        text = clean_text(s["text"])
        if not text:
            continue
        pages = wrap(text, C.SUB_LINE_CHARS, C.SUB_LINES)
        t0, t1 = s["start"] - clip["start"], min(s["end"], clip["end"]) - clip["start"]
        total = sum(len("".join(p)) for p in pages) or 1
        t = t0
        for p in pages:                      # 長い文は文字数に比例して画面を分ける
            d = (t1 - t0) * len("".join(p)) / total
            ev.append(f"Dialogue: 0,{_ts(t)},{_ts(t + d)},Sub,,0,0,0,,{{\\pos(540,{sub_y})}}" + "\\N".join(_esc(l) for l in p))
            t += d
    return head + "\n".join(ev) + "\n"


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("ffmpeg に失敗しました:\n" + " ".join(cmd) + "\n" + r.stderr[-2000:])
    return r


def measure_loudness(src: Path, start: float, dur: float) -> dict | None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{start}", "-i", str(src), "-t", f"{dur}", "-vn",
                        "-af", f"loudnorm=I={C.LOUDNESS_I}:TP={C.LOUDNESS_TP}:LRA={C.LOUDNESS_LRA}:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    return json.loads(m.group(0)) if m else None


def render_clip(src: Path, clip: dict, sents: list[dict], out: Path, font: str | None = None,
                credit: str = "", layout: str = "band", band_color: str = C.BAND_COLOR) -> Path:
    font = pick_font(font)
    dur = round(clip["end"] - clip["start"], 3)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "clip.ass").write_text(build_ass(clip, sents, font, credit, layout), encoding="utf-8")
        sub = "subtitles=clip.ass"
        ff = bundled_font_file()
        if ff and font == BUNDLED_FONT[0]:   # 同梱フォントを一時フォルダに置き、相対パスで渡す（Windows のパスのエスケープを避ける）
            (td / "fonts").mkdir()
            shutil.copy(ff, td / "fonts" / ff.name)
            sub += ":fontsdir=fonts"
        # 2パスのラウドネス正規化（1パス目で測定 → 2パス目で線形補正）
        m = measure_loudness(src, clip["start"], dur)
        if m and m.get("input_i") not in (None, "-inf"):
            af = (f"loudnorm=I={C.LOUDNESS_I}:TP={C.LOUDNESS_TP}:LRA={C.LOUDNESS_LRA}:measured_I={m['input_i']}:"
                  f"measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                  f"offset={m['target_offset']}:linear=true")
        else:
            af = f"loudnorm=I={C.LOUDNESS_I}:TP={C.LOUDNESS_TP}:LRA={C.LOUDNESS_LRA}"
        af += f",aresample={48000}"
        if layout == "band":
            fc = (f"color=c=0x{C.BG_COLOR}:s={C.OUT_W}x{C.OUT_H}:r={C.OUT_FPS}:d={dur}[bg];"
                  f"[bg]drawbox=x=0:y={C.BAND_Y}:w={C.OUT_W}:h={C.BAND_H}:color=0x{band_color}:t=fill[bg2];"
                  f"[0:v]scale={C.OUT_W}:{C.VIDEO_H}:force_original_aspect_ratio=decrease,setsar=1,fps={C.OUT_FPS}[v];"
                  f"[bg2][v]overlay=x=(W-w)/2:y={C.VIDEO_Y}+({C.VIDEO_H}-h)/2:shortest=1[c];"
                  f"[c]{sub}[out]")
        else:  # crop: 中央を縦に切り出して全面表示（顔の位置は追わない）
            fc = (f"[0:v]scale=-2:{C.OUT_H},crop={C.OUT_W}:{C.OUT_H},setsar=1,fps={C.OUT_FPS}[v];"
                  f"[v]{sub}[out]")
        cmd = ["ffmpeg", "-hide_banner", "-y", "-ss", f"{clip['start']}", "-i", str(Path(src).resolve()), "-t", f"{dur}",
               "-filter_complex", fc, "-map", "[out]", "-map", "0:a?", "-af", af,
               "-c:v", "libx264", "-preset", "medium", "-crf", str(C.CRF), "-pix_fmt", "yuv420p", "-r", str(C.OUT_FPS),
               "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{dur}", str(out.resolve())]
        _run(cmd, cwd=td)    # 字幕ファイルを相対パスで渡す（Windows のドライブ文字のエスケープ問題を避ける）
    return out


def safe_name(t: str) -> str:
    t = re.sub(r'[\\/:*?"<>|\s]+', "_", clean_text(t)).strip("_")
    return t[:40] or "clip"
