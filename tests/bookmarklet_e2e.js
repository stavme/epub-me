// Runs browser/bookmarklet.txt in headless Chromium on a fixture page and saves the EPUB.
// Usage: node tests/bookmarklet_e2e.js PAGE.html OUT.epub
// Prints the bookmarklet's summary as JSON. Pages are served from https://www.journal.test/
// (fixture files by name, /binary/* from tests/fixtures/web); everything else is refused,
// except the David Libre font download when E2E_FONTS=1 (needs network).
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const [page_, out] = process.argv.slice(2);
const root = path.join(__dirname, 'fixtures', 'web');
const code = decodeURIComponent(fs.readFileSync(path.join(__dirname, '..', 'browser', 'bookmarklet.txt'), 'utf8').trim().slice('javascript:'.length));

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  try {
    const ctx = await browser.newContext({ acceptDownloads: true });
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
