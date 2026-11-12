/** Optional real-Chrome smoke of generated owner-only page embed (no network/credentials). */
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {fileURLToPath, pathToFileURL} from 'node:url';

const path = process.env.JUNCTION_OWNER_PAGE_EMBED_PATH ||
  fileURLToPath(new URL('../../dist/mission-control/page-embed.html', import.meta.url));
assert.ok(existsSync(path), 'Run npm run ops:page:build first; owner Page embed not found');
const html = readFileSync(path, 'utf8');
const csp = html.match(/<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]+)"/i)?.[1];
assert.ok(csp, 'Owner Page embed missing CSP');
assert.match(csp, /script-src 'sha256-[^']+'/);
assert.match(csp, /style-src 'sha256-[^']+'/);
assert.doesNotMatch(csp, /unsafe-inline|unsafe-eval/);
assert.match(csp, /connect-src 'none'/);

const {chromium} = await import('playwright');
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROMIUM_EXECUTABLE_PATH ||
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  args: ['--no-sandbox'],
});
try {
  for (const viewport of [{width: 1440, height: 900}, {width: 390, height: 844}]) {
    const page = await browser.newPage({viewport});
    const errors = [];
    page.on('pageerror', error => errors.push('page: ' + error.message));
    page.on('console', message => {
      if (message.type() === 'error') errors.push('console: ' + message.text());
    });
    await page.goto(pathToFileURL(path).href, {waitUntil: 'load'});
    await page.locator('.pet-row').first().waitFor({timeout: 10_000});
    assert.equal(await page.locator('.pet-row').count(), 34, '34 bootstrapped records');
    assert.equal(await page.locator('#metric-cloud').textContent(), '00', 'no green from stored snapshot');
    assert.match(await page.locator('#snapshot-title').textContent(), /snapshot|Status/i);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    assert.ok(overflow <= 1, 'no mobile/desktop horizontal overflow: ' + overflow);
    assert.deepEqual(errors, [], 'CSP/JS console error in generated embed');
    await page.close();
  }
  console.log('OWNER_PAGE_EMBED_CHROME_SMOKE_OK: 34 records; hashed CSP; desktop/mobile; zero console violations; offline file preview only.');
} finally {
  await browser.close();
}
