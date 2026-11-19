#!/usr/bin/env python3
"""build_compare.py — 候補のファーストビューを並べた compare.html を1ファイルで生成する。

使い方:
  python3 build_compare.py <candidates_dir> [--out <compare.html>]

<candidates_dir>/meta.json の書式（例: works/<slug>/candidates/meta.json）:
{
  "title": "比較ページの見出し",
  "lead": "1〜2行の説明",
  "kind": "ui" | "logic",               # ui=10案, logic=3〜5案 を想定
  "viewport": [1280, 800],              # 各案HTMLの想定サイズ（ファーストビュー）
  "context": ["前提・仮説1", "..."],
  "axes": "比較軸の説明（任意）",
  "recommended": "D",
  "recommend_reason": "推奨理由",
  "candidates": [
    {"id": "A", "name": "案の名前", "file": "A.html",
     "aim": "狙い", "fit": "向くケース", "weak": "弱点",
     "effort": "規模の目安", "tags": ["自動度: 高"]}
  ],
  "questions": [                         # 任意: 手戻りが大きい質問（最大3）
    {"id": "Q1", "q": "質問", "hypothesis": "仮説", "options": ["選択肢1", "選択肢2"]}
  ],
  "if_answer": [{"when": "回答が〜なら", "then": "推奨は〜"}]   # 任意
}

出力の compare.html は外部ファイルに依存しない（各案は iframe srcdoc で埋め込み）。
ページ下部で「案の選択」「質問への回答」「補足」をまとめて返信用テキストにコピーできる。
"""
from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

CSS = r"""
:root{--bg:#f5f4f0;--card:#fff;--ink:#1c1c1e;--sub:#5d5d63;--line:#e0ded7;--accent:#1f5eff;
--rec:#c2410c;--rec-bg:#fff4ed;--chip:#efeee9;--shadow:0 1px 2px rgba(0,0,0,.06),0 4px 16px rgba(0,0,0,.05)}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#121214;--card:#1c1c20;--ink:#f1f1f3;
--sub:#a4a4ad;--line:#33333a;--accent:#7aa2ff;--rec:#ff8a4c;--rec-bg:#2a1b13;--chip:#2a2a30;--shadow:none}}
:root[data-theme=dark]{--bg:#121214;--card:#1c1c20;--ink:#f1f1f3;--sub:#a4a4ad;--line:#33333a;--accent:#7aa2ff;
--rec:#ff8a4c;--rec-bg:#2a1b13;--chip:#2a2a30;--shadow:none}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP","Yu Gothic UI",sans-serif;padding-bottom:120px}
.wrap{max-width:1360px;margin:0 auto;padding:28px 24px}
header h1{font-size:24px;line-height:1.35;letter-spacing:.01em}
header .lead{color:var(--sub);margin-top:6px}
.ctx{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:16px;margin:20px 0 8px}
.box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow)}
.box h2{font-size:13px;letter-spacing:.06em;color:var(--sub);margin-bottom:8px;font-weight:600}
.box ul{padding-left:1.1em}.box li{margin:2px 0}
.rec{border-color:var(--rec);background:var(--rec-bg)}
.rec h2{color:var(--rec)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,400px),1fr));gap:20px;margin-top:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:var(--shadow);display:flex;flex-direction:column}
.card.is-rec{border:2px solid var(--rec)}
.card.is-sel{outline:3px solid var(--accent);outline-offset:2px}
.ch{display:flex;align-items:center;gap:10px;padding:12px 14px 10px}
.cid{flex:none;width:32px;height:32px;border-radius:8px;background:var(--ink);color:var(--card);display:grid;place-items:center;font-weight:700}
.cname{font-weight:700;font-size:16px;line-height:1.35;flex:1;min-width:0}
.badge{flex:none;font-size:12px;font-weight:700;color:#fff;background:var(--rec);border-radius:999px;padding:2px 10px}
.frame{position:relative;background:#0b0b0c;overflow:hidden;cursor:zoom-in;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.frame iframe{position:absolute;left:0;top:0;border:0;transform-origin:0 0;pointer-events:none;background:#fff}
dl{padding:12px 14px 4px;display:grid;grid-template-columns:auto 1fr;gap:6px 12px;font-size:14px}
dt{color:var(--sub);font-weight:600;white-space:nowrap}
dd{min-width:0}
.tags{display:flex;flex-wrap:wrap;gap:6px;padding:6px 14px 0}
.tags span{font-size:12px;background:var(--chip);border-radius:6px;padding:2px 8px;color:var(--sub)}
.pick{margin-top:auto;padding:12px 14px 14px}
.pick label{display:flex;align-items:center;justify-content:center;gap:8px;border:1px solid var(--line);border-radius:10px;padding:10px;cursor:pointer;font-weight:600}
.pick input{accent-color:var(--accent);width:18px;height:18px}
section.qs{margin-top:28px}
section.qs h2,section.ifa h2{font-size:18px;margin-bottom:10px}
.q{margin-bottom:12px}
.q .qt{font-weight:700}
.q .hy{color:var(--sub);font-size:13px;margin:2px 0 8px}
.opts{display:flex;flex-wrap:wrap;gap:8px}
.opts label{border:1px solid var(--line);border-radius:999px;padding:6px 12px;cursor:pointer;font-size:14px;background:var(--card)}
.opts input{margin-right:6px;accent-color:var(--accent)}
section.ifa{margin-top:24px}
table{width:100%;border-collapse:collapse;font-size:14px;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--sub);font-weight:600;font-size:13px}
.bar{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);box-shadow:0 -4px 16px rgba(0,0,0,.08)}
.bar .in{max-width:1360px;margin:0 auto;padding:12px 24px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.bar .sel{font-weight:700;flex:1;min-width:200px}
.bar textarea{flex:2;min-width:220px;height:44px;resize:vertical;border:1px solid var(--line);border-radius:10px;padding:10px;font:inherit;background:var(--bg);color:var(--ink)}
.bar button{border:0;background:var(--accent);color:#fff;font:inherit;font-weight:700;border-radius:10px;padding:11px 18px;cursor:pointer}
.bar .done{font-size:13px;color:var(--sub)}
dialog{border:0;border-radius:12px;padding:0;max-width:96vw;max-height:92vh;background:var(--card)}
dialog::backdrop{background:rgba(0,0,0,.6)}
dialog .dh{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-bottom:1px solid var(--line);gap:12px}
dialog .dh button{border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:8px;padding:6px 12px;font:inherit;cursor:pointer}
dialog .db{overflow:auto;max-height:calc(92vh - 52px)}
dialog iframe{border:0;display:block;background:#fff}
@media (max-width:720px){.wrap{padding:20px 16px}header h1{font-size:20px}.bar .in{padding:10px 16px}
.bar textarea{order:3;flex-basis:100%;height:40px}}
"""

