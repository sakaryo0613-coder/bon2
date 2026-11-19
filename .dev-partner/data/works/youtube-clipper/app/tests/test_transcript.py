import importlib.util

from clipper.transcript import parse_vtt, to_sentences

from conftest import SAMPLES


def _script_sentences():
    spec = importlib.util.spec_from_file_location("b", SAMPLES / "build_sample.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    return [l for _, _, ls in b.SCRIPT for l in ls]


def test_sample_sentences_match_script(sents):
    """1字幕に2文・1文が2字幕にまたがる・括弧内の！を含むサンプルを、台本どおりの文に戻せる。"""
    assert [s["text"] for s in sents] == _script_sentences()
    assert [s["id"] for s in sents] == list(range(len(sents)))


def test_gap_splits_and_short_merge():
    segs = [{"start": 0.0, "end": 2.0, "text": "句点のない文"},           # 次まで0.8秒 → ここで区切る
            {"start": 2.8, "end": 5.0, "text": "次の話です"},
            {"start": 5.1, "end": 5.5, "text": "はい"},                   # 0.4秒・間が短い → 前の文に結合
            {"start": 7.0, "end": 9.0, "text": "最後の文。"}]
    out = [s["text"] for s in to_sentences(segs)]
    assert out == ["句点のない文", "次の話ですはい", "最後の文。"]


def test_youtube_rollup_vtt():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
<c>こんにちは</c>

00:00:03.000 --> 00:00:03.010
こんにちは

00:00:03.010 --> 00:00:05.000
こんにちは
今日はいい天気です。
"""
    segs = parse_vtt(vtt)
    assert [s["text"] for s in segs] == ["こんにちは", "今日はいい天気です。"]
