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
    v = SAMPLES / ".gen" / "talk_sample.mp4"
    if not v.exists():
        subprocess.run(["bash", str(SAMPLES / "make_sample_video.sh")], check=True)
    return v
