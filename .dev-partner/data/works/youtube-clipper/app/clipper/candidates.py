"""候補の生成・採点・選定。候補は必ず「文IDの範囲」で表す（＝文の途中で切れない）。"""
from __future__ import annotations

import re

from . import config as C

LAUGH = re.compile(r"\[笑\]|（笑）|\(笑\)|w{3,}|ｗ{3,}|ははは|あはは|笑っちゃ|爆笑")
EMOTION = re.compile(r"マジで|本当に|ほんとに|めちゃくちゃ|めっちゃ|ヤバ|やば|すご|最高|正直|感動|びっくり|衝撃|地獄")
CONCLUSION = re.compile(r"第[1一]位|[1一]位|結論|一番|いちばん|結果|つまり|ポイントは|コツ")
QUESTION = re.compile(r"[？?]$")
CONNECTIVE = re.compile(r"^(で、|でも、|だから|それで|あと、|そしたら|なので|ちなみに)")
GREETING = re.compile(r"こんばんは|こんにちは|おはよう|よろしくお願いします|おつかれ|お疲れ|チャンネル登録|高評価|告知|概要欄|メンバーシップ|始まりました|おやすみ")
SENT_END = re.compile(r"[。！？!?」』）)](\[[^\]]*\])?$")
TOPIC_SHIFT = re.compile(r"話は変わ|^次は|^最後に|^ここで|ところで|^さて|^それでは|^というわけで|の話をします|を話します")
TOPIC_GAP = 0.8   # 話題の切れ目とみなす無音（秒）。文中の間（0.2〜0.5秒）より長い


def n_candidates(duration_sec: float) -> int:
    return int(min(C.CAND_MAX, max(C.CAND_MIN, round(duration_sec / 60 * C.CAND_PER_MIN))))


def clip_bounds(sents: list[dict], a: int, b: int, duration: float | None = None) -> tuple[float, float]:
    """文 a〜b の切り出し範囲。前後に余白を付けるが、隣の文には食い込ませない。"""
    lo = sents[a - 1]["end"] if a > 0 else 0.0
    hi = sents[b + 1]["start"] if b + 1 < len(sents) else (duration if duration else sents[b]["end"] + C.PAD_END)
    start = max(sents[a]["start"] - C.PAD_START, lo)
    end = min(sents[b]["end"] + C.PAD_END, hi)
    return round(start, 3), round(end, 3)


def windows(sents: list[dict], duration: float | None = None):
    """長さ CLIP_MIN〜CLIP_MAX の文範囲をすべて列挙する。"""
    n = len(sents)
    for a in range(n):
        for b in range(a, n):
            s, e = clip_bounds(sents, a, b, duration)
            d = e - s
            if d > C.CLIP_MAX:
                break
            if d >= C.CLIP_MIN:
                yield a, b, s, e


def topic_starts(sents: list[dict]) -> list[bool]:
    """各文が話題の始まりらしいか（直前の無音が長い、または転換のフレーズで始まる）。"""
    out = []
    for i, s in enumerate(sents):
        gap = s["start"] - sents[i - 1]["end"] if i > 0 else 99
        out.append(gap >= TOPIC_GAP or bool(TOPIC_SHIFT.search(s["text"])))
    return out


def rule_score(ss: list[dict], dur: float, starts: list[bool] | None = None, ends_topic: bool = True) -> tuple[int, list[str]]:
    """starts: 区間内の各文が話題の始まりか。ends_topic: 区間の直後が話題の切れ目か。"""
    starts = starts or [True] + [False] * (len(ss) - 1)
    texts = [s["text"] for s in ss]
    joined = "".join(texts)
    score, why = 40, []
    laughs = sum(len(LAUGH.findall(t)) for t in texts)
    if laughs:
        score += min(24, 12 * laughs); why.append("笑い")
    emo = sum(len(EMOTION.findall(t)) for t in texts)
    if emo:
        score += min(20, 5 * emo); why.append("感情・強調")
    concl = sum(len(CONCLUSION.findall(t)) for t in texts)
    if concl:
        score += min(20, 10 * concl); why.append("結論・順位")
    q_idx = [i for i, t in enumerate(texts) if QUESTION.search(t)]
    if q_idx and q_idx[0] < len(texts) - 1:
        score += 10; why.append("質問→回答")
    if starts[0]:
        score += 8
    if SENT_END.search(texts[-1]) and ends_topic:
        score += 10; why.append("話が完結")
    inner = sum(starts[1:])
    if inner:
        score -= min(24, 12 * inner); why.append("−話題をまたぐ")
    if CONNECTIVE.search(texts[0]):
        score -= 10; why.append("−途中から始まる")
    greet = sum(len(GREETING.findall(t)) for t in texts)
    if greet:
        score -= 15 * min(2, greet); why.append("−あいさつ・告知")
    cps = len(re.sub(r"\[[^\]]*\]", "", joined)) / max(dur, 1)
    if 4 <= cps <= 9:
        score += 5
    if C.CLIP_SWEET[0] <= dur <= C.CLIP_SWEET[1]:
        score += 5
    return max(0, min(100, score)), why


