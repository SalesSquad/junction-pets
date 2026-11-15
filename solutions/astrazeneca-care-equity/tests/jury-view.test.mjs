// Jury view (?jury): switched on only by the query parameter; hides report sections, never the SYNTHETIC labels.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('../web/index.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../web/styles.css', import.meta.url), 'utf8');
const app = readFileSync(new URL('../web/app.mjs', import.meta.url), 'utf8');

test('jury view is opt-in and keeps the demo path', () => {
  assert.match(app, /URLSearchParams\(location\.search\)\.has\('jury'\)\)document\.documentElement\.classList\.add\('jury'\)/);
  assert.match(css, /\.jury-only\{display:none\}/, 'the jury note is not rendered on the default page');
  assert.match(html, /id="jury-note" class="jury-only"/);
  const hidden = css.match(/\.jury #county[^{]*\{display:none\}/)[0];
  for (const kept of ['#decision', '#gap', '#who', '#action', '#safety-net', '#comparability-gate', '#plan', '#scribe', '.scribe-try'])
    assert.ok(!hidden.includes(`.jury ${kept},`) && !hidden.includes(`.jury ${kept}{`), `${kept} must stay visible`);
  assert.match(css, /\.jury \.chip:not\(\.synthetic\)/, 'SYNTHETIC labels are never dimmed');
});
