import assert from 'node:assert/strict';
import {chromium, webkit} from 'playwright';

const baseUrl = process.env.JUNCTION_PREVIEW_URL ?? 'http://127.0.0.1:4173';
const parsed = new URL(baseUrl);
if (!['localhost', '127.0.0.1'].includes(parsed.hostname) || parsed.protocol !== 'http:') {
  throw new Error('Browser smoke must target a local, non-production preview.');
}

async function run(name, engine, viewport) {
  const browser = await engine.launch({headless: true});
  try {
    const page = await browser.newPage({viewport});
    const open = path => page.goto(new URL(path, parsed).href, {waitUntil: 'networkidle'});
    await open('/?pet=junction-aiven');
    await page.locator('.pet-detail .pet-name').waitFor();
    assert.match(await page.locator('.pet-detail .pet-name').textContent(), /Aiven/i);

    await page.getByRole('button', {name: /Preview QR code/}).click();
    await page.locator('dialog[open]').waitFor();
    assert.equal(
      new URL(await page.locator('dialog input[type=url]').inputValue()).pathname,
      '/en/chibi/junction-aiven',
    );
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('dialog[open]').count(), 0);

    await page.getByPlaceholder('Search companies').fill('mariadb');
    await page.getByRole('heading', {name: 'Hidden by your filters'}).waitFor();
    assert.equal(await page.locator('article.pet-detail').count(), 0);
    await page.getByRole('button', {name: 'Clear filters'}).click();
    assert.match(await page.locator('.pet-detail .pet-name').textContent(), /Aiven/i);

    if (viewport.width < 600) {
      await page.locator('.mobile-company-select select').selectOption('junction-arduino');
    } else {
      await page.locator('.company-list button').filter({hasText: 'Arduino'}).click();
    }
    assert.equal(new URL(page.url()).searchParams.get('pet'), 'junction-arduino');
    assert.match(await page.locator('.pet-detail .pet-name').textContent(), /Arduino/i);

    await page.goBack({waitUntil: 'domcontentloaded'});
    await page.locator('.pet-detail .pet-name').waitFor();
    assert.equal(new URL(page.url()).searchParams.get('pet'), 'junction-aiven');
    assert.match(await page.locator('.pet-detail .pet-name').textContent(), /Aiven/i);
    await page.goForward({waitUntil: 'domcontentloaded'});
    assert.match(await page.locator('.pet-detail .pet-name').textContent(), /Arduino/i);

    await open('/?pet=junction-does-not-exist');
    await page.getByRole('heading', {name: 'Companion link not found'}).waitFor();
    assert.equal(await page.locator('article.pet-detail').count(), 0);
    await open('/?pet=junction-aiven&pet=junction-mariadb');
    await page.getByRole('heading', {name: 'Companion link not found'}).waitFor();
    assert.equal(await page.locator('article.pet-detail').count(), 0);

    const overflow = await page.evaluate(() => document.body.scrollWidth - window.innerWidth);
    assert.ok(overflow <= 1, `${name}: horizontal overflow ${overflow}px`);
    console.log(JSON.stringify({
      browser: name,
      viewport: `${viewport.width}x${viewport.height}`,
      deepLink: 'pass',
      history: 'pass',
      qr: 'pass',
      invalid: 'pass',
      overflow,
    }));
  } finally {
    await browser.close();
  }
}

for (const [name, engine] of [['Chromium', chromium], ['WebKit', webkit]]) {
  for (const viewport of [{width: 1440, height: 900}, {width: 390, height: 844}]) {
    await run(name, engine, viewport);
  }
}
