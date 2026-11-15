// Fallback recording of the 2-minute demo click path (submission/DEMO_SCRIPT.md), from a running SAMA server
// started with the live model switched off:  SAMA_SCRIBE_LIVE=0 PORT=4191 node web/serve.mjs
// Then:  PUPPETEER_CORE=/path/to/node_modules/puppeteer-core node submission/fallback/record.mjs
// Headless Chrome, one instance, viewport 1440x810. Still frames are captured once and held; scrolls are captured
// frame by frame at FPS. Frames go to FRAMES_DIR with a concat list; submission/fallback/encode.sh makes the MP4.
// Everything patient-like on the page is SYNTHETIC and labelled there; this script only scrolls and screenshots.
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const PC = process.env.PUPPETEER_CORE;
if (!PC) throw new Error('set PUPPETEER_CORE to a puppeteer-core directory');
const puppeteer = (await import(resolve(PC, 'lib/esm/puppeteer/puppeteer-core.js'))).default;

const URL = process.env.SAMA_URL || 'http://127.0.0.1:4191/';
const OUT = process.env.FRAMES_DIR;
if (!OUT) throw new Error('set FRAMES_DIR');
mkdirSync(OUT, { recursive: true });
const W = 1440, H = 810, FPS = 15; // 15 divides the 30 fps output exactly

// The click path: [start second, label, section id, extra offset px, pan px over the hold]
const steps = [
  [0, '0:00 The gap', null, 0, 260],
  [15, '0:15 Who, how and where', 'who', 0, 1100],
  [35, '0:35 What to do', 'action', 0, 420],
  [50, '0:50 Comparability gate', 'comparability-gate', 0, 420],
  [70, '1:10 Close the loop', 'safety-net', 0, 900],
  [90, '1:30 Gemma demo, Note 4 (stored output)', 'scribe', 0, 1300],
  [105, '1:45 Nemotron county plan and the ask', 'plan', 0, 1000],
];
const END = 120;

const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: 'new', args: ['--no-first-run', '--hide-scrollbars', '--force-color-profile=srgb', `--window-size=${W},${H}`],
  defaultViewport: { width: W, height: H, deviceScaleFactor: 1 },
});
const list = [];
let n = 0;
try {
  const page = await browser.newPage();
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }, { name: 'prefers-reduced-motion', value: 'reduce' }]);
  await page.goto(URL, { waitUntil: 'networkidle0', timeout: 60000 });
  await page.waitForFunction(() => !document.querySelector('#loading') || document.querySelector('#loading').hidden || getComputedStyle(document.querySelector('#loading')).display === 'none' || !document.querySelector('#loading').textContent.trim(), { timeout: 30000 }).catch(() => {});
  await page.waitForFunction(() => /one-click confirmation/i.test(document.querySelector('#demo-content')?.textContent || ''), { timeout: 30000 });
  await page.waitForFunction(() => /255 of 299/.test(document.querySelector('#plan')?.textContent || ''), { timeout: 30000 }).catch(() => {});
  await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; });
  // Small step badge, fixed bottom-left, so the presenter knows where the recording is.
  await page.evaluate(() => {
    const b = document.createElement('div');
    b.id = 'fallback-badge';
    b.style.cssText = 'position:fixed;left:16px;bottom:14px;z-index:99999;font:600 13px/1.3 system-ui,sans-serif;color:#fafaf6;background:rgba(23,44,43,.88);padding:6px 10px;border-radius:4px;pointer-events:none;max-width:70vw';
    document.body.appendChild(b);
  });
  const stickyTop = await page.evaluate(() => {
    let h = 0;
    for (const el of document.querySelectorAll('body *')) {
      const cs = getComputedStyle(el);
      if ((cs.position === 'sticky' || cs.position === 'fixed') && el.id !== 'fallback-badge') {
        const r = el.getBoundingClientRect();
        if (r.top <= 1 && r.height < 200 && r.width > 600) h = Math.max(h, r.bottom);
      }
    }
    return Math.round(h);
  });
  const maxY = await page.evaluate(() => document.documentElement.scrollHeight - innerHeight);
  const yOf = (id, off) => page.evaluate((id, off, top) => Math.round(document.getElementById(id).getBoundingClientRect().top + scrollY - top - 12 + off), id, off, stickyTop);
  const shot = async (dur) => {
    const f = `f${String(n++).padStart(5, '0')}.jpg`;
    await page.screenshot({ path: resolve(OUT, f), type: 'jpeg', quality: 88 });
    list.push([f, dur]);
  };
  const scrollTo = (y) => page.evaluate((y) => window.scrollTo(0, y), y);
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  let y = 0;
  const glide = async (from, to, seconds, fn = ease) => {
    const frames = Math.max(1, Math.round(seconds * FPS));
    for (let i = 1; i <= frames; i++) { await scrollTo(Math.round(from + (to - from) * fn(i / frames))); await shot(1 / FPS); }
  };
  for (let i = 0; i < steps.length; i++) {
    const [t0, label, id, off, pan] = steps[i];
    const t1 = i + 1 < steps.length ? steps[i + 1][0] : END;
    await page.evaluate((l) => { document.getElementById('fallback-badge').textContent = `Fallback recording · ${l} · stored outputs, SYNTHETIC patient-like data`; }, label);
    let used = 0;
    if (id) {
      const target = Math.min(maxY, Math.max(0, await yOf(id, off)));
      await glide(y, target, 1.0); used += 1.0; y = target;
    } else { await scrollTo(0); y = 0; }
    // hold 3 s, slow pan, hold the rest
    const hold1 = 3, panS = Math.max(0, (t1 - t0) - used - hold1 - 2.5);
    await shot(hold1); used += hold1;
    const panTo = Math.min(maxY, y + pan);
    if (panTo > y && panS > 0) { await glide(y, panTo, panS, (t) => t); y = panTo; used += panS; }
    await shot(Math.max(0.1, (t1 - t0) - used));
  }
} finally {
  await browser.close();
}
// ffmpeg concat list (the last file repeated so its duration is honoured)
let txt = list.map(([f, d]) => `file '${f}'\nduration ${d.toFixed(4)}`).join('\n') + `\nfile '${list.at(-1)[0]}'\n`;
writeFileSync(resolve(OUT, 'list.txt'), txt);
console.log(JSON.stringify({ frames: list.length, seconds: +list.reduce((a, [, d]) => a + d, 0).toFixed(2), stickyTop: 'measured' }));
