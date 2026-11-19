// アプリ内の更新のお知らせ（test_updater.py から呼ばれる）。2つ目の引数が none なら「お知らせが出ない」ことだけ確認する。
const { chromium } = require('playwright');
(async () => {
  const [url, mode] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 680 } })).newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(url); await page.waitForSelector('#pick'); await page.waitForTimeout(800);
  const bannerHidden = await page.$eval('#upd', e => e.hidden);
  const ver = await page.textContent('#ver');
  if (mode === 'none') { console.log(JSON.stringify({ errors, bannerHidden, ver })); await browser.close(); return; }
  const banner = await page.textContent('#upd-msg');
  await page.click('#upd-go');
  await page.waitForFunction(() => /更新しています|できませんでした/.test(document.getElementById('upd-msg').textContent), null, { timeout: 60000 });
  const after = await page.textContent('#upd-msg');
  console.log(JSON.stringify({ errors, bannerHidden, ver, banner, after }));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