JS = r"""
const VW=__VW__,VH=__VH__;
function fit(){document.querySelectorAll('.frame').forEach(f=>{const s=f.clientWidth/VW;const i=f.querySelector('iframe');
 i.style.width=VW+'px';i.style.height=VH+'px';i.style.transform='scale('+s+')';f.style.height=(VH*s)+'px';});}
new ResizeObserver(fit).observe(document.body);fit();
const cards=[...document.querySelectorAll('.card')];
function selected(){const r=document.querySelector('input[name=pick]:checked');return r?cards.find(c=>c.dataset.id===r.value):null;}
function render(){const c=selected();cards.forEach(x=>x.classList.toggle('is-sel',x===c));
 document.getElementById('sel').textContent=c?('選択中: 案'+c.dataset.id+'「'+c.dataset.name+'」'):'案を選んでください（未選択なら「おまかせ」= 推奨案）';}
document.addEventListener('change',render);render();
function prompt(){const c=selected();const lines=[];
 lines.push(c?('案'+c.dataset.id+'「'+c.dataset.name+'」で進めて。'):'おまかせ（推奨案）で進めて。');
 document.querySelectorAll('.q').forEach(q=>{const a=q.querySelector('input:checked');if(a)lines.push(q.dataset.id+' '+q.dataset.label+': '+a.value);});
 const m=document.getElementById('memo').value.trim();if(m)lines.push('補足: '+m);return lines.join('\n');}
document.getElementById('copy').addEventListener('click',async()=>{const t=prompt();const d=document.getElementById('done');
 try{await navigator.clipboard.writeText(t);d.textContent='コピーしました。チャットに貼り付けて送ってください。';}
 catch(e){const ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();
  const ok=document.execCommand('copy');ta.remove();
  d.textContent=ok?'コピーしました。チャットに貼り付けて送ってください。':'コピーできませんでした: '+t.replace(/\n/g,' / ');}
});
const dlg=document.getElementById('dlg');
document.querySelectorAll('.frame').forEach(f=>f.addEventListener('click',()=>{const i=f.querySelector('iframe');
 const n=dlg.querySelector('iframe');n.srcdoc=i.srcdoc;n.width=VW;n.height=VH;dlg.querySelector('.dt').textContent=f.dataset.title;dlg.showModal();}));
dlg.querySelector('button').addEventListener('click',()=>dlg.close());
"""


