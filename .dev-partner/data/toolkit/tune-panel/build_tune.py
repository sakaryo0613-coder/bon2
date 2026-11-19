#!/usr/bin/env python3
"""build_tune.py — 数値をスライダーで調整し、変更点をまとめてプロンプトにする HTML ツールを生成する。

使い方:
  python3 build_tune.py <dir> [--out <tune.html>]

<dir>/tune.json:
{
  "title": "何を調整するか",
  "target": "変更を反映するファイル（例: app/clipper/config.py）",
  "viewport": [1080, 1920],                      # preview.html の設計サイズ
  "params": [
    {"key": "TITLE_SIZE", "label": "タイトルの文字サイズ", "value": 72, "min": 40, "max": 110, "step": 2,
     "unit": "px", "css": "--title-size", "note": "任意の補足"},
    {"key": "BAND_COLOR", "label": "帯の色", "type": "color", "value": "#E11D48", "css": "--band-color"}
  ]
}
<dir>/preview.html: CSS変数（var(--title-size) など）で見た目が決まるプレビュー。viewport の大きさで作る。

出力の tune.html は1ファイルで完結する。プレビューは即時に反映され、「変更点をプロンプトにしてコピー」で
「KEY: 変更前 → 変更後」の一覧を、そのままチャットに貼れる文章にする。
"""
from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

