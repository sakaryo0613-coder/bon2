#!/usr/bin/env node
/*
 * shot.cjs — HTML/URL を複数の幅でスクショし、見た目の事故を自動チェックする。
 *
 * 使い方:
 *   node shot.cjs <file.html|URL> [--out DIR] [--widths 1280,390] [--height 800]
 *                 [--full] [--dpr 1] [--wait 600] [--must-see "#ok,#ng"] [--edge 48]
 *
 * 出力: DIR/<name>-<幅>.png（ファーストビュー。固定表示の要素も実際の位置で写る）と、標準出力にチェック結果。
 *       --full のときは全体を読めるサイズに分割した DIR/<name>-<幅>-p1.png, -p2.png … も保存する
 *       （固定表示の要素はページ途中に写り込むため、分割画像では隠す）。
 * チェック内容（NG があると終了コード 1）:
 *   - ページのJSエラー / console.error
 *   - 横スクロール（documentElement.scrollWidth > 画面幅）
 *   - 画面幅からはみ出している要素（上位5件）
 *   - 読み込みに失敗した画像
 *   - --must-see で指定した要素（主要な操作ボタンなど）がファーストビューに収まっていない
 * 参考情報（NG にはしない）: 11px未満の文字を含む要素数、失敗したリクエスト（外部フォント等）、
 *   --must-see の要素が画面の下端から --edge px（既定48＝ボタン1つ分）以内にある（入ってはいるが、何か1つ足すと画面外に出る）
 *
 * 人に見せるスクショは --dpr 2、自分の確認用は --dpr 1（既定）。
 */
const path = require('path');
const fs = require('fs');

function args(argv) {
  const o = { out: null, widths: [1280, 390], height: 800, full: false, dpr: 1, wait: 600, target: null, mustSee: [], edge: 48 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--out') o.out = argv[++i];
    else if (a === '--widths') o.widths = argv[++i].split(',').map(Number);
    else if (a === '--height') o.height = Number(argv[++i]);
    else if (a === '--full') o.full = true;
    else if (a === '--dpr') o.dpr = Number(argv[++i]);
    else if (a === '--wait') o.wait = Number(argv[++i]);
    else if (a === '--must-see') o.mustSee = argv[++i].split(',').map(s => s.trim()).filter(Boolean);
    else if (a === '--edge') o.edge = Number(argv[++i]);
    else if (!o.target) o.target = a;
  }
  return o;
}

