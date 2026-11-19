"""Claude による候補の採点。失敗・拒否・認証なしのときは None を返し、呼び出し側がルール採点に切り替える。"""
from __future__ import annotations

import sys

from pydantic import BaseModel, Field

from . import config as C

SYSTEM = """あなたはYouTubeの切り抜き編集者です。長い動画の文字起こし（番号つきの文の一覧）から、
ショート動画（{min:.0f}〜{max:.0f}秒）として単体で面白く・分かりやすく成立する区間を選びます。

選ぶ基準:
- 冒頭の1文で「何の話か」が分かり、最後の文で話が完結している（オチ・結論・答えがある）
- 笑い、意外な結果、具体的な数字、質問への明確な回答、感情が動く本音など、見どころがある
- 前の文脈を知らないと理解できない区間、あいさつ・告知・雑談のつなぎは選ばない

出力:
- 区間は文の番号で指定する（start_id〜end_id、両端を含む）。各文の時刻を見て、長さを{min:.0f}〜{max:.0f}秒に収める
- 区間どうしは重ならないようにする
- score は0〜100（公開したときに見てもらえる見込み）
- title は動画の上部に出す日本語タイトル（{title_max}字以内、煽りすぎず内容が伝わるもの）
- reasons は選んだ理由の短いラベルを1〜3個（例: 笑い、意外な結果、質問への回答）"""


class LlmCandidate(BaseModel):
    start_id: int
    end_id: int
    score: int = Field(ge=0, le=100)
    title: str
    reasons: list[str]


class LlmResult(BaseModel):
    candidates: list[LlmCandidate]


def _fmt(t: float) -> str:
    m, s = divmod(t, 60)
    h, m = divmod(m, 60)
    return f"{int(h):d}:{int(m):02d}:{s:04.1f}"


def build_prompt(sents: list[dict], n: int, video_title: str = "") -> str:
    lines = [f"[{s['id']}] ({_fmt(s['start'])}–{_fmt(s['end'])}) {s['text']}" for s in sents]
    head = f"動画タイトル: {video_title}\n" if video_title else ""
    return (f"{head}次の文字起こしから、ショート動画の候補を {n + 4} 個まで選んでください（良い順でなくてよい）。\n\n"
            + "\n".join(lines))


def llm_candidates(sents: list[dict], n: int, video_title: str = "", client=None, log=print) -> list[dict] | None:
    try:
        import anthropic
    except ImportError:
        log("[llm] anthropic パッケージがないため、ルール採点を使います（pip install anthropic）")
        return None
    try:
        client = client or anthropic.Anthropic()
        resp = client.beta.messages.parse(
            model=C.LLM_MODEL,
            max_tokens=16000,
            output_config={"effort": C.LLM_EFFORT},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",   # 安全分類で拒否されたときはサーバー側で別モデルに切り替える
            system=SYSTEM.format(min=C.CLIP_MIN, max=C.CLIP_MAX, title_max=C.TITLE_LINE_CHARS * C.TITLE_LINES),
            messages=[{"role": "user", "content": build_prompt(sents, n, video_title)}],
            output_format=LlmResult,
        )
    except anthropic.AuthenticationError:
        log("[llm] APIキーが無効か未設定のため、ルール採点を使います（ANTHROPIC_API_KEY を設定すると Claude で採点します）")
        return None
    except anthropic.RateLimitError:
        log("[llm] レート制限のため、ルール採点を使います")
        return None
    except anthropic.APIStatusError as e:
        log(f"[llm] APIエラー {e.status_code} のため、ルール採点を使います")
        return None
    except anthropic.APIConnectionError:
        log("[llm] APIに接続できないため、ルール採点を使います")
        return None
    except Exception as e:  # 認証情報が見つからない等（SDKの初期化エラーを含む）
        if "authentication" in str(e).lower():
            log("[llm] Claude の認証情報が見つからないため、ルール採点を使います（ANTHROPIC_API_KEY を設定すると Claude で採点します）")
        else:
            log(f"[llm] Claude を使えないため、ルール採点を使います: {type(e).__name__}: {e}")
        return None

    if resp.stop_reason == "refusal":
        log("[llm] 応答が拒否されたため、ルール採点を使います")
        return None
    parsed = getattr(resp, "parsed_output", None)
    if not parsed or not parsed.candidates:
        log(f"[llm] 応答を読み取れなかったため、ルール採点を使います（stop_reason={resp.stop_reason}）")
        return None
    return [{"start_sid": c.start_id, "end_sid": c.end_id, "score": c.score, "title": c.title,
             "reasons": c.reasons, "scorer": "llm"} for c in parsed.candidates]


if __name__ == "__main__":  # 手動確認用: python -m clipper.llm sentences.json
    import json
    sents = json.load(open(sys.argv[1], encoding="utf-8"))
    print(json.dumps(llm_candidates(sents, 5), ensure_ascii=False, indent=2))