PAGE = r"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>
:root{--bg:#f4f4f2;--card:#fff;--ink:#1c1c1e;--sub:#62626a;--line:#deddd6;--accent:#1f5eff;--chg:#c2410c}
@media (prefers-color-scheme:dark){:root{--bg:#121214;--card:#1c1c20;--ink:#f1f1f3;--sub:#a4a4ad;--line:#33333a;--accent:#7aa2ff;--chg:#ff8a4c}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font:14px/1.6 -apple-system,"Hiragino Sans","Noto Sans JP","Yu Gothic UI",sans-serif}
.wrap{display:grid;grid-template-columns:minmax(300px,420px) 1fr;gap:20px;max-width:1300px;margin:0 auto;padding:20px}
h1{font-size:18px;margin-bottom:2px}.lead{color:var(--sub);font-size:13px;margin-bottom:12px}
.ctl{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:6px 14px}
.p{padding:10px 0;border-top:1px solid var(--line)}.p:first-child{border-top:0}
.p .h{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.p label{font-weight:600}.p code{font-size:11.5px;color:var(--sub)}
.p .v{font-variant-numeric:tabular-nums;font-weight:700}.p.chg .v{color:var(--chg)}
.p .r{display:flex;gap:8px;align-items:center;margin-top:4px}
.p input[type=range]{flex:1;accent-color:var(--accent)}
.p input[type=number]{width:76px;font:inherit;padding:2px 6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink)}
.p input[type=color]{width:56px;height:30px;border:1px solid var(--line);border-radius:6px;background:none}
.p .note{font-size:12px;color:var(--sub);margin-top:2px}
.p button{font-size:12px;border:1px solid var(--line);background:var(--bg);color:var(--sub);border-radius:6px;padding:1px 8px;cursor:pointer;visibility:hidden}
.p.chg button{visibility:visible}
.act{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
.act button{font:inherit;font-weight:700;border-radius:10px;padding:10px 14px;cursor:pointer;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.act .main{background:var(--accent);border-color:var(--accent);color:#fff;flex:1}
#out{width:100%;min-height:110px;margin-top:10px;font:12.5px/1.6 ui-monospace,Menlo,monospace;border:1px solid var(--line);border-radius:10px;padding:10px;background:var(--card);color:var(--ink)}
#msg{font-size:12px;color:var(--sub);margin-top:4px}
.pv{position:sticky;top:20px;align-self:start}
.frame{position:relative;margin:0 auto;background:#000;border-radius:10px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.15)}
.frame iframe{position:absolute;left:0;top:0;border:0;transform-origin:0 0}
.opts{display:flex;justify-content:center;gap:12px;margin-top:8px;font-size:13px;color:var(--sub)}
@media (max-width:820px){.wrap{grid-template-columns:1fr;padding:16px}.pv{position:static;order:-1}}
</style></head><body>
<div class="wrap">
 <section>
  <h1>__TITLE__</h1><p class="lead">スライダーで調整すると右のプレビューに即時に反映されます。終わったら「変更点をプロンプトにしてコピー」→ チャットに貼り付け。<br>反映先: <code>__TARGET__</code></p>
  <div class="ctl" id="ctl"></div>
  <div class="act"><button class="main" id="copy">変更点をプロンプトにしてコピー</button><button id="reset">すべて戻す</button></div>
  <textarea id="out" readonly placeholder="ここに変更点の一覧が出ます"></textarea><div id="msg"></div>
 </section>
 <section class="pv"><div class="frame" id="frame"><iframe id="pf" title="プレビュー"></iframe></div>
  <div class="opts" id="opts"></div></section>
</div>
<template id="src">__PREVIEW__</template>
<script>
const CFG = __CFG__;
const [VW, VH] = CFG.viewport;
const pf = document.getElementById('pf');
pf.srcdoc = document.getElementById('src').innerHTML;
const cur = Object.fromEntries(CFG.params.map(p => [p.key, p.value]));
const fmt = (p, v) => p.type === 'color' ? String(v).toUpperCase() : `${v}${p.unit || ''}`;
function apply() {
  const d = pf.contentDocument; if (!d || !d.documentElement) return;
  for (const p of CFG.params) if (p.css) d.documentElement.style.setProperty(p.css, p.type === 'color' ? cur[p.key] : cur[p.key] + (p.unit || ''));
}
pf.addEventListener('load', apply);
function fit() {
  const box = document.getElementById('frame'); const maxH = Math.min(window.innerHeight - 80, 900);
  const w = Math.min(box.parentElement.clientWidth, maxH * VW / VH); const s = w / VW;
  box.style.width = w + 'px'; box.style.height = VH * s + 'px';
  pf.style.width = VW + 'px'; pf.style.height = VH + 'px'; pf.style.transform = `scale(${s})`;
}
window.addEventListener('resize', fit); fit();
const ctl = document.getElementById('ctl');
for (const p of CFG.params) {
  const el = document.createElement('div'); el.className = 'p'; el.dataset.key = p.key;
  const input = p.type === 'color'
    ? `<input type="color" value="${p.value}">`
    : `<input type="range" min="${p.min}" max="${p.max}" step="${p.step || 1}" value="${p.value}"><input type="number" min="${p.min}" max="${p.max}" step="${p.step || 1}" value="${p.value}">`;
  el.innerHTML = `<div class="h"><label>${p.label}</label><span><span class="v"></span> <button title="元に戻す">戻す</button></span></div>
    <div class="r">${input}</div><code>${p.key}</code>${p.note ? `<div class="note">${p.note}</div>` : ''}`;
  ctl.appendChild(el);
  const ins = el.querySelectorAll('input');
  const set = v => { cur[p.key] = p.type === 'color' ? v : Number(v); ins.forEach(i => { if (i.value != v) i.value = v; });
    el.querySelector('.v').textContent = fmt(p, cur[p.key]); el.classList.toggle('chg', String(cur[p.key]).toLowerCase() !== String(p.value).toLowerCase()); apply(); };
  ins.forEach(i => i.addEventListener('input', () => set(i.value)));
  el.querySelector('button').onclick = () => set(p.value);
  set(p.value);
}
const toggles = CFG.toggles || [];
document.getElementById('opts').innerHTML = toggles.map(t => `<label><input type="checkbox" data-cls="${t.cls}" ${t.on ? 'checked' : ''}> ${t.label}</label>`).join('');
document.querySelectorAll('#opts input').forEach(i => i.onchange = () => pf.contentDocument.body.classList.toggle(i.dataset.cls, i.checked));
pf.addEventListener('load', () => document.querySelectorAll('#opts input').forEach(i => pf.contentDocument.body.classList.toggle(i.dataset.cls, i.checked)));
function prompt() {
  const ch = CFG.params.filter(p => String(cur[p.key]).toLowerCase() !== String(p.value).toLowerCase());
  if (!ch.length) return '';
  return `${CFG.title}：次の数値を変更してください（反映先: ${CFG.target}）。\n` +
    ch.map(p => `- ${p.label}（${p.key}）: ${fmt(p, p.value)} → ${fmt(p, cur[p.key])}`).join('\n') +
    `\n変更後、プレビューではなく実際の出力で確認してください。`;
}
document.getElementById('copy').onclick = async () => {
  const t = prompt(); const out = document.getElementById('out'); const msg = document.getElementById('msg');
  out.value = t || ''; if (!t) { msg.textContent = 'まだ何も変更していません'; return; }
  try { await navigator.clipboard.writeText(t); msg.textContent = 'コピーしました。チャットに貼り付けて送ってください。'; }
  catch (e) { out.select(); document.execCommand('copy'); msg.textContent = 'コピーしました（できていなければ上の欄から手動でコピー）'; }
};
document.getElementById('reset').onclick = () => document.querySelectorAll('.p button').forEach(b => b.click());
</script></body></html>"""


def build(d: Path, out: Path | None = None) -> Path:
    cfg = json.loads((d / "tune.json").read_text(encoding="utf-8"))
    preview = (d / "preview.html").read_text(encoding="utf-8")
    html = (PAGE.replace("__TITLE__", escape(cfg["title"])).replace("__TARGET__", escape(cfg.get("target", "")))
            .replace("__PREVIEW__", preview.replace("</template", "<\\/template"))
            .replace("__CFG__", json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")))
    out = out or d / "tune.html"
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0)
    print(build(Path(a[0]), Path(a[a.index("--out") + 1]) if "--out" in a else None))
