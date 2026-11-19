"""Twitch のアーカイブの取り込み（B-012）。

- URL の判定: アーカイブ（twitch.tv/videos/<番号>）だけを受け付け、それ以外は理由と次の操作を1文で返す
- 動画の取得: yt-dlp（Python から呼ぶ。アプリに同梱）。720p まで（帯レイアウトでは幅1080に縮めるので十分）
- チャットの取得: Twitch の GraphQL（Web サイトがチャットのリプレイに使うのと同じ公開の窓口）。時刻と本文だけを使う
- チャットの集計: 平常（前後5分の中央値）に比べて何倍か。チャットは映像より遅れるので、区間の 3〜12 秒後ろを数える

使えるのは、自分のアーカイブと、切り抜きを許可されたアーカイブだけ。
"""
from __future__ import annotations

import json
import re
import statistics
import time
import urllib.error
import urllib.request
from bisect import bisect_left, bisect_right
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------- URL の判定
VOD_RE = re.compile(r"(?:^|//|\b)(?:www\.|m\.|go\.)?twitch\.tv/(?:videos/|[\w-]+/v(?:ideo)?/)(\d+)", re.I)
CLIP_RE = re.compile(r"clips\.twitch\.tv/|twitch\.tv/[\w-]+/clip/", re.I)
CHANNEL_RE = re.compile(r"(?:^|//)(?:www\.|m\.)?twitch\.tv/[\w-]+/?(?:videos/?)?(?:[?#].*)?$", re.I)
YOUTUBE_RE = re.compile(r"(?:youtube\.com|youtu\.be)/", re.I)

MSG = {
    "clip": "クリップは短すぎるため使えません。元の配信のアーカイブ（twitch.tv/videos/…）の URL を貼ってください",
    "youtube": "YouTube の動画は URL では取り込めません（YouTube の利用規約のため）。YouTube Studio からダウンロードして「動画を選ぶ」で選んでください",
    "channel": "チャンネルの URL です。チャンネルの「動画」から取り込みたい配信を開き、その URL（twitch.tv/videos/…）を貼ってください",
    "other": "Twitch のアーカイブの URL（https://www.twitch.tv/videos/数字）を貼ってください",
}


def parse_url(s: str) -> dict:
    s = (s or "").strip()
    m = VOD_RE.search(s)
    if m:
        vid = m.group(1)
        return {"kind": "vod", "id": vid, "url": f"https://www.twitch.tv/videos/{vid}"}
    for kind, rx in (("clip", CLIP_RE), ("youtube", YOUTUBE_RE), ("channel", CHANNEL_RE)):
        if rx.search(s):
            return {"kind": kind, "message": MSG[kind]}
    return {"kind": "other", "message": MSG["other"]}


class TwitchError(RuntimeError):
    """画面にそのまま出せる日本語の説明を持つ例外。"""


def explain_error(e: BaseException) -> str:
    """yt-dlp や通信のエラーを、利用者向けの1文にする。"""
    t = str(e)
    low = t.lower()
    if "subscriber" in low or "login" in low or "logged" in low:
        return "このアーカイブはサブスク限定などで、ログインが必要です。clipper では取り込めません"
    if "does not exist" in low or "404" in low or "not found" in low or "unavailable" in low:
        return "アーカイブが見つかりません。期限（通常7〜60日）が過ぎて消えたか、非公開にされた可能性があります"
    if "is live" in low or "is currently live" in low:
        return "まだ配信中です。配信が終わってアーカイブになってから貼ってください"
    if isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError)) or "timed out" in low or "getaddrinfo" in low \
            or "connection" in low:
        return "Twitch に接続できません。インターネットの接続を確認して、もう一度お試しください"
    return f"Twitch から取得できませんでした（{t[:160]}）"


# ---------------------------------------------------------------- 動画
MAX_HEIGHT = 720


def _ydl(opts: dict):
    try:
        import yt_dlp
    except ImportError:
        raise TwitchError("URL から取り込むには yt-dlp が必要です（pip install yt-dlp）")
    base = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True}
    return yt_dlp.YoutubeDL({**base, **opts})


def fetch_info(url: str) -> dict:
    """ダウンロードせずに、題名・配信者・長さを取る。配信中なら断る。"""
    try:
        with _ydl({}) as y:
            info = y.extract_info(url, download=False)
    except TwitchError:
        raise
    except Exception as e:
        raise TwitchError(explain_error(e)) from e
    if info.get("is_live"):
        raise TwitchError(explain_error(RuntimeError("is live")))
    return info


