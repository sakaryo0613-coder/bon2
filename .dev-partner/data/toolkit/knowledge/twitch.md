# ナレッジ: Twitch のアーカイブ（動画・チャット）を取り込む

Twitch の配信を扱う案件の手順0で読む。B-012 で、GitHub Actions から本物の Twitch に対して確かめた内容（2026-11）。
実物: `works/youtube-clipper/app/clipper/twitch.py`、テスト: `app/tests/test_twitch.py`

## この環境から
- **このクラウド環境は twitch.tv・gql.twitch.tv に接続できない**（プロキシで遮断）。PyPI は通る
- 本物での確認は GitHub Actions（ubuntu・windows どちらも接続できる）で行う。`clipper.exe --twitch-probe <dir>` が、公開のアーカイブを探して情報・チャット（冒頭10分）・動画（冒頭20秒）を取り、`twitch_probe.json` に結果を書く
- アーカイブは期限で消えるので、テストに固定の URL は使えない。チャンネルの「動画」の一覧（`https://www.twitch.tv/<login>/videos?filter=archives&sort=time`）を yt-dlp の `extract_flat` で読み、最新から順に試す。**最新のものは配信中（`is_live`）のことがある**ので飛ばす

## 動画（yt-dlp）
| 項目 | やり方 | 注意 |
|---|---|---|
| 情報 | `YoutubeDL.extract_info(url, download=False)` → title・uploader・duration・is_live | 配信中なら断る。サブスク限定はエラーに `subscriber-only` / `logged into` が入る |
| 取得 | `process_ie_result(info, download=True)`、`format: b[height<=720]`、`concurrent_fragment_downloads: 8` | HLS（.ts の断片）。mp4 にまとめるのに ffmpeg が要る（アプリは同梱の ffmpeg を PATH に入れている）。進み具合は `fragment_index / fragment_count` |
| 区間だけ | `download_ranges: download_range_func(None, [(0, 20)])` | 確認用。20秒で約7MB・1.6秒（720p） |
| アプリに同梱 | PyInstaller の spec で `yt_dlp` を excludes から外し、hiddenimports に入れる（関数の中で import しているため） | yt-dlp 自身に PyInstaller の hook がある。標準出力のないアプリでは `logger` を渡してログファイルに回す |
| 更新 | yt-dlp はサイトの変更に合わせて頻繁に更新される | アプリ内の更新（B-013）で、新しい版を出すたびに最新の yt-dlp が入る |
- yt-dlp 2026.10 には、Twitch のチャット（以前の `rechat` 字幕）はない。v5 API の廃止で使えなくなった

## チャット（GraphQL）
```
POST https://gql.twitch.tv/gql
Client-ID: kimne78kx3ncx6brgo4mv6wki5h1ko   （Web サイトの公開のクライアント ID）
[{"operationName": "VideoCommentsByOffsetOrCursor",
  "variables": {"videoID": "<番号>", "contentOffsetSeconds": 0},          ← 時刻送り
  "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"}}}]
→ data.video.comments.edges[].node { id, contentOffsetSeconds, message.fragments[].text }, pageInfo.hasNextPage
```
- **カーソル送り（`"cursor": ...`）は `failed integrity check` で断られる**（2026-11、CI で確認）。時刻送りは通る
- 時刻送りは、最後のコメントの秒から次を頼む。前のページと重なるので **id で重複を除く**。同じ秒にページより多いコメントがあると進まないので、新しいものがなければ1秒進める
- 量の目安: 冒頭10分で158件・4ページ・0.9秒（大手の配信の開始直後）。3時間でも数十〜数百ページ
- Twitch の変更に備え、取り方を順に試す（登録済みの問い合わせでカーソル → 時刻 → 問い合わせの本文で同じ2通り）。全部だめならチャットなしで続ける（チャットは補助）

## チャットを盛り上がりの信号にする
| 項目 | 値 | 理由 |
|---|---|---|
| 数える幅 | 10秒 | 1秒ではぶれる |
| 平常 | 前後5分の中央値（下限 0.1件/秒） | 配信の時間帯で流速が変わる。中央値は山に引っ張られない。下限がないと、静かな配信で2〜3件が「×5」になる |
| 遅れ | 映像の区間の 3〜12 秒後ろ | 配信の遅延（2〜5秒）＋読んで打つ時間 |
| 盛り上がり | 1.5倍以上かつ5件以上 | |
| 加点 | 最大+25 × **山をどれだけ含むか（capture）** | capture がないと、山に少しでもかかる長い区間（前の話題をくっつけたもの）が満点になり、話題をまたいだ候補が選ばれた（B-012 の試作） |
| 笑い | 「草」「www」「LUL」「KEKW」「888」などが30%以上で+5 | |

## 規約と案内
- Twitch の規約は、用意された手段以外でのダウンロードを広く認めていない。自分のアーカイブは「動画プロデューサー」からダウンロードできる
- 画面と説明書に「自分のアーカイブ、または切り抜きを許可されたアーカイブだけ」と書く
- アーカイブの期限: 通常7日、アフィリエイト14日、パートナー・Turbo・Prime など60日
