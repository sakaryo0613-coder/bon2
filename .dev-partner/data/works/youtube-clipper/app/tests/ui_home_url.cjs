// B-012: ホーム画面で Twitch の URL を貼って候補を作る（test_app.py から呼ばれる）。
// 使い方: node ui_home_url.cjs <URL> <スクショ保存先.png>
const { chromium } = require('playwright');

(async () => {
  const [url, shot] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 680 } })).newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  let clicks = 0;
  await page.goto(url);
  await page.waitForSelector('#url');
  // 取り込めない URL: 理由が出て、「候補を作る」は押せない
  await page.fill('#url', 'https://clips.twitch.tv/FunnyClip');
  await page.waitForSelector('#url-st.ng');
  const badMsg = await page.textContent('#url-st');
  const startDisabledOnBad = await page.$eval('#start', e => e.disabled);
  // 操作1: アーカイブの URL を貼る
  clicks++;
  await page.fill('#url', 'https://www.twitch.tv/videos/987');
  await page.waitForSelector('#url-st.ok');
  const okMsg = await page.textContent('#url-st');
  await page.waitForFunction(() => !document.getElementById('start').disabled);
  if (shot) await page.screenshot({ path: shot.replace(/\.png$/, '-ready.png') });
  // 操作2: 候補を作る
  clicks++;
  await page.click('#start');
  await page.waitForSelector('#job:not([hidden])');
  const stgKeys = await page.$$eval('.stg span', es => es.map(e => e.dataset.s));
  const startHiddenDuringJob = await page.$eval('#start', e => e.offsetParent === null);
  const jobInView = await page.$eval('#job', e => e.getBoundingClientRect().top < innerHeight - 60);
  const stagesSeen = new Set();
  const t0 = Date.now();
  let jobShot = false;
  while (!page.url().includes('/review') && Date.now() - t0 < 150000) {
    const now = await page.$$eval('.stg span.now', es => es.map(e => e.dataset.s)).catch(() => []);
    now.forEach(s => stagesSeen.add(s));
    if (!jobShot && shot && now.length) { await page.screenshot({ path: shot.replace(/\.png$/, '-job.png') }).catch(() => {}); jobShot = true; }
    await page.waitForTimeout(150);
  }
  const reachedReview = page.url().includes('/review');
  let chatReason = false;
  if (reachedReview) {
    await page.waitForSelector('.c');
    chatReason = (await page.content()).includes('チャット ×');
    if (shot) await page.screenshot({ path: shot });
  }
  console.log(JSON.stringify({ errors, clicks, stgKeys, startHiddenDuringJob, jobInView, badMsg, startDisabledOnBad, okMsg, stagesSeen: [...stagesSeen], reachedReview, chatReason }));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
