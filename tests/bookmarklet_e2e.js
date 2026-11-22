// Runs browser/bookmarklet.txt in headless Chromium on a fixture page and saves the EPUB.
// Usage: node tests/bookmarklet_e2e.js PAGE.html OUT.epub [ios]
// With "ios" it poses as iPhone Safari with a stub share sheet: the EPUB must come
// through the box's Save / share button, with its name.
// Prints the bookmarklet's summary as JSON. Pages are served from https://www.journal.test/
// (fixture files by name, /binary/* from tests/fixtures/web); everything else is refused,
// except the David Libre font download when E2E_FONTS=1 (needs network).
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const [page_, out, mode] = process.argv.slice(2);
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';
const root = path.join(__dirname, 'fixtures', 'web');
const code = decodeURIComponent(fs.readFileSync(path.join(__dirname, '..', 'browser', 'bookmarklet.txt'), 'utf8').trim().slice('javascript:'.length));

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  try {
    const ctx = await browser.newContext(mode === 'ios' ? { userAgent: IPHONE } : { acceptDownloads: true });
    await ctx.route('**/*', (route) => {
      const u = new URL(route.request().url());
      if (u.hostname === 'raw.githubusercontent.com' && process.env.E2E_FONTS === '1') return route.continue();
      if (u.hostname !== 'www.journal.test') return route.abort();
      const p = path.join(root, path.basename(u.pathname));
      if (!fs.existsSync(p)) return route.fulfill({ status: 404, body: 'no' });
      const type = p.endsWith('.png') ? 'image/png' : 'text/html; charset=utf-8';
      return route.fulfill({ status: 200, body: fs.readFileSync(p), headers: { 'content-type': type } });
    });
    const page = await ctx.newPage();
    await page.goto('https://www.journal.test/' + path.basename(page_));
    if (mode === 'ios') {
      await page.evaluate(() => {
        navigator.canShare = () => true;
        navigator.share = async (d) => {
          const f = d.files[0];
          window.__shared = { name: f.name, type: f.type, data: Array.from(new Uint8Array(await f.arrayBuffer())) };
        };
      });
      await page.evaluate(code);
      await page.click('#epubme-status button');
      await page.waitForFunction(() => window.__shared);
      const sh = await page.evaluate(() => window.__shared);
      fs.writeFileSync(out, Buffer.from(sh.data));
      const summary = await page.evaluate(() => window.__epubMeSummary);
      summary.shared = { name: sh.name, type: sh.type };
      console.log(JSON.stringify(summary));
      return;
    }
    const dl = page.waitForEvent('download', { timeout: 60000 });
    dl.catch(() => {});
    await page.evaluate(code);
    const err = await page.evaluate(() => window.__epubMeError);
    if (err) throw new Error('bookmarklet failed: ' + err);
    const d = await dl;
    await d.saveAs(out);
    const summary = await page.evaluate(() => window.__epubMeSummary || { error: window.__epubMeError });
    summary.suggested = d.suggestedFilename();
    console.log(JSON.stringify(summary));
  } finally {
    await browser.close();
  }
})().catch((e) => { console.error(e); process.exit(1); });