def download_vod(url: str, dest: Path, progress: Callable[[float, str], None] | None = None,
                 section: tuple[float, float] | None = None, info: dict | None = None) -> tuple[Path, dict]:
    """動画を dest/source.mp4 に保存する。section=(開始, 終了) を渡すとその区間だけ（確認用）。"""
    dest.mkdir(parents=True, exist_ok=True)
    progress = progress or (lambda pct, msg: None)

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            frag, nfrag = d.get("fragment_index"), d.get("fragment_count")
            pct = 100.0 * frag / nfrag if frag and nfrag else (100.0 * d.get("downloaded_bytes", 0) / total if total else 0.0)
            mb = d.get("downloaded_bytes", 0) / 1e6
            progress(min(pct, 99.0), f"動画を取得しています（{mb:,.0f}MB）")

    opts = {"format": f"b[height<={MAX_HEIGHT}]/bv*[height<={MAX_HEIGHT}]+ba/b",
            "outtmpl": str(dest / "source.%(ext)s"), "merge_output_format": "mp4",
            "concurrent_fragment_downloads": 8, "progress_hooks": [hook], "retries": 5, "fragment_retries": 10}
    if section:
        from yt_dlp.utils import download_range_func
        opts["download_ranges"] = download_range_func(None, [section])
    try:
        with _ydl(opts) as y:
            info = y.process_ie_result(info, download=True) if info else y.extract_info(url, download=True)
    except TwitchError:
        raise
    except Exception as e:
        raise TwitchError(explain_error(e)) from e
    files = [p for p in dest.glob("source.*") if p.suffix.lower() in (".mp4", ".mkv", ".ts", ".webm")]
    if not files:
        raise TwitchError("動画を保存できませんでした（ファイルが見つかりません）")
    progress(100.0, "動画を取得しました")
    return files[0], info


# ---------------------------------------------------------------- チャット
GQL_URL = "https://gql.twitch.tv/gql"
CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"     # Twitch の Web サイトの公開のクライアント ID
COMMENTS_OP = "VideoCommentsByOffsetOrCursor"
COMMENTS_HASH = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"
COMMENTS_QUERY = ("query($id: ID!, $offset: Int, $cursor: Cursor) { video(id: $id) { "
                  "comments(contentOffsetSeconds: $offset, after: $cursor) { "
                  "edges { cursor node { id contentOffsetSeconds message { fragments { text } } } } "
                  "pageInfo { hasNextPage } } } }")
PAGE_SLEEP = 0.05


