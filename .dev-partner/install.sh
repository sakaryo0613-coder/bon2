#!/usr/bin/env bash
# dev-partner を ~/.claude にリンクする（何度実行しても同じ結果になる）。
#
#   bash .dev-partner/install.sh            # リンクを張るだけ（クラウドの bon2 セッションはフックがこれを毎回実行する）
#   bash .dev-partner/install.sh --global   # ローカルPC用: さらにユーザー設定へ SessionStart フックと CLAUDE.md のルールを追加
#   bash .dev-partner/install.sh --quiet    # 出力なし（フック用）
#
# 作られるもの:
#   ~/.claude/skills/dev-partner  -> <repo>/.dev-partner/skill
#   ~/.claude/dev-partner         -> <repo>/.dev-partner/data
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
QUIET=0; GLOBAL=0
for a in "$@"; do
  case "$a" in --quiet) QUIET=1;; --global) GLOBAL=1;; esac
done
say() { [ "$QUIET" = 1 ] || echo "$@"; }

link() { # link <target> <linkpath>
  local target="$1" lp="$2"
  mkdir -p "$(dirname "$lp")"
  if [ -L "$lp" ]; then
    [ "$(readlink "$lp")" = "$target" ] && { say "ok      $lp"; return; }
    ln -sfn "$target" "$lp"; say "update  $lp -> $target"
  elif [ -e "$lp" ]; then
    # 既存の実体ディレクトリは消さずに退避する
    local bak="$lp.bak-$(date +%Y%m%d%H%M%S)"
    mv "$lp" "$bak"; ln -s "$target" "$lp"
    say "backup  $lp -> $bak（中身を確認して必要なら .dev-partner へ統合してください）"
  else
    ln -s "$target" "$lp"; say "link    $lp -> $target"
  fi
}

link "$HERE/skill" "$CLAUDE_DIR/skills/dev-partner"
link "$HERE/data"  "$CLAUDE_DIR/dev-partner"

if [ "$GLOBAL" = 1 ]; then
  python3 - "$CLAUDE_DIR" <<'PY'
import json, sys
from pathlib import Path
d = Path(sys.argv[1])
# 1) ~/.claude/settings.json に SessionStart フック（重複しないように追加）
s = d / "settings.json"
cfg = json.loads(s.read_text()) if s.exists() and s.read_text().strip() else {}
cmd = "python3 ~/.claude/dev-partner/toolkit/dp.py hook-session-start"
ss = cfg.setdefault("hooks", {}).setdefault("SessionStart", [])
if not any(h.get("command") == cmd for g in ss for h in g.get("hooks", [])):
    ss.append({"matcher": "startup|clear", "hooks": [{"type": "command", "command": cmd}]})
    s.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    print("hook    " + str(s))
else:
    print("ok      " + str(s))
# 2) ~/.claude/CLAUDE.md にルール（マーカーで囲んで差し替え可能に）
m = d / "CLAUDE.md"
block = """<!-- dev-partner:begin -->
## dev-partner
- モノづくり（ツール・アプリ・サイト・スクリプト等の作成/改修）の依頼は dev-partner スキル（~/.claude/skills/dev-partner/SKILL.md）の手順で進める。
- 依頼がないまま話しかけられたとき（挨拶・雑談・「何かある？」等）は `python3 ~/.claude/dev-partner/toolkit/dp.py top 3` の結果を提示し、どれに着手するか尋ねる。
- 定期実行・バックグラウンドでの自動実行はしない。
<!-- dev-partner:end -->"""
t = m.read_text() if m.exists() else ""
import re
if "<!-- dev-partner:begin -->" in t:
    t = re.sub(r"<!-- dev-partner:begin -->.*?<!-- dev-partner:end -->", block, t, flags=re.S)
else:
    t = (t.rstrip() + "\n\n" if t.strip() else "") + block + "\n"
m.write_text(t)
print("memory  " + str(m))
PY
fi
exit 0
