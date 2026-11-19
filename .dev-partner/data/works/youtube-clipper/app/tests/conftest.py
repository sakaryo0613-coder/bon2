import json
import subprocess
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
SAMPLES = APP.parent / "samples"
sys.path.insert(0, str(APP))

from clipper.transcript import load_subs, to_sentences  # noqa: E402


@pytest.fixture(scope="session")
def expected():
    return json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def sents():
    return to_sentences(load_subs(SAMPLES / "talk_sample.srt"))


@pytest.fixture(scope="session")
def sample_video():
    """make_sample_video.sh と同じ内容を Python から作る（Windows でも動くように bash を使わない）。"""
    v = SAMPLES / ".gen" / "talk_sample.mp4"
    if not v.exists():
        v.parent.mkdir(parents=True, exist_ok=True)
        dur = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))["duration"]
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={dur}",
                        "-f", "lavfi", "-i", f"sine=frequency=220:sample_rate=48000:duration={dur}",
                        "-filter_complex", "[1:a]volume='0.25+0.2*sin(2*PI*t/3)':eval=frame[a]",
                        "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                        "-c:a", "aac", "-b:a", "96k", str(v)], check=True)
    return v
