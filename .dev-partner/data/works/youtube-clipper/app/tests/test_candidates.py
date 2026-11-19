"""AC1〜AC5, AC10: 候補の生成と採点。"""
import time

from clipper import config as C
from clipper.candidates import n_candidates, rule_candidates


def _cover(c, r):
    return max(0.0, min(c["end"], r["end"]) - max(c["start"], r["start"]))


def test_boundaries_length_overlap_count(sents, expected):
    cands = rule_candidates(sents, expected["duration"])
    starts = {s["id"]: s["start"] for s in sents}
    ends = {s["id"]: s["end"] for s in sents}
    # AC4 候補数
    assert len(cands) == expected["n_candidates"] == n_candidates(expected["duration"])
    for c in cands:
        # AC1 文の境目（余白は前後の文に食い込まない）
        assert c["start"] <= starts[c["start_sid"]] and c["end"] >= ends[c["end_sid"]]
        if c["start_sid"] > 0:
            assert c["start"] >= ends[c["start_sid"] - 1]
        if c["end_sid"] + 1 < len(sents):
            assert c["end"] <= starts[c["end_sid"] + 1]
        # AC2 長さ
        assert C.CLIP_MIN <= c["end"] - c["start"] <= C.CLIP_MAX
    # AC3 重なりなし
    s = sorted(cands, key=lambda c: c["start"])
    assert all(a["end_sid"] < b["start_sid"] and a["end"] <= b["start"] for a, b in zip(s, s[1:]))


def test_highlight_recall_and_no_bad(sents, expected):
    """AC5 仕込んだ見どころ5か所のうち4か所以上が入り、あいさつ・告知は入らない。"""
    cands = rule_candidates(sents, expected["duration"])
    hits = {k for k, r in expected["highlights"].items()
            for c in cands if _cover(c, r) >= 0.6 * (r["end"] - r["start"])}
    bad = [(c["id"], k) for k, r in expected["bad"].items()
           for c in cands if _cover(c, r) >= 0.5 * (c["end"] - c["start"])]
    assert len(hits) >= expected["min_highlight_hits"], f"hits={sorted(hits)}"
    assert not bad, bad


def test_titles_fit(sents, expected):
    for c in rule_candidates(sents, expected["duration"]):
        assert 0 < len(c["title"]) <= C.TITLE_LINE_CHARS * C.TITLE_LINES


def test_n_candidates_rule():
    assert n_candidates(60 * 60) == 12
    assert n_candidates(5 * 60) == C.CAND_MIN
    assert n_candidates(4 * 3600) == C.CAND_MAX


def test_speed_60min(sents):
    """AC10 60分相当の文字起こしでも5秒以内。"""
    span = sents[-1]["end"] + 2
    long = []
    for k in range(10):
        for s in sents:
            long.append({**s, "id": len(long), "start": s["start"] + k * span, "end": s["end"] + k * span})
    t = time.time()
    cands = rule_candidates(long, span * 10)
    assert time.time() - t < 5.0
    assert len(cands) == n_candidates(span * 10)
