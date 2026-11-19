# toolkit/INDEX — AIが自作した開発補助ツール

作る条件は2つのうちどちらか：**2回以上使う見込みがある**、または**実際に起きた失敗を防ぐ**。
既存のツールで足りるなら、新しく作らずに改善する。
ここに載っていないファイルは `dp.py lint` でエラーになる（乱立を防ぐため）。

| パス | 用途 | いつ使う | 作った理由（再利用の見込み／防ぐ失敗） | 作成・更新 |
|---|---|---|---|---|
| `dp.py` | backlog の上位N件、書式チェック（lint）、次のID、SessionStart フック | 毎セッションの開始時、データ更新後、提案の追加時 | 毎回使う。上位3件の提示と、表の書式崩れによる並び順の誤りを防ぐ | 2026-11-19 作成 |
| `shot.cjs` | HTML/URL を1280px幅と390px幅でスクショ。横スクロール・はみ出し・JSエラー・画像切れを自動判定。`--must-see` で主要な操作ボタンがファーストビューに入っているかも判定 | 手順2の compare.html、手順4の画面確認 | 見た目が関わる案件すべてで使う。「スクショで自己確認」を毎回同じ基準で行うため | 2026-11-19 作成・改善2回（B-001） |
| `compare/build_compare.py` | 各案のファーストビューHTMLと meta.json から、比較用の compare.html を1ファイルで生成。選択・質問への回答・補足をまとめてコピーするボタン付き | 手順2（UIは10案、ロジック系は3〜5案） | 見た目が関わる案件すべてで使う。毎回比較ページを手書きする繰り返し作業をなくす | 2026-11-19 作成 |
| `tune-panel/build_tune.py` | 数値をスライダーで調整し、変更点をまとめてプロンプトにする HTML を生成（tune.json と preview.html から） | 見た目の数値（サイズ・位置・色・秒数）を感覚で詰めるとき。ユーザーに好みで調整してもらうとき | B-001 で改行・レイアウトの調整に4往復かかった（感覚的な調整）。見た目の案件ごとに使う見込み（B-002） | 2026-11-19 作成 |
| `knowledge/japanese-text.md` | 日本語の文の区切り・話題の区切り・話速・改行の規則 | 日本語のテキストや字幕を扱う案件の手順0 | B-001 で実際に起きた知識不足3件（括弧内の！、話題をまたぐ区間、話速）と改行4往復 | 2026-11-19 作成 |
| `knowledge/short-video.md` | 縦型ショート動画の仕様（解像度・安全領域・ラウドネス）と ffmpeg の実装メモ | 動画を書き出す案件の手順0 | B-001 で調べて確かめた内容を、次の動画案件（B-005 など）で繰り返し調べないため | 2026-11-19 作成 |

## 使い方メモ
```bash
DP="python3 ~/.claude/dev-partner/toolkit/dp.py"
$DP top 3
$DP lint
python3 ~/.claude/dev-partner/toolkit/compare/build_compare.py works/<slug>/candidates   # → works/<slug>/compare.html
node ~/.claude/dev-partner/toolkit/shot.cjs works/<slug>/compare.html --out works/<slug>/shots --full
node ~/.claude/dev-partner/toolkit/shot.cjs http://127.0.0.1:8765/ --must-see "#ok,#ng"   # 主要ボタンがファーストビューにあるか
python3 ~/.claude/dev-partner/toolkit/tune-panel/build_tune.py works/<slug>/tune          # → tune.html
```

## 改善履歴
- 2026-11-19 初版（dp.py / shot.cjs / compare/build_compare.py）
- 2026-11-19 shot.cjs 改善（B-001 で実際に起きた検証漏れへの対策）: ファーストビューを必ず別に撮影する。`--full` では全体を読めるサイズに分割して保存し、固定表示の要素は隠す。以前は、固定バーがページ途中に写り込み、390px幅の全体画像は縮小されて読めなかった
- 2026-11-19 B-001 完了後の環境改善: tune-panel を新規作成（B-002）、shot.cjs に `--must-see` を追加（レビュー画面の操作ボタンが画面外だった失敗への対策）、knowledge/ に2件追加
