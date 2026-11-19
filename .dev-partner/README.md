# .dev-partner — 開発者の立場でモノを作り続けるAIの仕組み

| リポジトリ内 | ~/.claude 側（リンク） | 中身 |
|---|---|---|
| `skill/SKILL.md` | `~/.claude/skills/dev-partner/SKILL.md` | 進め方の本体 |
| `data/projects.md` | `~/.claude/dev-partner/projects.md` | 作ったモノの一覧 |
| `data/backlog.md` | `~/.claude/dev-partner/backlog.md` | 次に作る候補（区分・価値・工数・優先度・状態） |
| `data/learnings.md` | `~/.claude/dev-partner/learnings.md` | 成功例・失敗例 |
| `data/toolkit/` | `~/.claude/dev-partner/toolkit/` | AIが自作した開発補助ツール（一覧は `INDEX.md`） |
| `data/works/` | `~/.claude/dev-partner/works/` | 案件ごとの要件・候補・仕様・検証ログ（成果物の置き場所の指定がない場合は成果物も） |

## しくみ
- **クラウド（bon2 のセッション）**: `.claude/settings.json` の SessionStart フックが毎回 `install.sh` を実行して `~/.claude` にリンクを張る。新しいセッションでは backlog 上位3件を Claude の文脈に入れる。
- **ローカルPC**: `git clone` したあと、次を1回実行する。

  ```bash
  bash .dev-partner/install.sh --global
  ```

  リンクに加えて、`~/.claude/settings.json` に SessionStart フック、`~/.claude/CLAUDE.md` にルールを追加する。どのリポジトリで作業しても有効になる。
- 定期実行・バックグラウンドでの自動実行は行わない。動くのはユーザーが話しかけたときだけ。

## よく使うコマンド
```bash
python3 ~/.claude/dev-partner/toolkit/dp.py top 3     # backlog 上位3件
python3 ~/.claude/dev-partner/toolkit/dp.py lint      # 書式チェック
```
