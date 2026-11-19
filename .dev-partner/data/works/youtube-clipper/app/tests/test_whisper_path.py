"""文字起こしの経路のうち、モデルなしで確かめられる部分（B-008 の Windows CI で PyAV の版違いが見つかったため追加）。"""
import subprocess
import sys
import types

import numpy as np

from clipper.transcript import load_audio_16k, transcribe_whisper


def test_load_audio_16k(tmp_path):
    wav = tmp_path / "t.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-ar", "44100", "-ac", "2", str(wav)], check=True)
    a = load_audio_16k(wav)
    assert a.dtype == np.float32 and abs(len(a) - 32000) <= 160     # 2秒 × 16kHz
    assert 0.1 < float(np.abs(a).max()) <= 1.0


def test_transcribe_passes_array_and_reports_progress(tmp_path, monkeypatch, sample_video):
    """WhisperModel を差し替え、音声配列で呼ばれること・進み具合が出ること・語の時刻が残ることを確認する。"""
    seen = {}

    class FakeModel:
        def __init__(self, name, **kw):
            seen["init"] = (name, kw)

        def transcribe(self, audio, **kw):
            seen["audio"], seen["kw"] = audio, kw
            w = types.SimpleNamespace(start=1.0, end=1.5, word="テスト")
            segs = [types.SimpleNamespace(start=1.0, end=2.0, text=" テストです。", words=[w])]
            return iter(segs), types.SimpleNamespace(duration=4.0)

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    prog = []
    out = transcribe_whisper(sample_video, "tiny", progress=lambda p, m: prog.append(p), download_root=tmp_path, duration=4.0)
    assert isinstance(seen["audio"], np.ndarray) and seen["audio"].dtype == np.float32
    assert seen["init"][1]["download_root"] == str(tmp_path) and seen["kw"]["word_timestamps"]
    assert out == [{"start": 1.0, "end": 2.0, "text": "テストです。", "words": [{"start": 1.0, "end": 1.5, "text": "テスト"}]}]
    assert prog[0] == -1 and prog[-1] == 50.0


def test_pipeline_with_numpy_typed_whisper_output(tmp_path, monkeypatch, sample_video):
    """B-004 の実機で起きた不具合の再現: faster-whisper が numpy の型（int64・float32）で時刻を返しても、
    文字起こし → 文の分割 → 候補 → JSON の保存まで通る。"""
    from clipper.pipeline import build
    texts = ["今日はいい天気ですね。", "朝から散歩に行きました。", "公園で猫を見つけたんです。[笑]",
             "その猫がすごく人なつっこくて。", "結論から言うと、毎朝行くことにしました。", "みなさんも試してみてください。"]

    class FakeModel:
        def __init__(self, name, **kw):
            pass

        def transcribe(self, audio, **kw):
            segs = []
            t = np.int64(2)
            for i in range(30):                           # 約4分ぶん（2分の動画でも区間の上限で切れる）
                txt = texts[i % len(texts)]
                end = np.float32(float(t) + 3.5)
                w = types.SimpleNamespace(start=np.int64(int(t)), end=end, word=txt)
                segs.append(types.SimpleNamespace(start=np.int64(int(t)), end=end, text=txt, words=[w]))
                t = np.int64(int(t) + 4)
            return iter(segs), types.SimpleNamespace(duration=np.float64(120.0))

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    wd = build(sample_video, tmp_path / "np.clipper", subs=None, scorer="rule", model="tiny",
               download_root=tmp_path / "m", log=lambda *a: None)
    import json
    sents = json.loads((wd.path / "sentences.json").read_text(encoding="utf-8"))
    cands = json.loads((wd.path / "candidates.json").read_text(encoding="utf-8"))
    assert len(sents) == 30 and all(isinstance(s["start"], float) for s in sents)
    assert cands and (wd.path / "decisions.json").exists()
