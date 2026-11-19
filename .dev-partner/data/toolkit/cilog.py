#!/usr/bin/env python3
"""cilog.py — GitHub Actions のジョブログを読みやすく要約・検索する。

GitHub の MCP ツール（get_job_logs）の結果は数十万字の1行になり、そのままでは読めない。
保存されたファイル（JSON の logs_content、またはプレーンテキスト）を行に戻し、時刻を外してから、
失敗した箇所と指定した語の前後だけを表示する。

使い方:
  python3 cilog.py <ログファイル>                     要約（全行数・エラー行・失敗した手順の前後）
  python3 cilog.py <ログファイル> <正規表現> [...]     語の前後を表示（-A 行数 / -B 行数 で範囲を変更）
  python3 cilog.py <ログファイル> --json-block '"checks"'   指定した語から始まる JSON の塊（selftest.json など）を表示

表示の最後に「読んだ範囲」（全行数）を必ず出す。要約を書くときは、それを添えること。
"""
from __future__ import annotations

import json
import re
import sys

ERROR_PAT = r"##\[error\]|Traceback|Error:|FAILED|AssertionError|\bfailed\b"


def load(path: str) -> list[str]:
    raw = open(path, encoding="utf-8", errors="replace").read()
    try:
        txt = json.loads(raw).get("logs_content", raw)
    except (ValueError, AttributeError):
        txt = raw
    lines = txt.lstrip("\ufeff").replace("\r\n", "\n").split("\n")
    return [re.sub(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ", "", l) for l in lines]


def show(lines: list[str], pats: list[str], before: int, after: int, limit: int = 20) -> None:
    rx = re.compile("|".join(pats))
    shown, n = set(), 0
    for i, l in enumerate(lines):
        if rx.search(l):
            n += 1
            if n > limit:
                print(f"…（ほかにも一致あり。-n で件数を増やせる）")
                break
            for j in range(max(0, i - before), min(len(lines), i + after + 1)):
                if j not in shown:
                    print(f"{j:6d} {'>' if j == i else ' '} {lines[j][:300]}")
                    shown.add(j)
            print("      --")


def json_block(lines: list[str], start_pat: str) -> None:
    for i, l in enumerate(lines):
        if re.search(start_pat, l):
            depth, out, opened = 0, [], False
            for j in range(i, len(lines)):
                out.append(lines[j])
                depth += lines[j].count("{") - lines[j].count("}")
                opened = opened or "{" in lines[j]
                if opened and depth <= 0:
                    break
            print("\n".join(out))
            return
    print(f"（{start_pat} は見つかりませんでした）")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    lines = load(argv[0])
    before, after, limit, pats, jb = 2, 2, 20, [], None
    it = iter(argv[1:])
    for a in it:
        if a == "-A":
            after = int(next(it))
        elif a == "-B":
            before = int(next(it))
        elif a == "-n":
            limit = int(next(it))
        elif a == "--json-block":
            jb = next(it)
        else:
            pats.append(a)
    if jb:
        json_block(lines, jb)
    elif pats:
        show(lines, pats, before, after, limit)
    else:
        print("== エラーらしい行 ==")
        show(lines, [ERROR_PAT], 3, 3, limit)
    print(f"\n（読んだ範囲: 全 {len(lines)} 行。先頭: {lines[0][:60]!r}）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
