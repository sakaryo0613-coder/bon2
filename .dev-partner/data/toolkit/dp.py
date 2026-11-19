#!/usr/bin/env python3
"""dev-partner の補助CLI（標準ライブラリのみ）。

使い方:
  dp.py top [N]                 backlog 上位N件（既定3）を Markdown で表示
  dp.py lint                    backlog.md / projects.md / toolkit/INDEX.md の書式チェック
  dp.py next-id backlog|project|learning
  dp.py score <価値> <工数>       優先度ラベルを表示（例: 高(7)）
  dp.py hook-session-start      SessionStart フック用（stdin の JSON を読み、上位3件を文脈に注入）

上位N件の並び順:
  進行中 → 選択待ち → 未着手（スコア降順、同点は価値降順 → 工数昇順 → ID昇順）
  保留・完了・見送りは対象外。
優先度スコア = 価値×2 − 工数 → 高(6以上) / 中(3〜5) / 低(2以下)
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent  # ~/.claude/dev-partner の実体
BACKLOG = HOME / "backlog.md"
PROJECTS = HOME / "projects.md"
LEARNINGS = HOME / "learnings.md"
TOOLKIT = HOME / "toolkit"
INDEX = TOOLKIT / "INDEX.md"

KINDS = {"拡張", "新規", "環境"}
STATES_ACTIVE = ["進行中", "選択待ち"]
STATES_ALL = {"進行中", "選択待ち", "未着手", "保留", "完了", "見送り"}
BACKLOG_COLS = ["ID", "区分", "提案", "価値", "工数", "優先度", "状態", "対象/場所"]
PROJECT_FIELDS = ["目的", "対象ユーザー", "使う場面", "扱うデータ", "主な機能", "保存場所"]


def score(value: int, effort: int) -> int:
    return value * 2 - effort


def label(s: int) -> str:
    return "高" if s >= 6 else ("中" if s >= 3 else "低")


def priority_text(value: int, effort: int) -> str:
    s = score(value, effort)
    return f"{label(s)}({s})"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def parse_table(text: str, first_col: str) -> tuple[list[str], list[list[str]]]:
    """先頭列名が first_col の最初の Markdown 表を返す。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        cells = split_row(line)
        if cells and cells[0] == first_col:
            header = cells
            rows = []
            for row in lines[i + 2:]:
                if not row.strip().startswith("|"):
                    break
                rows.append(split_row(row))
            return header, rows
    return [], []


def split_row(line: str) -> list[str]:
    s = line.strip()
    if not s.startswith("|"):
        return []
    return [c.strip() for c in s.strip("|").split("|")]


def backlog_items() -> list[dict]:
    header, rows = parse_table(read(BACKLOG), "ID")
    items = []
    for r in rows:
        if len(r) != len(header):
            items.append({"_bad": r})
            continue
        items.append(dict(zip(header, r)))
    return items


def detail_next_action(item_id: str) -> str:
    text = read(BACKLOG)
    m = re.search(rf"^### {re.escape(item_id)}\b.*?$(.*?)(?=^### |\Z)", text, re.M | re.S)
    if not m:
        return ""
    for line in m.group(1).splitlines():
        line = line.strip()
        if line.startswith("- 次のアクション:") or line.startswith("- 次のアクション："):
            return re.split(r"[:：]", line, maxsplit=1)[1].strip()
    return ""


def ranked() -> list[dict]:
    items = [it for it in backlog_items() if "_bad" not in it]

    def key(it):
        st = it.get("状態", "")
        try:
            v, e = int(it["価値"]), int(it["工数"])
        except (ValueError, KeyError):
            v, e = 0, 9
        group = STATES_ACTIVE.index(st) if st in STATES_ACTIVE else 2
        return (group, -score(v, e), -v, e, it.get("ID", ""))

    return sorted([it for it in items if it.get("状態") in STATES_ACTIVE + ["未着手"]], key=key)


