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
