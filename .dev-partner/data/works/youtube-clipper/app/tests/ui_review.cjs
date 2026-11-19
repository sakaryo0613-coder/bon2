// レビュー画面の操作テスト（test_review.py から呼ばれる）。
// 使い方: node ui_review.cjs <URL> <スクショ保存先.png>
const { chromium } = require('playwright');

(async () => {
  const [url, shot] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  let alerts = 0;
  page.on('dialog', d => { alerts++; d.accept(); });
  const state = () => page.evaluate(async () => (await (await fetch('/api/state')).json()).clips);
  const byId = async id => (await state()).find(c => c.id === id);
  const settle = () => page.waitForTimeout(250);

  await page.goto(url);
  await page.waitForSelector('.c');
  const first = await byId('c01');
  const sel = () => page.$eval('.c.sel', e => e.dataset.id);

  // 1) キーボードで c01, c02 を採用（採用すると次の未判断に移る）
  await page.keyboard.press('a'); await settle();
  const afterA = await sel();
  await page.keyboard.press('a'); await settle();

  // 2) c03 を「＋次の文」で伸ばしてボタンで採用
  await page.click('.c[data-id=c03]'); await settle();
  const before3 = await byId('c03');
  await page.click('#pb'); await settle();
  const after3 = await byId('c03');
  await page.click('#ok'); await settle();

  // 3) c04 のタイトルを編集（未判断のまま）
  await page.click('.c[data-id=c04]'); await settle();
  await page.fill('#tt', '朝5時起きを1か月続けた結果');
  await page.keyboard.press('Tab'); await settle();

  // 4) c05 を X で却下
  await page.click('.c[data-id=c05]'); await settle();
  await page.keyboard.press('x'); await settle();

  // 5) c03 を縮めすぎようとする（20秒未満は拒否される）
  await page.click('.c[data-id=c03]'); await settle();
  let minDur = 999;
  for (let i = 0; i < 12; i++) {
    const btn = await page.$('#ma');
    if (!btn || await btn.isDisabled()) break;
    await btn.click(); await settle();
    minDur = Math.min(minDur, (await byId('c03')).duration);
  }

  // 6) 書き出し
  await page.click('#go');
  await page.waitForFunction(() => /完了|エラー/.test(document.getElementById('ptext').textContent), null, { timeout: 300000 });
  const ptext = await page.textContent('#ptext');
  if (shot) await page.screenshot({ path: shot });
  const clips = await state();
  console.log(JSON.stringify({
    firstSelected: first.id, afterAccept: afterA,
    c03: { before: [before3.start_sid, before3.end_sid, before3.duration], after: [after3.start_sid, after3.end_sid, after3.duration] },
    minDurAfterShrink: minDur, alerts, ptext, errors,
    statuses: Object.fromEntries(clips.map(c => [c.id, c.status])),
    titles: Object.fromEntries(clips.map(c => [c.id, c.title])),
  }));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
