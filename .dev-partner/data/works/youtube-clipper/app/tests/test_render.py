"""AC7・AC8: 書き出した動画の形式・長さ・ラウドネスと、文字が安全領域に収まっていること。"""
import json
import re
import subprocess

import pytest

from clipper import config as C
from clipper.candidates import rule_candidates
from clipper.render import render_clip


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1])


def frame(path, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    assert len(raw) == C.OUT_W * C.OUT_H * 3
    return raw


def px(raw, x, y):
    i = (y * C.OUT_W + x) * 3
    return raw[i], raw[i + 1], raw[i + 2]


def count_white(raw, y0, y1, x0=0, x1=C.OUT_W, step=2):
    return sum(1 for y in range(y0, y1, step) for x in range(x0, x1, step) if min(px(raw, x, y)) > 225)


def is_bg_rows(raw, y0, y1, step=4):
    bg = int(C.BG_COLOR[:2], 16)
    return all(max(abs(c - bg) for c in px(raw, x, y)) <= 14 for y in range(y0, y1, step) for x in range(0, C.OUT_W, step))


@pytest.fixture(scope="module")
def rendered(sents, expected, sample_video, tmp_path_factory):
    c = rule_candidates(sents, expected["duration"])[2]
    out = tmp_path_factory.mktemp("render") / "clip.mp4"
    render_clip(sample_video, c, sents, out, credit="出典: サンプルチャンネル")
    return c, out


def test_format_duration_loudness(rendered):
    c, out = rendered
    info = probe(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert (v["width"], v["height"], v["codec_name"], v["r_frame_rate"]) == (1080, 1920, "h264", "30/1")
    assert (a["codec_name"], a["sample_rate"]) == ("aac", "48000")
    assert abs(float(info["format"]["duration"]) - (c["end"] - c["start"])) <= 0.1
    assert abs(loudness(out) - C.LOUDNESS_I) <= 1.5


def test_text_inside_safe_area(rendered):
    c, out = rendered
    raw = frame(out, 5.0)
    assert is_bg_rows(raw, 0, C.BAND_Y), "タイトル帯より上（上部UIの領域）に何か描かれている"
    assert is_bg_rows(raw, C.SAFE_BOTTOM + 10, C.OUT_H), "安全領域より下（下部UIの領域）に何か描かれている"
    assert count_white(raw, C.BAND_Y, C.BAND_Y + C.BAND_H) > 500, "タイトルが描かれていない"
    assert count_white(raw, C.SUB_Y - 10, C.SAFE_BOTTOM) > 500, "字幕が描かれていない"
    for y0, y1 in [(C.BAND_Y, C.BAND_Y + C.BAND_H), (C.SUB_Y - 10, C.SAFE_BOTTOM)]:
        assert count_white(raw, y0, y1, 0, C.SAFE_X - 10) == 0
        assert count_white(raw, y0, y1, C.OUT_W - C.SAFE_X + 10, C.OUT_W) == 0


def test_crop_layout(sents, expected, sample_video, tmp_path):
    c = rule_candidates(sents, expected["duration"])[0]
    out = render_clip(sample_video, c, sents, tmp_path / "crop.mp4", layout="crop")
    v = next(s for s in probe(out)["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920)