def format_top(n: int) -> str:
    items = ranked()[:n]
    if not items:
        return "（backlog に未着手・進行中の候補はありません）"
    out = []
    for i, it in enumerate(items, 1):
        line = (f"{i}. **[{it['ID']}]【{it['区分']}】{it['提案']}** — {it['状態']}｜"
                f"価値{it['価値']}・工数{it['工数']}・優先度 {it['優先度']}｜{it['対象/場所']}")
        nxt = detail_next_action(it["ID"])
        if nxt:
            line += f"\n   次のアクション: {nxt}"
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------- lint
def lint() -> list[str]:
    issues: list[str] = []

    # backlog
    header, _ = parse_table(read(BACKLOG), "ID")
    if header != BACKLOG_COLS:
        issues.append(f"backlog.md: 表の列が {BACKLOG_COLS} ではありません（実際: {header}）")
    seen = set()
    text = read(BACKLOG)
    for it in backlog_items():
        if "_bad" in it:
            issues.append(f"backlog.md: 列数が合わない行: {it['_bad']}")
            continue
        bid = it["ID"]
        if not re.fullmatch(r"B-\d{3}", bid):
            issues.append(f"backlog.md: ID形式が不正: {bid}（B-001 形式）")
        if bid in seen:
            issues.append(f"backlog.md: ID重複: {bid}")
        seen.add(bid)
        if it["区分"] not in KINDS:
            issues.append(f"backlog.md {bid}: 区分は {sorted(KINDS)} のいずれか（実際: {it['区分']}）")
        if it["状態"] not in STATES_ALL:
            issues.append(f"backlog.md {bid}: 状態は {sorted(STATES_ALL)} のいずれか（実際: {it['状態']}）")
        try:
            v, e = int(it["価値"]), int(it["工数"])
            if not (1 <= v <= 5 and 1 <= e <= 5):
                raise ValueError
            if it["優先度"] != priority_text(v, e):
                issues.append(f"backlog.md {bid}: 優先度は {priority_text(v, e)} のはず（実際: {it['優先度']}）")
        except ValueError:
            issues.append(f"backlog.md {bid}: 価値・工数は1〜5の整数")
        if not re.search(rf"^### {re.escape(bid)}\b", text, re.M):
            issues.append(f"backlog.md {bid}: 詳細セクション '### {bid} ...' がありません")

    # projects
    ptext = read(PROJECTS)
    for m in re.finditer(r"^## (P-\d{3}) .*?$(.*?)(?=^## |\Z)", ptext, re.M | re.S):
        pid, body = m.group(1), m.group(2)
        for f in PROJECT_FIELDS:
            if not re.search(rf"^- {f}[:：]", body, re.M):
                issues.append(f"projects.md {pid}: 項目「{f}」がありません")

    # toolkit INDEX
    itext = read(INDEX)
    listed = set(re.findall(r"^\|\s*`([^`]+)`", itext, re.M))
    for path in listed:
        if not (TOOLKIT / path).exists():
            issues.append(f"toolkit/INDEX.md: 記載された `{path}` が存在しません")
    for p in sorted(TOOLKIT.rglob("*")):
        if p.is_dir() or p.name == "INDEX.md" or "__pycache__" in p.parts or p.name.startswith("."):
            continue
        rel = p.relative_to(TOOLKIT).as_posix()
        if rel not in listed and not any(rel.startswith(d.rstrip("/") + "/") for d in listed if d.endswith("/")):
            issues.append(f"toolkit/INDEX.md: `{rel}` が一覧にありません（乱立防止のため必ず登録）")
    return issues


def next_id(kind: str) -> str:
    if kind == "backlog":
        nums = [int(x) for x in re.findall(r"\bB-(\d{3})\b", read(BACKLOG))]
        return f"B-{max(nums, default=0) + 1:03d}"
    if kind == "project":
        nums = [int(x) for x in re.findall(r"^## P-(\d{3})", read(PROJECTS), re.M)]
        return f"P-{max(nums, default=-1) + 1:03d}"
    if kind == "learning":
        nums = [int(x) for x in re.findall(r"^## L-(\d{3})", read(LEARNINGS), re.M)]
        return f"L-{max(nums, default=0) + 1:03d}"
    raise SystemExit("next-id の種類は backlog|project|learning")


# ---------------------------------------------------------------- hook
def hook_session_start() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    source = data.get("source", "startup")
    if source not in ("startup", "clear"):
        return
    # ユーザー設定とプロジェクト設定の両方に登録されていても1回だけ出す
    sid = data.get("session_id") or ""
    if sid:
        marker = Path(tempfile.gettempdir()) / f"dev-partner-ss-{re.sub(r'[^A-Za-z0-9_-]', '', sid)}-{source}"
        if marker.exists():
            return
        try:
            marker.write_text("1")
        except OSError:
            pass

    real = HOME
    msg = f"""[dev-partner] 新しいセッションです。
- モノづくり（ツール・アプリ・サイト・スクリプト等の作成/改修）の依頼は、dev-partner スキル（~/.claude/skills/dev-partner/SKILL.md）の手順で進めること。
- ユーザーの発話が具体的な依頼でない場合（挨拶・雑談・「何かある？」「続きは？」など）は、下の backlog 上位3件を提示し、どれに着手するか（「おまかせ」可）を尋ねること。
- 具体的な依頼がある場合はそれを優先し、最初の応答の末尾に上位3件を短く添える（このセッションで1回だけ）。
- 定期実行・バックグラウンドでの自動実行はしない。
- dev-partner データの実体: {real}（更新したら、そのリポジトリで commit & push して保存する）

## backlog 上位3件
{format_top(3)}
"""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": msg}}, ensure_ascii=False))


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "top":
        print(format_top(int(argv[1]) if len(argv) > 1 else 3))
    elif cmd == "lint":
        issues = lint()
        if issues:
            print("NG: " + str(len(issues)) + " 件")
            for i in issues:
                print(" - " + i)
            return 1
        print("OK: backlog.md / projects.md / toolkit/INDEX.md に問題なし")
    elif cmd == "next-id":
        print(next_id(argv[1] if len(argv) > 1 else ""))
    elif cmd == "score":
        print(priority_text(int(argv[1]), int(argv[2])))
    elif cmd == "hook-session-start":
        try:
            hook_session_start()
        except Exception as e:  # セッション開始を絶対に妨げない
            print(f"[dev-partner] hook error: {e}", file=sys.stderr)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
