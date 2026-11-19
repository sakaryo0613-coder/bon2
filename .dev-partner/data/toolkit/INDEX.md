# toolkit/INDEX — AIが自作した開発補助ツール

作る条件は2つのうちどちらか：**2回以上使う見込みがある**、または**実際に起きた失敗を防ぐ**。
既存のツールで足りるなら、新しく作らずに改善する。
ここに載っていないファイルは `dp.py lint` でエラーになる（乱立を防ぐため）。

| パス | 用途 | いつ使う | 作った理由（再利用の見込み／防ぐ失敗） | 作成・更新 |
|---|---|---|---|---|
| `dp.py` | backlog の上位N件、書式チェック（lint）、次のID、SessionStart フック | 毎セッションの開始時、データ更新後、提案の追加時 | 毎回使う。上位3件の提示と、表の書式崩れによる並び順の誤りを防ぐ | 2026-11-19 作成 |
| `shot.cjs` | HTML/URL を1280px幅と390px幅でスクショ。横スクロール・はみ出し・JSエラー・画像切れを自動判定 | 手順2の compare.html、手順4の画面確認 | 見た目が関わる案件すべてで使う。「スクショで自己確認」を毎回同じ基準で行うため | 2026-11-19 作成・改善（B-001） |
| `compare/build_compare.py` | 各案のファーストビューHTMLと meta.json から、比較用の compare.html を1ファイルで生成。選択・質問への回答・補足をまとめてコピーするボタン付き | 手順2（UIは10案、ロジック系は3〜5案） | 見た目が関わる案件すべてで使う。毎回比較ページを手書きする繰り返し作業をなくす | 2026-11-19 作成 |

## 使い方メモ
```bash
DP="python3 ~/.claude/dev-partner/toolkit/dp.py"
$DP top 3
$DP lint
python3 ~/.claude/dev-partner/toolkit/compare/build_compare.py works/<slug>/candidates   # → works/<slug>/compare.html
node ~/.claude/dev-partner/toolkit/shot.cjs works/<slug>/compare.html --out works/<slug>/shots --full
```

## 改善履歴
- 2026-11-19 初版（dp.py / shot.cjs / compare/build_compare.py）
- 2026-11-19 shot.cjs 改善（B-001 で実際に起きた検証漏れへの対策）: ファーストビューを必ず別に撮影する。`--full` では全体を読めるサイズに分割して保存し、固定表示の要素は隠す。以前は、固定バーがページ途中に写り込み、390px幅の全体画像は縮小されて読めなかった
