import assert from 'node:assert/strict';
import {readFile, mkdir, writeFile, mkdtemp} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {chromium} from 'playwright';
import {startServer} from './server.mjs';
const out = process.env.ARDUINO_BROWSER_OUTPUT || await mkdtemp(join(tmpdir(), 'junction-arduino-browser-'));
await mkdir(out, {recursive:true});
const checks = [], errors = [], external = [];
const server = await startServer({port:0});
const base = `http://127.0.0.1:${server.address().port}`;
const executablePath = process.env.ARDUINO_CHROMIUM_PATH || (existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined);
const browser = await chromium.launch({executablePath, headless:true, args:['--no-sandbox']}).catch(async error => {
  await new Promise(resolve => server.close(resolve)); throw error;
});
const page = await browser.newPage({viewport:{width:1440,height:1000},acceptDownloads:true});
page.on('pageerror', e => errors.push(e.message));
page.on('request', r => {
  try {if (new URL(r.url()).origin !== base) external.push(r.url());}
  catch {external.push(r.url());}
});
const ready = () => page.waitForFunction(() => !document.querySelector('#download-json').disabled);
try {
  await page.goto(base); await ready();
  assert.match(await page.locator('#summary-total').innerText(), /17/);
  await page.locator('[data-pin="P0"]').focus(); await page.keyboard.press('Enter');
  assert.match(await page.locator('#pin-details').innerText(), /sensor-a/);
  checks.push('pin map selects declared sensor and budget');
  await page.locator('#sensor-range-0').focus(); await page.keyboard.press('ArrowRight'); await ready();
  await page.waitForFunction(() => document.querySelector('#summary-total').textContent.includes('18'));
  await page.locator('#sensor-current-0').fill('8'); await ready();
  checks.push('native slider supports keyboard adjustment');
  await page.locator('#save-baseline').click();
  let releaseOld, sawOld, finishOld;
  const hold = new Promise(resolve => {releaseOld = resolve;});
  const oldStarted = new Promise(resolve => {sawOld = resolve;});
  const oldFinished = new Promise(resolve => {finishOld = resolve;});
  await page.route('**/api/compare', async route => {
    const input = route.request().postDataJSON();
    const response = await route.fetch();
    const old = input.baseline.sensors[0].currentMa === 8 && input.candidate.sensors[0].currentMa === 100;
    if (old) {
      sawOld(); await hold;
    }
    await route.fulfill({response}).catch(() => {}); // Cancellation is an expected stale-response defense.
    if (old) finishOld();
  });
  await page.locator('#sensor-current-0').fill('100'); await ready();
  await oldStarted;
  await page.locator('#save-baseline').click();
  await page.waitForFunction(() => document.querySelector('#compare-result').textContent.includes('Ei uusia huomioita.'));
  releaseOld();
  await oldFinished;
  await page.waitForTimeout(100); // Allow a delivered stale response to reach browser promise handlers.
  await page.unroute('**/api/compare');
  assert.equal((await page.locator('#compare-result').innerText()).includes('power-oversubscribed'),false);
  checks.push('replacing baseline rejects a deliberately delayed older comparison');
  await page.locator('#sensor-current-0').fill('101'); await ready();
  await page.waitForFunction(() => document.querySelector('#compare-result .compare-metric strong')?.textContent.includes('-1') || document.querySelector('#compare-result .compare-metric strong')?.textContent.includes('−1'));
  assert.match(await page.locator('#summary-headroom').innerText(), /−|-|−/);
  checks.push('interactive overcurrent and baseline comparison');
  await page.locator('#unknown-powerLimitMa').check(); await ready();
  assert.match(await page.locator('#summary-headroom').innerText(), /Tuntematon/);
  checks.push('unknown limits remain unknown');
  await page.locator('#reset-example').click(); await ready();
  await page.locator('#evidence-url').fill('https://user:password@example.invalid/spec');
  await page.locator('#add-evidence').click();
  await page.locator('#evidence-error').waitFor({state:'visible'});
  assert.match(await page.locator('#evidence-count').innerText(), /0 merkintää/);
  checks.push('credential-bearing evidence URLs are rejected before insertion');
  await page.locator('#evidence-path').selectOption('board.powerLimitMa');
  await page.locator('#evidence-status').selectOption('reviewed');
  await page.locator('#evidence-url').fill('https://example.invalid/synthetic-spec');
  await page.locator('#evidence-revision').fill('fictional-revision-1');
  await page.locator('#evidence-excerpt').fill('Invented declared current limit 30 mA');
  await page.locator('#evidence-note').fill('<img src=x onerror="window.__xss=1">');
  await page.locator('#add-evidence').click(); await ready();
  assert.match(await page.locator('#evidence-list').innerText(), /ei varmennettu|USER-ASSERTED/);
  assert.equal(await page.evaluate(() => window.__xss), undefined);
  checks.push('user-asserted evidence renders inertly without fetching source');
  const jsonEvent = page.waitForEvent('download'); await page.locator('#download-json').click();
  const jd = await jsonEvent; await jd.saveAs(`${out}/report.json`);
  const report = JSON.parse(await readFile(`${out}/report.json`,'utf8'));
  assert.equal(report.checkerVersion,JSON.parse(await readFile(new URL('../pet.json',import.meta.url),'utf8')).version); assert.equal(report.authorization,false);
  assert.equal(report.safetyCertification,false); assert.equal(report.evidence.length,1);
  assert.equal(report.review.budgets.total.headroomMa,13);
  const mdEvent = page.waitForEvent('download'); await page.locator('#download-markdown').click();
  const md = await mdEvent; await md.saveAs(`${out}/report.md`);
  assert.match(await readFile(`${out}/report.md`,'utf8'), /USER-ASSERTED/);
  checks.push('JSON and readable report downloads match current review');
  await page.locator('#json-details').evaluate(el => el.open=true);
  await page.locator('#design-json').fill('{');
  assert.equal(await page.locator('#download-json').isDisabled(),true);
  await page.locator('#apply-json').click();
  assert.match(await page.locator('#error-banner').innerText(), /JSON/);
  checks.push('unapplied or invalid JSON blocks stale exports');
  for (const text of ['null', '0', 'false', '{}']) {
    await page.locator('#design-json').fill(text); await page.locator('#apply-json').click();
    await page.waitForFunction(() => !document.querySelector('#error-banner').hidden);
    assert.equal(await page.locator('#download-json').isDisabled(),true);
  }
  checks.push('malformed structural JSON remains rejected without stale exports');
  await page.locator('#reset-example').click(); await ready();
  await page.locator('#json-details').evaluate(el => el.open=true);
  const imported=JSON.parse(await readFile(new URL('../example-v2.json',import.meta.url),'utf8'));
  imported.sensors[0].currentMa=9;
  await page.locator('#import-json').setInputFiles({name:'fictional.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(imported))});
  await ready(); await page.waitForFunction(() => document.querySelector('#summary-total').textContent.includes('18'));
  checks.push('JSON file import updates actual reviewed design');
  await page.locator('#reset-example').click(); await ready();
  await page.screenshot({path:`${out}/desktop.png`,fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1),true);
  await page.screenshot({path:`${out}/mobile.png`,fullPage:true});
  checks.push('390px responsive layout has no horizontal overflow');
  assert.deepEqual(errors,[]); assert.deepEqual(external,[]);
  for(const [path,init,status] of [
    ['/api/review',{method:'POST',headers:{'Content-Type':'application/json',Origin:'https://example.invalid'},body:'{}'},403],
    ['/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:'x'.repeat(262145)},413],
    ['/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:'{'},400],
    ['/missing',{},404],
  ]) assert.equal((await fetch(base+path,init)).status,status);
  const headers=await fetch(base); assert.match(headers.headers.get('content-security-policy'),/default-src 'self'/);
  checks.push('server rejects cross-origin, oversized, malformed and unknown requests');
  console.log(JSON.stringify({result:'pass',checks,errors,external,base,artifacts:out},null,2));
  await writeFile(`${out}/result.json`,JSON.stringify({result:'pass',checks,errors,external},null,2));
} catch(error) {
  await page.screenshot({path:`${out}/failure.png`,fullPage:true}).catch(()=>{});
  console.error(error); console.error({checks,errors,external}); process.exitCode=1;
} finally {await browser.close(); await new Promise(resolve => server.close(resolve));}