def build(cdir: Path, out: Path | None) -> Path:
    meta = json.loads((cdir / "meta.json").read_text(encoding="utf-8"))
    vw, vh = meta.get("viewport", [1280, 800])
    rec = meta.get("recommended", "")
    e = escape

    ctx_items = "".join(f"<li>{e(x)}</li>" for x in meta.get("context", []))
    ctx_html = f'<div class="box"><h2>前提・仮説</h2><ul>{ctx_items}</ul>' + (
        f'<p style="margin-top:8px;color:var(--sub);font-size:14px">{e(meta["axes"])}</p>' if meta.get("axes") else "") + "</div>"
    rec_c = next((c for c in meta["candidates"] if c["id"] == rec), None)
    rec_html = (f'<div class="box rec"><h2>推奨：案{e(rec)}「{e(rec_c["name"])}」</h2>'
                f'<p>{e(meta.get("recommend_reason", ""))}</p></div>') if rec_c else ""

    cards = []
    for c in meta["candidates"]:
        src = (cdir / c["file"]).read_text(encoding="utf-8")
        is_rec = c["id"] == rec
        tags = "".join(f"<span>{e(t)}</span>" for t in c.get("tags", []))
        cards.append(f"""
<article class="card{' is-rec' if is_rec else ''}" data-id="{e(c['id'])}" data-name="{e(c['name'])}">
  <div class="ch"><div class="cid">{e(c['id'])}</div><div class="cname">{e(c['name'])}</div>{'<span class="badge">推奨</span>' if is_rec else ''}</div>
  <div class="frame" data-title="案{e(c['id'])}「{e(c['name'])}」" title="クリックで原寸表示" style="aspect-ratio:{vw}/{vh}"><iframe loading="lazy" srcdoc="{e(src, quote=True)}" title="案{e(c['id'])}"></iframe></div>
  <dl><dt>狙い</dt><dd>{e(c['aim'])}</dd><dt>向くケース</dt><dd>{e(c['fit'])}</dd><dt>弱点</dt><dd>{e(c['weak'])}</dd>{f"<dt>規模</dt><dd>{e(c['effort'])}</dd>" if c.get('effort') else ''}</dl>
  {f'<div class="tags">{tags}</div>' if tags else ''}
  <div class="pick"><label><input type="radio" name="pick" value="{e(c['id'])}">この案にする</label></div>
</article>""")

    qs = meta.get("questions", [])
    qs_html = ""
    if qs:
        items = []
        for q in qs:
            opts = "".join(
                f'<label><input type="radio" name="{e(q["id"])}" value="{e(o)}">{e(o)}</label>' for o in q.get("options", []))
            items.append(f'<div class="q box" data-id="{e(q["id"])}" data-label="{e(q.get("label", q["id"]))}">'
                         f'<div class="qt">{e(q["id"])}. {e(q["q"])}</div>'
                         f'<div class="hy">仮説（未回答ならこれで進めます）: {e(q.get("hypothesis", ""))}</div>'
                         f'<div class="opts">{opts}</div></div>')
        qs_html = f'<section class="qs"><h2>確認したいこと（最大3つ・答えられる分だけ）</h2>{"".join(items)}</section>'

    ifa = meta.get("if_answer", [])
    ifa_html = ""
    if ifa:
        rows = "".join(f"<tr><td>{e(r['when'])}</td><td>{e(r['then'])}</td></tr>" for r in ifa)
        ifa_html = f'<section class="ifa"><h2>回答次第で推奨はこう変わる</h2><table><tr><th>回答</th><th>推奨</th></tr>{rows}</table></section>'

    html = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(meta['title'])}</title><style>{CSS}</style></head>
<body><div class="wrap">
<header><h1>{e(meta['title'])}</h1><p class="lead">{e(meta.get('lead', ''))}</p></header>
<div class="ctx">{ctx_html}{rec_html}</div>
<div class="grid">{''.join(cards)}</div>
{qs_html}{ifa_html}
</div>
<div class="bar"><div class="in"><div class="sel" id="sel"></div>
<textarea id="memo" placeholder="補足（任意）: 例) 店のInstagram用にも使いたい"></textarea>
<button id="copy">選択をコピー</button><span class="done" id="done"></span></div></div>
<dialog id="dlg"><div class="dh"><strong class="dt"></strong><button>閉じる</button></div><div class="db"><iframe></iframe></div></dialog>
<script>{JS.replace('__VW__', str(vw)).replace('__VH__', str(vh))}</script>
</body></html>"""
    out = out or cdir.parent / "compare.html"
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    o = Path(a[a.index("--out") + 1]) if "--out" in a else None
    print(build(Path(a[0]), o))
