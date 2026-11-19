"""AC6: LLM採点の検証・補正と、失敗時の切り替え（API はモック）。"""
from types import SimpleNamespace

import anthropic
import httpx2 as httpx  # anthropic SDK 2.x は httpx2 を使う

from clipper import config as C
from clipper.candidates import normalize
from clipper.llm import LlmCandidate, LlmResult, llm_candidates


class FakeMessages:
    def __init__(self, result=None, stop="end_turn", exc=None):
        self.result, self.stop, self.exc, self.kwargs = result, stop, exc, None

    def parse(self, **kw):
        self.kwargs = kw
        if self.exc:
            raise self.exc
        return SimpleNamespace(stop_reason=self.stop, parsed_output=self.result)


def fake_client(**kw):
    m = FakeMessages(**kw)
    return SimpleNamespace(beta=SimpleNamespace(messages=m)), m


def test_request_shape_and_parse(sents):
    res = LlmResult(candidates=[LlmCandidate(start_id=10, end_id=17, score=90, title="知らないおじさんに先生と呼ばれた話", reasons=["笑い"])])
    client, m = fake_client(result=res)
    out = llm_candidates(sents, 5, "サンプル", client=client, log=lambda *_: None)
    assert out == [{"start_sid": 10, "end_sid": 17, "score": 90, "title": "知らないおじさんに先生と呼ばれた話",
                    "reasons": ["笑い"], "scorer": "llm"}]
    kw = m.kwargs
    assert kw["model"] == C.LLM_MODEL and kw["output_format"] is LlmResult
    assert kw["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in kw["betas"]
    assert kw["output_config"] == {"effort": C.LLM_EFFORT}
    assert "[0]" in kw["messages"][0]["content"] and "thinking" not in kw


def test_refusal_and_errors_fall_back(sents):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    for kw in [dict(stop="refusal", result=LlmResult(candidates=[])),
               dict(result=None),
               dict(exc=anthropic.APIConnectionError(request=req)),
               dict(exc=anthropic.RateLimitError("rate", response=httpx.Response(429, request=req), body=None)),
               dict(exc=TypeError("Could not resolve authentication method"))]:
        client, _ = fake_client(**kw)
        assert llm_candidates(sents, 5, client=client, log=lambda *_: None) is None


def test_normalize_fixes_bad_ranges(sents, expected):
    last = len(sents) - 1
    raw = [
        {"start_sid": 10, "end_sid": 17, "score": 90, "title": "OK"},                # 正常
        {"start_sid": 12, "end_sid": 14, "score": 85, "title": "重なり"},             # 上と重なり点も低い → 落ちる
        {"start_sid": 40, "end_sid": 41, "score": 80, "title": "短すぎ"},             # 20秒未満 → 次の文を足す
        {"start_sid": 50, "end_sid": 75, "score": 70, "title": "長すぎ"},             # 60秒超 → 末尾から削る
        {"start_sid": last + 30, "end_sid": last + 40, "score": 60, "title": "範囲外"},  # 範囲外 → 末尾に丸める
        {"start_sid": "x", "end_sid": 3, "score": 99},                               # 型が不正 → 捨てる
        {"start_sid": 24, "end_sid": 22, "score": 50, "title": "あ" * 40},           # 逆順・長いタイトル
    ]
    out = normalize(raw, sents, expected["duration"], 10)
    titles = [c["title"] for c in out]
    assert "重なり" not in titles and "OK" in titles
    for c in out:
        assert C.CLIP_MIN <= c["end"] - c["start"] <= C.CLIP_MAX
        assert 0 <= c["start_sid"] <= c["end_sid"] <= last
        assert len(c["title"]) <= C.TITLE_LINE_CHARS * C.TITLE_LINES
    s = sorted(out, key=lambda c: c["start_sid"])
    assert all(a["end_sid"] < b["start_sid"] for a, b in zip(s, s[1:]))


def test_prompt_includes_chat_marks(sents, expected):
    """B-012 AC5: チャットが盛り上がった文に「💬×N」が付き、system に意味の説明が入る。"""
    from clipper.twitch import ChatSignal
    from test_candidates import burst_chat
    sig = ChatSignal(burst_chat(expected["duration"]), expected["duration"])
    res = LlmResult(candidates=[LlmCandidate(start_id=7, end_id=13, score=80, title="雨の週の話", reasons=["盛り上がり"])])
    client, m = fake_client(result=res)
    llm_candidates(sents, 5, "配信", client=client, log=lambda *_: None, chat=sig)
    content = m.kwargs["messages"][0]["content"]
    marked = [ln for ln in content.splitlines() if "💬×" in ln]
    assert marked and all(ln.split("]")[0].strip("[") in {str(i) for i in range(5, 14)} for ln in marked), marked
    assert "チャット" in m.kwargs["system"]
    client, m = fake_client(result=res)
    llm_candidates(sents, 5, "配信", client=client, log=lambda *_: None)
    assert "💬" not in m.kwargs["messages"][0]["content"] and "チャット" not in m.kwargs["system"]
