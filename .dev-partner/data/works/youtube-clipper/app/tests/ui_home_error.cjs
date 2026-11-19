// 候補づくりが失敗したときの表示（test_app.py から呼ばれる）。
const { chromium } = require('playwright');
(async () => {
  const [url] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 680 } })).newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(url); await page.waitForSelector('#pick');
  await page.click('#pick'); await page.waitForFunction(() => !document.getElementById('start').disabled);
  await page.click('#start');
  await page.waitForSelector('#err:not([hidden])', { timeout: 60000 });
  const res = await page.evaluate(() => ({
    err: document.getElementById('err').textContent,
    animating: document.getElementById('bar').classList.contains('ind'),
    failedStage: [...document.querySelectorAll('.stg span.ng')].map(e => e.textContent),
    retry: !document.getElementById('start').hidden && !document.getElementById('start').disabled ? document.getElementById('start').textContent : '',
    title: document.getElementById('job-title').textContent,
  }));
  console.log(JSON.stringify({ errors, ...res }));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
