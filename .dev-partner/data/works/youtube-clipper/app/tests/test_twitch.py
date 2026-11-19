"""B-012: Twitch の取り込み（通信しない部分）。本物の Twitch での取得は CI の確認（twitch probe）で行う。"""
import pytest

from clipper import twitch as T


@pytest.mark.parametrize("url,kind,vid", [
    ("https://www.twitch.tv/videos/2299887766", "vod", "2299887766"),
    ("https://m.twitch.tv/videos/2299887766?t=1h2m3s", "vod", "2299887766"),
    ("twitch.tv/videos/123", "vod", "123"),
    ("https://www.twitch.tv/somechannel/v/987654", "vod", "987654"),
    ("  https://www.twitch.tv/videos/55\n", "vod", "55"),
    ("https://clips.twitch.tv/FunnyClipName-abc", "clip", None),
    ("https://www.twitch.tv/somechannel/clip/FunnyClip", "clip", None),
    ("https://www.twitch.tv/somechannel", "channel", None),
    ("https://www.twitch.tv/somechannel/videos?filter=archives", "channel", None),
    ("https://www.youtube.com/watch?v=abc", "youtube", None),
    ("https://youtu.be/abc", "youtube", None),
    ("配信の動画", "other", None),
])
def test_parse_url(url, kind, vid):
    r = T.parse_url(url)
    assert r["kind"] == kind
    if vid:
        assert r["id"] == vid and r["url"] == f"https://www.twitch.tv/videos/{vid}"
    else:
        assert r["message"]


# ---------------------------------------------------------------- チャットの取得（偽の GraphQL）
def make_msgs(times):
    return [{"id": f"m{i}", "t": t, "text": f"msg{i}"} for i, t in enumerate(times)]


class FakeGql:
    """Twitch の GraphQL の代わり。ページは3件ずつ。cursor_ok=False ならカーソル送りを断る（integrity のエラー）。"""
    def __init__(self, msgs, cursor_ok=True, persisted_ok=True, size=3):
        self.msgs, self.cursor_ok, self.persisted_ok, self.size = msgs, cursor_ok, persisted_ok, size
        self.calls = []

    def page(self, start):
        chunk = self.msgs[start:start + self.size]
        edges = [{"cursor": str(start + k + 1),
                  "node": {"id": m["id"], "contentOffsetSeconds": int(m["t"]),
                           "message": {"fragments": [{"text": m["text"]}]}}} for k, m in enumerate(chunk)]
        return {"data": {"video": {"comments": {"edges": edges,
                                                "pageInfo": {"hasNextPage": start + self.size < len(self.msgs)}}}}}

    def __call__(self, body):
        persisted = isinstance(body, list)
        v = body[0]["variables"] if persisted else body["variables"]
        self.calls.append(("persisted" if persisted else "query", "cursor" if v.get("cursor") else "offset"))
        if persisted and not self.persisted_ok:
            return [{"errors": [{"message": "PersistedQueryNotFound"}]}]
        if v.get("cursor"):
            if not self.cursor_ok:
                out = {"errors": [{"message": "failed integrity check"}]}
                return [out] if persisted else out
            out = self.page(int(v["cursor"]))
        else:
            off = v.get("contentOffsetSeconds", v.get("offset", 0))
            out = self.page(next((i for i, m in enumerate(self.msgs) if int(m["t"]) >= off), len(self.msgs)))
        return [out] if persisted else out


def test_fetch_chat_by_cursor():
    msgs = make_msgs([1, 2, 3, 5, 8, 13, 21, 34])
    g = FakeGql(msgs)
    r = T.fetch_chat("1", post=g, sleep=0)
    assert [m["t"] for m in r["messages"]] == [1, 2, 3, 5, 8, 13, 21, 34]
    assert r["method"] == "persisted/cursor" and r["pages"] == 3