def fit_title(t: str) -> str:
    """タイトルを 2行×13字 に収める。長いときは上限内の最後の読点で切る（なければ「…」で切る）。"""
    t = t.strip().rstrip("。、")
    limit = C.TITLE_LINE_CHARS * C.TITLE_LINES
    if len(t) <= limit:
        return t
    cut = max((i for i, ch in enumerate(t[:limit]) if ch in "、！？!?" and i >= 8), default=None)
    return t[:cut].rstrip("、") if cut else t[: limit - 1] + "…"


def make_title(ss: list[dict]) -> str:
    """一番“強い”文をタイトル候補にする（LLMがない場合の簡易版）。"""
    def strength(t):
        return (len(CONCLUSION.findall(t)) * 3 + len(LAUGH.findall(t)) * 2 + len(EMOTION.findall(t))
                + (2 if QUESTION.search(t) else 0) - (3 if GREETING.search(t) else 0))
    best = max(ss, key=lambda s: strength(s["text"]))["text"]
    best = re.sub(r"\[[^\]]*\]", "", best)
    return fit_title(CONNECTIVE.sub("", best))


def overlaps(a1: int, b1: int, a2: int, b2: int) -> bool:
    return not (b1 < a2 or b2 < a1)


def select(scored: list[dict], n: int) -> list[dict]:
    """スコアの高い順に、重ならないものを n 件。"""
    chosen = []
    for c in sorted(scored, key=lambda c: (-c["score"], c["start"])):
        if any(overlaps(c["start_sid"], c["end_sid"], x["start_sid"], x["end_sid"]) for x in chosen):
            continue
        chosen.append(c)
        if len(chosen) >= n:
            break
    chosen.sort(key=lambda c: c["start"])
    for i, c in enumerate(chosen, 1):
        c["id"] = f"c{i:02d}"
    return chosen


def rule_candidates(sents: list[dict], duration: float, n: int | None = None, chat=None) -> list[dict]:
    """chat: twitch.ChatSignal（あれば、チャットの盛り上がりを加点する）"""
    n = n or n_candidates(duration)
    starts = topic_starts(sents)
    scored = []
    for a, b, s, e in windows(sents, duration):
        ss = sents[a:b + 1]
        ends_topic = b + 1 >= len(sents) or starts[b + 1]
        sc, why = rule_score(ss, e - s, starts[a:b + 1], ends_topic)
        if chat is not None and len(chat):
            pts, cwhy, _ = chat.bonus(s, e)
            sc, why = max(0, min(100, sc + pts)), why + cwhy
        scored.append({"start_sid": a, "end_sid": b, "start": s, "end": e, "duration": round(e - s, 3),
                       "score": sc, "reasons": why, "scorer": "rule"})
    chosen = select(scored, n)
    for c in chosen:
        c["title"] = make_title(sents[c["start_sid"]:c["end_sid"] + 1])
    return chosen


def normalize(raw: list[dict], sents: list[dict], duration: float, n: int) -> list[dict]:
    """LLMなど外部から来た候補を検証・補正する（範囲外・長さ違反・重なりを直すか捨てる）。"""
    fixed = []
    last = len(sents) - 1
    for r in raw:
        try:
            a, b = int(r["start_sid"]), int(r["end_sid"])
        except (KeyError, TypeError, ValueError):
            continue
        a, b = max(0, min(a, last)), max(0, min(b, last))
        if a > b:
            a, b = b, a
        s, e = clip_bounds(sents, a, b, duration)
        while e - s > C.CLIP_MAX and b > a:          # 長すぎ → 末尾の文から削る
            b -= 1; s, e = clip_bounds(sents, a, b, duration)
        while e - s < C.CLIP_MIN and b < last:        # 短すぎ → 次の文を足す
            b += 1; s, e = clip_bounds(sents, a, b, duration)
        while e - s > C.CLIP_MAX and b > a:
            b -= 1; s, e = clip_bounds(sents, a, b, duration)
        if not (C.CLIP_MIN <= e - s <= C.CLIP_MAX):
            continue
        title = fit_title(str(r.get("title") or make_title(sents[a:b + 1])))
        fixed.append({"start_sid": a, "end_sid": b, "start": s, "end": e, "duration": round(e - s, 3),
                      "score": int(max(0, min(100, r.get("score", 50)))), "reasons": list(r.get("reasons") or [])[:4],
                      "title": title, "scorer": r.get("scorer", "llm")})
    return select(fixed, n)


def annotate_chat(cands: list[dict], chat) -> list[dict]:
    """候補にチャットの反応（倍率・件数）を付け、盛り上がっていれば理由の先頭に出す（Claude の採点でも同じ表示にする）。"""
    if chat is None or not len(chat):
        return cands
    for c in cands:
        pts, cwhy, m = chat.bonus(c["start"], c["end"])
        c["chat"] = m
        c["reasons"] = cwhy + [r for r in c.get("reasons", []) if not r.startswith("チャット")]
    return cands
