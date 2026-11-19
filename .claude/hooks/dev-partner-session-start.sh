#!/usr/bin/env bash
# SessionStart: dev-partner を ~/.claude にリンクし、新規セッションなら backlog 上位3件を文脈に入れる。
# どんな失敗があってもセッション開始は止めない（常に exit 0）。
ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
bash "$ROOT/.dev-partner/install.sh" --quiet </dev/null >/dev/null 2>&1 || true
python3 "$ROOT/.dev-partner/data/toolkit/dp.py" hook-session-start 2>/dev/null || true
exit 0