def test_fetch_chat_falls_back_to_offset_without_duplicates():
    # 同じ秒に複数のコメント（ページより多い）があっても、重複なく最後まで取る
    msgs = make_msgs([0, 1, 1, 1, 1, 2, 4, 4, 7, 9, 30, 31])
    g = FakeGql(msgs, cursor_ok=False)
    r = T.fetch_chat("1", post=g, sleep=0)
    got = [m["text"] for m in r["messages"]]
    assert len(got) == len(set(got))
    assert r["method"] == "persisted/offset"
    assert [m["t"] for m in r["messages"]][-2:] == [30, 31]
    assert any("integrity" in n for n in r["notes"])
    # 同じ秒の4件のうち、3件ずつのページで取りこぼすのは最大1件まで
    assert len(got) >= len(msgs) - 1


def test_fetch_chat_uses_query_when_persisted_is_gone():
    msgs = make_msgs([1, 2, 3, 4, 5])
    g = FakeGql(msgs, persisted_ok=False)
    r = T.fetch_chat("1", post=g, sleep=0)
    assert r["method"] == "query/cursor" and len(r["messages"]) == 5


def test_fetch_chat_until_stops_early():
    msgs = make_msgs(list(range(0, 3000, 10)))
    g = FakeGql(msgs)
    r = T.fetch_chat("1", until=95, post=g, sleep=0)
    assert r["messages"][-1]["t"] <= 95 and len(r["messages"]) == 10
    assert len(g.calls) < 10       # 全部は取りに行かない


def test_fetch_chat_reports_all_failures():
    def broken(body):
        raise OSError("network down")
    with pytest.raises(T.TwitchError) as e:
        T.fetch_chat("1", post=broken, sleep=0)
    assert "チャットを取得できませんでした" in str(e.value)


def test_parse_page_errors():
    with pytest.raises(T.TwitchError):
        T.parse_page([{"errors": [{"message": "failed integrity check"}]}])
    with pytest.raises(T.TwitchError):
        T.parse_page({"data": {"video": None}})


# ---------------------------------------------------------------- チャットの集計
def steady_with_burst(duration=1800, every=2.0, burst=(600, 615), burst_every=0.25, laugh=False):
    msgs, t = [], 0.0
    while t < duration:
        msgs.append({"t": t, "text": "こんにちは"})
        t += every
    t = burst[0]
    while t < burst[1]:
        msgs.append({"t": t, "text": "草" if laugh else "すごい"})
        t += burst_every
    return msgs


def test_chat_signal_detects_burst_after_the_moment():
    sig = T.ChatSignal(steady_with_burst(), 1800)
    # 映像の 590〜605 秒の出来事に、チャットは 3〜12 秒遅れて反応する（600〜615 秒の急増）
    hot = sig.measure(590, 605)
    calm = sig.measure(1200, 1230)
    assert hot["ratio"] >= 2.5, hot
    assert 0.8 <= calm["ratio"] <= 1.25, calm
    pts, why, _ = sig.bonus(590, 605)
    assert pts >= 15 and why[0].startswith("チャット ×")
    assert sig.bonus(1200, 1230)[0] == 0


def test_chat_signal_laugh_and_quiet_chat():
    sig = T.ChatSignal(steady_with_burst(laugh=True), 1800)
    pts, why, m = sig.bonus(590, 605)
    assert "チャットで笑い" in why and m["laugh"] >= 0.3
    # ほとんどチャットがない配信: 下限の流速があるので、2〜3件で「盛り上がり」にしない
    sparse = T.ChatSignal([{"t": 100, "text": "a"}, {"t": 101, "text": "b"}, {"t": 102, "text": "c"}], 1800)
    assert sparse.bonus(95, 100)[0] == 0


def test_chat_series_for_ui():
    sig = T.ChatSignal(steady_with_burst(duration=600, burst=(0, 0)), 600)
    s = sig.series()
    assert len(s) == 11 and s[0]["n"] == 30


def test_explain_error_messages():
    assert "サブスク" in T.explain_error(RuntimeError("You must be logged into an account that has access to this subscriber-only content"))
    assert "見つかりません" in T.explain_error(RuntimeError("HTTP Error 404: Not Found"))
    assert "接続" in T.explain_error(OSError("getaddrinfo failed"))
    assert "配信中" in T.explain_error(RuntimeError("is live"))