(async () => {
  const o = args(process.argv.slice(2));
  if (!o.target) {
    console.log(fs.readFileSync(__filename, 'utf8').split('\n').slice(1, 20).join('\n'));
    process.exit(2);
  }
  let chromium;
  try { ({ chromium } = require('playwright')); }
  catch (e) {
    console.error('playwright が見つかりません。ローカルでは `npm i -g playwright && npx playwright install chromium` を実行してください。');
    process.exit(3);
  }
  const isUrl = /^https?:\/\//.test(o.target);
  const url = isUrl ? o.target : 'file://' + path.resolve(o.target);
  const base = isUrl ? new URL(o.target).hostname : path.basename(o.target).replace(/\.[^.]+$/, '');
  const out = o.out || (isUrl ? '.' : path.join(path.dirname(path.resolve(o.target)), 'shots'));
  fs.mkdirSync(out, { recursive: true });

  const browser = await chromium.launch();
  let ng = 0;
  for (const w of o.widths) {
    const ctx = await browser.newContext({ viewport: { width: w, height: o.height }, deviceScaleFactor: o.dpr });
    const page = await ctx.newPage();
    const errors = [], failed = [];
    page.on('pageerror', e => errors.push('pageerror: ' + e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
    page.on('requestfailed', r => failed.push(r.url().slice(0, 90)));
    await page.goto(url, { waitUntil: 'load', timeout: 30000 }).catch(e => errors.push('goto: ' + e.message));
    await page.waitForTimeout(o.wait);

    const r = await page.evaluate(([mustSee, edge]) => {
      const vw = window.innerWidth;
      const de = document.documentElement;
      const desc = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
        (el.classList.length ? '.' + [...el.classList].slice(0, 2).join('.') : '');
      const over = [];
      for (const el of document.body.querySelectorAll('*')) {
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden' || cs.position === 'fixed') continue;
        const b = el.getBoundingClientRect();
        if (b.width > 0 && b.right > vw + 1) {
          // はみ出している祖先がすでに記録済みなら子は省く
          if (!over.some(o => o.el.contains(el))) over.push({ el, right: Math.round(b.right) });
        }
      }
      let small = 0;
      for (const el of document.body.querySelectorAll('*')) {
        if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
        const cs = getComputedStyle(el);
        if (cs.display !== 'none' && parseFloat(cs.fontSize) < 11) small++;
      }
      const broken = [...document.images].filter(i => i.complete && i.naturalWidth === 0).map(i => i.src.slice(0, 80));
      const hidden = mustSee.filter(sel => {
        const el = document.querySelector(sel);
        if (!el) return true;
        const b = el.getBoundingClientRect();
        return !(b.width > 0 && b.top >= 0 && b.left >= 0 && b.bottom <= window.innerHeight && b.right <= vw);
      });
      // 入ってはいるが端に近い（B-013: 帯を足したら grid の行が伸び、「候補を作る」が下端まで押し出されたのに OK だった）
      const nearEdge = mustSee.filter(sel => !hidden.includes(sel)).map(sel => {
        const b = document.querySelector(sel).getBoundingClientRect();
        const room = Math.round(window.innerHeight - b.bottom);   // 横幅いっぱいの要素があるので、下端だけを見る
        return room < edge ? `${sel}（残り${room}px）` : null;
      }).filter(Boolean);
      return {
        scrollWidth: de.scrollWidth, vw, hidden, nearEdge,
        overflow: over.slice(0, 5).map(o => `${desc(o.el)} (right=${o.right}px)`),
        small, broken,
      };
    }, [o.mustSee, o.edge]);

    // ファーストビュー（固定表示の要素も実際の位置で写る）
    const file = path.join(out, `${base}-${w}.png`);
    await page.screenshot({ path: file });
    const tiles = [];
    if (o.full) {
      // 全体: 固定表示の要素はページ途中に写り込むので隠す（ファーストビュー画像で確認する）。
      // 縦に長いと縮小されて読めないため、読めるサイズに分割して保存する。
      const nFixed = await page.evaluate(() => {
        let n = 0;
        for (const el of document.querySelectorAll('body *')) {
          const p = getComputedStyle(el).position;
          if (p === 'fixed' || p === 'sticky') { el.style.setProperty('visibility', 'hidden', 'important'); n++; }
        }
        return n;
      });
      const total = await page.evaluate(() => document.documentElement.scrollHeight);
      const th = Math.min(2000, Math.max(800, Math.round(w * 1.6)));
      for (let k = 0, y = 0; y < total; k++, y += th) {
        const t = path.join(out, `${base}-${w}-p${k + 1}.png`);
        await page.screenshot({ path: t, fullPage: true, clip: { x: 0, y, width: w, height: Math.min(th, total - y) } });
        tiles.push(t);
      }
      if (nFixed) tiles.push(`（固定表示の要素 ${nFixed} 個は分割画像では非表示。ファーストビュー画像で確認）`);
    }
    const hScroll = r.scrollWidth > r.vw;
    const bad = errors.length || hScroll || r.broken.length || r.hidden.length;
    if (bad) ng++;
    console.log(`\n[${w}px] ${bad ? 'NG' : 'OK'}  → ${file}`);
    if (tiles.length) console.log('  全体（分割）: ' + tiles.join('\n               '));
    if (hScroll) console.log(`  ✗ 横スクロール: scrollWidth=${r.scrollWidth} > ${r.vw}`);
    if (r.overflow.length) console.log(`  ${hScroll ? '✗' : '・'} はみ出し要素: ${r.overflow.join(', ')}`);
    if (errors.length) console.log('  ✗ エラー:\n    ' + errors.slice(0, 8).join('\n    '));
    if (r.broken.length) console.log('  ✗ 画像の読み込み失敗: ' + r.broken.join(', '));
    if (r.hidden.length) console.log('  ✗ ファーストビューに入っていない要素: ' + r.hidden.join(', '));
    if (r.nearEdge.length) console.log(`  ・画面の下端から${o.edge}px以内の要素: ${r.nearEdge.join(', ')}（押し出されかけていないか、スクショで確認）`);
    if (r.small) console.log(`  ・11px未満の文字を含む要素: ${r.small} 個（意図したものか確認）`);
    if (failed.length) console.log(`  ・失敗したリクエスト ${failed.length} 件（外部フォント等。表示に影響がないか確認）`);
    await ctx.close();
  }
  await browser.close();
  console.log(ng ? `\n結果: NG（${ng} 幅）` : '\n結果: OK');
  process.exit(ng ? 1 : 0);
})();
