# ナレッジ: ショート動画（縦型）の書き出し

縦型動画・動画加工の案件の着手前（手順0）に読む。数値の根拠は `works/youtube-clipper/02-spec.md` を参照。

## 仕様の関係
```
プラットフォーム（Shorts / TikTok / Reels）
 ├─ 解像度 1080×1920・9:16・30fps（トーク動画なら60fpsは不要）
 ├─ 長さ: 3つ共通で出すなら60秒以内（Shorts 単体は最長3分）
 ├─ 操作UIに隠れる範囲 → 文字の安全領域: y=240〜1520、x=60〜1020
 │    上部 0〜240: 検索・カメラ／下部 1520〜: タイトル・チャンネル名・いいね等
 └─ 再生側のラウドネス正規化の基準 ≒ −14 LUFS → 書き出しも −14 LUFS・TP −1.5dB
```

## ffmpeg の実装メモ（すべて B-001 で動作確認済み）
| やりたいこと | 方法 | 注意 |
|---|---|---|
| 区間の切り出し | `-ss <開始> -i 元 -t <長さ>`、出力側にも `-t` | 入力前の `-ss` は再エンコードありなら正確。長さの誤差は0.00秒だった |
| 横動画を縦の帯レイアウトに | `color` で背景 → `drawbox` で帯 → `overlay` で 1080×608 の動画を y=656 に置く | `shortest=1` を付けないと背景の長さで止まらない |
| 文字（タイトル・字幕・出典） | ASS 字幕を `subtitles=clip.ass` で焼き込む。`PlayResX/Y` を 1080×1920 にし、`\pos` と `\an` で座標を指定する | 字幕ファイルは**相対パス**で渡す（cwd を一時フォルダにする）。Windows のドライブ文字 `C:` のエスケープ問題を避けるため |
| ラウドネス | 2パスの `loudnorm`（1回目に `print_format=json` で測定 → 2回目に `measured_*` と `linear=true`） | 1パスの動的モードは短いクリップでずれやすい |
| フォント | fc-list で `:lang=ja` を確認。Mac は Hiragino Sans、Windows は Yu Gothic UI | クラウドの Linux 環境には IPAGothic がある（太字なし） |
| 検証 | ffprobe（解像度・fps・コーデック・長さ）、`ebur128`（Integrated LUFS）、rawvideo rgb24 で1フレームを取り出し、画素で安全領域の外が背景のままか確認 | `works/youtube-clipper/app/tests/test_render.py` がひな形 |

## プレビューで見た目を調整する
- `works/youtube-clipper/tune/`（`toolkit/tune-panel` で生成）でレイアウトの数値を動かし、変更点をプロンプトにする
- CSS のプレビューは libass の描画の近似。縁取りの太さなどは実際の書き出しで最終確認する
