// ホーム画面の操作テスト（test_app.py から呼ばれる）。
// 使い方: node ui_home.cjs <URL> <スクショ保存先.png>
// 「動画を選ぶ」のファイル選択画面はテスト用に差し替えてある（サーバー側で決まったパスを返す）。
const { chromium } = require('playwright');

(async () => {
  const [url, shot] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 680 } })).newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  let clicks = 0;
  const click = async sel => { clicks++; await page.click(sel); };

  await page.goto(url);
  await page.waitForSelector('#pick');
  const startDisabledBefore = await page.$eval('#start', e => e.disabled);
  await click('#pick');                                   // 操作2: 動画を選ぶ（操作1はアプリの起動）
  await page.waitForFunction(() => !document.getElementById('start').disabled);
  const picked = await page.textContent('#pick-title');
  await page.fill('#credit', '出典: テストチャンネル');     // 任意の入力（操作数に数えない）
  await click('#start');                                  // 操作3: 候補を作る
  await page.waitForSelector('#job:not([hidden])');
  const stagesSeen = new Set();
  const t0 = Date.now();
  while (!page.url().includes('/review') && Date.now() - t0 < 120000) {
    const now = await page.$$eval('.stg span.now', es => es.map(e => e.dataset.s)).catch(() => []);
    now.forEach(s => stagesSeen.add(s));
    await page.waitForTimeout(200);
  }
  const reachedReview = page.url().includes('/review');
  if (reachedReview) await page.waitForSelector('.c');
  const nClips = reachedReview ? await page.$$eval('.c', es => es.length) : 0;
  const guideShown = reachedReview ? await page.$eval('#guide', e => !e.hidden) : false;
  if (shot) await page.screenshot({ path: shot });

  // ホームに戻ると「最近の作業」に出ている
  await page.goto(url); await page.waitForSelector('#recent .item');
  const recent = await page.$$eval('#recent .item', es => es.map(e => e.textContent.trim()));
  console.log(JSON.stringify({ errors, clicks, startDisabledBefore, picked, stagesSeen: [...stagesSeen], reachedReview, nClips, guideShown, recent }));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