def _post(body, timeout: float = 20.0):
    req = urllib.request.Request(GQL_URL, data=json.dumps(body).encode("utf-8"), method="POST", headers={
        "Client-ID": CLIENT_ID, "Content-Type": "text/plain;charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
        "Origin": "https://www.twitch.tv", "Referer": "https://www.twitch.tv/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _request(video_id: str, style: str, offset: int | None, cursor: str | None):
    """style: persisted（Web サイトと同じ登録済みの問い合わせ）／ query（問い合わせの本文を送る）"""
    if style == "persisted":
        v = {"videoID": str(video_id)}
        if cursor:
            v["cursor"] = cursor
        else:
            v["contentOffsetSeconds"] = int(offset or 0)
        return [{"operationName": COMMENTS_OP, "variables": v,
                 "extensions": {"persistedQuery": {"version": 1, "sha256Hash": COMMENTS_HASH}}}]
    v = {"id": str(video_id)}
    if cursor:
        v["cursor"] = cursor
    else:
        v["offset"] = int(offset or 0)
    return {"query": COMMENTS_QUERY, "variables": v}


def parse_page(resp) -> tuple[list[dict], bool, str | None]:
    """GraphQL の応答から (コメント, 続きがあるか, 最後のカーソル) を取り出す。エラーなら TwitchError。"""
    item = resp[0] if isinstance(resp, list) and resp else resp
    if not isinstance(item, dict):
        raise TwitchError("チャットの応答を読み取れません")
    if item.get("errors"):
        raise TwitchError("; ".join(str(e.get("message", e)) for e in item["errors"])[:300])
    video = (item.get("data") or {}).get("video")
    if video is None:
        raise TwitchError("アーカイブが見つかりません（チャット）")
    comments = video.get("comments") or {}
    edges = comments.get("edges") or []
    out = []
    for ed in edges:
        node = ed.get("node") or {}
        if node.get("contentOffsetSeconds") is None:
            continue
        frags = ((node.get("message") or {}).get("fragments")) or []
        out.append({"id": str(node.get("id") or ""), "t": float(node["contentOffsetSeconds"]),
                    "text": "".join(str(f.get("text") or "") for f in frags)})
    cursor = edges[-1].get("cursor") if edges else None
    return out, bool((comments.get("pageInfo") or {}).get("hasNextPage")), cursor


def fetch_chat(video_id: str, until: float | None = None, post: Callable = _post,
               progress: Callable[[float, str], None] | None = None, sleep: float = PAGE_SLEEP,
               max_pages: int = 50000) -> dict:
    """チャットを最初から（until 秒まで）取る。

    取り方は、Twitch の変更に備えて順に試す: 登録済みの問い合わせでカーソル送り → 時刻送り → 問い合わせ本文で同じ2通り。
    時刻送りでは、同じコメントを id で除き、進まないときは1秒進める。
    戻り値: {"messages": [{"t", "text"}...], "method": "persisted/cursor" など, "pages": n}
    """
    progress = progress or (lambda pct, msg: None)
    errors = []
    for style in ("persisted", "query"):
        try:
            first, has_next, cursor = parse_page(post(_request(video_id, style, 0, None)))
        except Exception as e:  # 次の取り方を試す
            errors.append(f"{style}: {type(e).__name__}: {e}"[:200])
            continue
        seen = {m["id"] for m in first if m["id"]}
        msgs = list(first)
        mode, pages, stale = "cursor", 1, 0
        offset = int(first[-1]["t"]) if first else 0
        while has_next and pages < max_pages and (until is None or offset <= until):
            time.sleep(sleep)
            try:
                if mode == "cursor":
                    page, has_next, cursor = parse_page(post(_request(video_id, style, None, cursor)))
                else:
                    page, _, _ = parse_page(post(_request(video_id, style, offset, None)))
            except Exception as e:
                if mode == "cursor":            # カーソル送りが断られたら、時刻送りに切り替える
                    errors.append(f"{style}/cursor: {type(e).__name__}: {e}"[:200])
                    mode = "offset"
                    continue
                raise TwitchError(explain_error(e)) from e
            pages += 1
            new = [m for m in page if not m["id"] or m["id"] not in seen]
            seen.update(m["id"] for m in new if m["id"])
            msgs.extend(new)
            if page:
                offset = max(offset, int(page[-1]["t"]))
            if mode == "offset":
                if not page:
                    break                        # 最後まで来た
                stale = 0 if new else stale + 1
                if stale >= 5:
                    break
                if not new:
                    offset += 1                  # 同じ秒にページより多くのコメントがある・進まないときは1秒進める
            if msgs:
                done = 100.0 * msgs[-1]["t"] / until if until else 0.0
                progress(min(99.0, done), f"チャットを取得しています（{len(msgs):,}件）")
        if until is not None:
            msgs = [m for m in msgs if m["t"] <= until]
        msgs.sort(key=lambda m: m["t"])
        progress(100.0, f"チャットを取得しました（{len(msgs):,}件）")
        return {"messages": [{"t": m["t"], "text": m["text"]} for m in msgs], "method": f"{style}/{mode}",
                "pages": pages, "notes": errors}
    raise TwitchError("チャットを取得できませんでした（" + " / ".join(errors)[:300] + "）")


# ---------------------------------------------------------------- チャットの集計
BIN = 10.0               # 秒。チャットの件数を数える幅
BASE_HALF = 300.0        # 平常の基準は、前後5分の中央値（配信の時間帯で流速が変わるため、全体の平均は使わない）
MIN_RATE = 0.1           # 平常の流速の下限（件/秒 = 10秒に1件）。チャットが少ない配信で倍率が暴れないように
LAG = (3.0, 12.0)        # 映像からチャットまでの遅れ（配信の遅延2〜5秒＋打つ時間）。区間の 3〜12 秒後ろを数える
MIN_COUNT = 5            # これより少ない件数では盛り上がりと見なさない
HOT = 1.5                # 平常のこの倍率以上で「盛り上がり」
LAUGH = re.compile(r"草|[wｗ]{3,}|笑|ワロ|LUL|KEKW|OMEGALUL|lol|LOL|[8８]{3,}")


class ChatSignal:
    def __init__(self, messages: list[dict], duration: float):
        self.times = sorted(float(m["t"]) for m in messages)
        self.texts = [m["text"] for m in sorted(messages, key=lambda m: m["t"])]
        self.duration = max(duration, self.times[-1] if self.times else 0.0, BIN)
        nb = int(self.duration // BIN) + 1
        self.bins = [0] * nb
        for t in self.times:
            self.bins[min(nb - 1, int(t // BIN))] += 1

    def __len__(self):
        return len(self.times)

    def base_rate(self, center: float) -> float:
        k = int(BASE_HALF // BIN)
        i = int(center // BIN)
        window = self.bins[max(0, i - k): i + k + 1]
        return max(MIN_RATE, statistics.median(window) / BIN if window else 0.0)

    def measure(self, start: float, end: float) -> dict:
        """映像の区間 [start, end] に対するチャットの反応。"""
        a, b = start + LAG[0], end + LAG[1]
        i, j = bisect_left(self.times, a), bisect_right(self.times, b)
        count = j - i
        expected = self.base_rate((a + b) / 2) * (b - a)
        laughs = sum(1 for t in self.texts[i:j] if LAUGH.search(t))
        return {"ratio": round(count / expected, 2) if expected else 0.0, "count": count,
                "laugh": round(laughs / count, 2) if count else 0.0}

    def bonus(self, start: float, end: float) -> tuple[int, list[str], dict]:
        """ルール採点への加点。×2で+10、×3.5以上で上限+25（言葉の「笑い」の加点と同じ程度）。"""
        m = self.measure(start, end)
        pts, why = 0, []
        if m["count"] >= MIN_COUNT and m["ratio"] >= HOT:
            pts += min(25, round(10 * (m["ratio"] - 1)))
            why.append(f"チャット ×{m['ratio']:.1f}")
            if m["laugh"] >= 0.3:
                pts += 5
                why.append("チャットで笑い")
        return pts, why, m

    def series(self, step: float = 60.0) -> list[dict]:
        """画面用の流速の推移（1分ごとの件数）。"""
        k = max(1, int(step // BIN))
        return [{"t": i * BIN, "n": sum(self.bins[i:i + k])} for i in range(0, len(self.bins), k)]


# ---------------------------------------------------------------- 確認用（CI）
PROBE_CHANNELS = ("fps_shaka", "stylishnoob4", "kato_junichi0817", "twitchjapan", "shroud", "summit1g")


def recent_vods(channels=PROBE_CHANNELS, per_channel: int = 3):
    """公開のアーカイブの URL を順に返す（期限で消えるので、固定の URL は使えない）。配信中のものも混ざる。"""
    for ch in channels:
        try:
            with _ydl({"extract_flat": True, "playlistend": per_channel}) as y:
                res = y.extract_info(f"https://www.twitch.tv/{ch}/videos?filter=archives&sort=time", download=False)
        except Exception:
            continue
        for e in res.get("entries") or []:
            r = parse_url(e.get("url") or "")
            if r["kind"] == "vod":
                yield r["url"]


def probe(outdir: Path, url: str | None = None, chat_until: float = 600.0, video_secs: float = 20.0) -> dict:
    """本物の Twitch から、情報・チャットの冒頭・動画の冒頭を取れるか確かめる（CI 用）。結果は outdir/twitch_probe.json。"""
    outdir.mkdir(parents=True, exist_ok=True)
    res = {"ok": False, "checks": {}, "errors": []}

    def check(name, cond, detail=""):
        res["checks"][name] = {"ok": bool(cond), "detail": str(detail)[:500]}
        if not cond:
            res["errors"].append(f"{name}: {str(detail)[:300]}")

    try:
        info, skipped = None, []
        for u in ([url] if url else recent_vods()):
            try:
                info = fetch_info(u)
                url = u
                break
            except TwitchError as e:          # 配信中・サブスク限定などは飛ばして次へ
                skipped.append(f"{u}: {e}")
        check("vod_found", info, {"url": url, "skipped": skipped})
        if info:
            check("info", info.get("duration"), {k: info.get(k) for k in ("id", "title", "uploader", "duration")})
            vid = parse_url(url)["id"]
            t0 = time.time()
            chat = fetch_chat(vid, until=chat_until)
            n = len(chat["messages"])
            check("chat", n > 0, f"{n} 件 / {chat['method']} / {chat['pages']} ページ / {time.time() - t0:.1f}秒 / {chat['notes']}")
            res["chat_sample"] = chat["messages"][:5]
            sig = ChatSignal(chat["messages"], chat_until)
            res["chat_series"] = sig.series()[:12]
            t0 = time.time()
            path, _ = download_vod(url, outdir / "vod", section=(0.0, video_secs), info=info)
            check("video", path.exists() and path.stat().st_size > 0, f"{path.name} {path.stat().st_size:,} バイト / {time.time() - t0:.1f}秒")
    except Exception as e:
        import traceback
        res["errors"].append(f"{type(e).__name__}: {e}")
        res["trace"] = traceback.format_exc()[-3000:]
    res["ok"] = not res["errors"]
    (outdir / "twitch_probe.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2), flush=True)
    return res


if __name__ == "__main__":   # python -m clipper.twitch probe <出力先> [URL]
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "probe":
        r = probe(Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None)
        sys.exit(0 if r["ok"] else 1)
    print(__doc__)
