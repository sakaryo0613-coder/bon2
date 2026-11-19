# bon2 リポジトリ

- ルートの `index.html` は「浅草シーシャbon」の公式サイト（GitHub Pages で main ブランチを公開）。
- `.dev-partner/` は dev-partner（モノを作り続ける開発パートナー）の実体。SessionStart フックが `~/.claude/skills/dev-partner` と `~/.claude/dev-partner` をここにリンクする。

## dev-partner のルール
- モノづくり（ツール・アプリ・サイト・スクリプト等の作成/改修）の依頼は、dev-partner スキル（`~/.claude/skills/dev-partner/SKILL.md` ＝ `.dev-partner/skill/SKILL.md`）の手順で進める。
- 依頼がないまま話しかけられたとき（挨拶・雑談・「何かある？」など）は、`python3 ~/.claude/dev-partner/toolkit/dp.py top 3` の結果を提示し、どれに着手するか（「おまかせ」可）を尋ねる。
- 定期実行・バックグラウンドでの自動実行はしない。
- 2026-11-19 ユーザーの許可: 必要と判断したタスクは確認なしで backlog から着手してよい（推奨案で進める）。費用が発生するもの・公開範囲を広げるもの・ユーザーの作業が必要なものだけは事前に確認する（SKILL「次のモノづくりへのつなぎ」）。
- dev-partner のデータ（projects / backlog / learnings / toolkit / works）を更新したら、`dp.py lint` を通してから commit & push する（クラウドの `~/.claude` は揮発するため）。
