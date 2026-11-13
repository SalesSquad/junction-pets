import assert from 'node:assert/strict';
import {chromium, webkit} from 'playwright';
import {localPreviewBase, previewSelectionUrl} from './preview-url.mjs';

const baseUrl = process.env.JUNCTION_PREVIEW_URL ?? 'http://127.0.0.1:4173';
const parsed = localPreviewBase(baseUrl);

async function run(name, engine, viewport) {
  const browser = await engine.launch({headless: true});
  try {
    const page = await browser.newPage({viewport});
    const open = query => page.goto(previewSelectionUrl(parsed, query).href, {waitUntil: 'networkidle'});
    const assertMount = () => assert.equal(new URL(page.url()).pathname, parsed.pathname, `${name}: mount path changed`);
    const detailName = page.locator('.pet-detail .pet-name');
    const waitForPet = async pattern => {
      await detailName.filter({hasText: pattern}).waitFor();
      assert.match(await detailName.textContent(), pattern);
    };
    const assertNoOverflow = async state => {
      const overflow = await page.evaluate(
        () => Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) - window.innerWidth,
      );
      assert.ok(overflow <= 1, `${name} ${viewport.width}x${viewport.height} ${state}: horizontal overflow ${overflow}px`);
      return overflow;
    };
    await open('pet=junction-aiven');
    assertMount();
    await waitForPet(/Aiven/i);
    const aivenOverflow = await assertNoOverflow('Aiven detail');

    await page.getByRole('button', {name: /Preview QR code/}).click();
    await page.locator('dialog[open]').waitFor();
    const qrDestination = new URL(await page.locator('dialog input[type=url]').inputValue());
    assert.equal(qrDestination.origin, 'https://chibi-pet.ervamaamikael.chatgpt.site');
    assert.equal(qrDestination.pathname, '/en/chibi/junction-aiven');
    assert.equal(qrDestination.search, '');
    assert.equal(qrDestination.hash, '');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('dialog[open]').count(), 0);

    await page.getByPlaceholder('Search companies').fill('mariadb');
    await page.getByRole('heading', {name: 'Hidden by your filters'}).waitFor();
    assert.equal(await page.locator('article.pet-detail').count(), 0);
    await page.getByRole('button', {name: 'Clear filters'}).click();
    await waitForPet(/Aiven/i);

    if (viewport.width < 600) {
      await page.locator('.mobile-company-select select').selectOption('junction-arduino');
    } else {
      await page.locator('.company-list button').filter({hasText: 'Arduino'}).click();
    }
    assert.equal(new URL(page.url()).searchParams.get('pet'), 'junction-arduino');
    assertMount();
    await waitForPet(/Arduino/i);
    const arduinoOverflow = await assertNoOverflow('Arduino detail');

    await page.goBack({waitUntil: 'domcontentloaded'});
    assertMount();
    assert.equal(new URL(page.url()).searchParams.get('pet'), 'junction-aiven');
    await waitForPet(/Aiven/i);
    await page.goForward({waitUntil: 'domcontentloaded'});
    assertMount();
    await waitForPet(/Arduino/i);

    await open('pet=junction-does-not-exist');
    assertMount();
    await page.getByRole('heading', {name: 'Companion link not found'}).waitFor();
    assert.equal(await page.locator('article.pet-detail').count(), 0);
    await open('pet=junction-aiven&pet=junction-mariadb');
    assertMount();
    await page.getByRole('heading', {name: 'Companion link not found'}).waitFor();
    assert.equal(await page.locator('article.pet-detail').count(), 0);

    const overflow = await assertNoOverflow('invalid selector');
    console.log(JSON.stringify({
      browser: name,
      viewport: `${viewport.width}x${viewport.height}`,
      mountPath: parsed.pathname,
      deepLink: 'pass',
      history: 'pass',
      qr: 'pass',
      invalid: 'pass',
      overflow,
      richDetailOverflow: {aiven: aivenOverflow, arduino: arduinoOverflow},
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
