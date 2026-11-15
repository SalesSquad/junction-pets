// The two product panels mounted in section 05 during the ship wave: the county safety-net worklist
// (DO #2, data/safetynet/safetynet-v1.json, rendered by web/safetynet.mjs) and the FLARE comparability
// gate (DO #3, data/flare/gate-v1.json, rendered by web/flare.mjs). Both are SYNTHETIC; the gate's
// stage chip is PUBLISHED public data. These tests bind the bundle in app.json to its file, check the
// missing-file and required-field rules of src/tracks.mjs, and check what the page renders from it.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { buildApp } from '../src/build.mjs';
import { buildFlareGate, buildSafetyNet, buildTracks, FILES, SYNTHETIC } from '../src/tracks.mjs';
import { safetyNetHtml } from '../web/safetynet.mjs';
import { flareGateHtml } from '../web/flare.mjs';
import { dataPlanHtml, pilotHtml, processHtml, scribeHtml, whoHtml } from '../web/tracks.mjs';

const url = (p) => new URL(`../${p}`, import.meta.url);
const has = (p) => existsSync(url(p));
const read = (p) => JSON.parse(readFileSync(url(p), 'utf8'));
const text = (p) => readFileSync(url(p), 'utf8');
const sha256 = (p) => createHash('sha256').update(readFileSync(url(p))).digest('hex');
const clone = (x) => JSON.parse(JSON.stringify(x));
const BANNED = ['auto-confirmed', 'skips review', 'skip review', 'skipped review', 'skip human review', 'skip the person', 'skip a person', 'clinically accurate', 'works on real notes'];
const app = buildApp();
const regions = app.analysis.regions;
const sum = (rows, f) => rows.reduce((s, r) => s + f(r), 0);
const del = (o, path) => { const ks = path.split('.'); let v = o; for (const k of ks.slice(0, -1)) v = v[k]; delete v[ks.at(-1)]; return o; };

// ------------------------------------------------------------------ safety net
test('safety net: the bundle in app.json is the result file plus its source, marked SYNTHETIC', { skip: !has(FILES.safetyNet) }, () => {
  const file = read(FILES.safetyNet), s = app.safetyNet;
  assert.ok(s, 'app.safetyNet is present when its file exists');
  for (const [k, v] of Object.entries(file)) assert.deepEqual(s[k], v, k);
  assert.deepEqual(s.source, { file: FILES.safetyNet, sha256: sha256(FILES.safetyNet) });
  assert.equal(s.statement, SYNTHETIC); assert.equal(s.synthetic, true); assert.equal(s.dataClass, 'SYNTHETIC');
  assert.equal(s.counties.length, regions.length, 'one worklist row per area of the snapshot');
  assert.ok(s.counties.every((c) => regions.some((r) => r.regionId === c.regionId) && c.synthetic === true && c.examples.length <= 3 && c.examples.every((e) => e.synthetic === true)));
  for (const k of ['open_loops', 'overdue']) assert.equal(s.national[k], sum(s.counties, (c) => c.counts[k]), `national ${k} is the sum of the county rows`);
  for (const k of ['open', 'overdue', 'due_passed', 'done_by_due']) assert.equal(s.national.imaging[k], sum(s.counties, (c) => c.counts.imaging[k]), `imaging ${k}`);
  for (const k of ['open', 'overdue', 'clock_passed', 'diagnosed_by_threshold']) assert.equal(s.national.referral[k], sum(s.counties, (c) => c.counts.referral[k]), `referral ${k}`);
  assert.ok(s.thresholds.filter((t) => typeof t.days === 'number').every((t) => t.label === 'PLACEHOLDER'), 'every numeric clock threshold is a placeholder');
  const pilot = s.counties.find((c) => c.regionId === s.pilotRegionId);
  assert.ok(pilot && pilot.name === regions.find((r) => r.regionId === s.pilotRegionId).name.replace(' wellbeing services county', ''), 'the pilot county is a named area of the snapshot');
});

test('safety net: every county renders without gaps, the pilot is labelled, small counts are shown as <5, banned wording is absent', { skip: !app.safetyNet }, () => {
  const s = clone(app.safetyNet), below = s.suppression.below;
  for (const r of regions) {
    const html = safetyNetHtml(s, r.regionId);
    assert.ok(!/undefined|NaN|\[object Object\]/.test(html), r.regionId);
    assert.match(html, /class="chip synthetic"/);
    for (const w of BANNED) assert.ok(!html.toLowerCase().includes(w), `${r.regionId}: ${w}`);
    const c = s.counties.find((x) => x.regionId === r.regionId);
    if (c.counts.overdue > 0 && c.counts.overdue < below) assert.match(html, /Overdue on the replay date \([^)]*\) <span class="chip synthetic">SYNTHETIC<\/span><\/p><strong>&lt;5<\/strong>/, `${r.regionId} small overdue count suppressed`);
    assert.ok((html.match(/<tr><td><code>/g) || []).length <= 3, 'at most three example rows');
  }
  const pilot = safetyNetHtml(s, s.pilotRegionId);
  assert.match(pilot, /\(pilot county\)/);
  assert.match(pilot, /PLACEHOLDER/); assert.match(pilot, /Governance\./); assert.match(pilot, /No patient data leaves the county|no patient data leaves the county/i);
  assert.match(safetyNetHtml(s, 'HVA00'), /class="missing-label"/, 'an unknown county shows its absence');
  assert.match(safetyNetHtml(undefined), /class="missing-label"/, 'no bundle shows its absence');
});

// ------------------------------------------------------------------ comparability gate
test('comparability gate: the bundle equals its file; the summary counts equal the county verdicts; the national row is the sum of the counties', { skip: !has(FILES.flareGate) }, () => {
  const file = read(FILES.flareGate), g = app.flareGate;
  assert.ok(g, 'app.flareGate is present when its file exists');
  for (const [k, v] of Object.entries(file)) assert.deepEqual(g[k], v, k);
  assert.deepEqual(g.source, { file: FILES.flareGate, sha256: sha256(FILES.flareGate) });
  assert.equal(g.statement, SYNTHETIC); assert.equal(g.synthetic, true); assert.equal(g.label, 'SYNTHETIC');
  assert.equal(g.counties.length, regions.length);
  for (const arm of ['raw', 'resolver']) {
    assert.equal(g.summary[arm].not_comparable, g.counties.filter((c) => c.scribe[arm].comparable === false).length, arm);
    assert.equal(g.summary[arm].of, g.counties.length, arm);
  }
  const open = g.counties.filter((c) => !c.rtt.suppressed);
  assert.equal(g.national.n, sum(open, (c) => c.rtt.n)); assert.equal(g.national.within, sum(open, (c) => c.rtt.within));
  assert.match(g.clock.threshold_label, /placeholder \(OECD\/EU-reported target\)/);
  assert.match(g.clock.threshold_text, /six months/);
  if (g.flare.ran) assert.ok(g.flare.equivalence.success && g.flare.equivalence.cells_ok === g.flare.equivalence.cells);
  assert.equal(g.realData.kind, 'PUBLISHED');
  assert.ok(!/HVA\d/.test(JSON.stringify(g.realData)), 'the public stage chip names areas, never a SYNTHETIC county code');
});

test('comparability gate: the panel renders every county with both arms, keeps raw values beside "not comparable", and avoids banned wording', { skip: !app.flareGate }, () => {
  const g = clone(app.flareGate), html = flareGateHtml(g);
  assert.ok(!/undefined|NaN|\[object Object\]/.test(html));
  assert.equal((html.match(/data-gate="not-comparable"/g) || []).length, g.summary.raw.not_comparable + g.summary.resolver.not_comparable);
  assert.equal((html.match(/<tr><th>HVA/g) || []).length, g.counties.length);
  assert.match(html, /placeholder \(OECD\/EU-reported target\)/);
  assert.match(html, /class="chip synthetic"/); assert.match(html, /class="chip published"/); assert.match(html, /class="chip assumption"/);
  for (const w of BANNED) assert.ok(!html.toLowerCase().includes(w), w);
  assert.match(flareGateHtml(undefined), /class="missing-label"/);
});

// ------------------------------------------------------------------ build rules
test('required fields: a result file without a field its panel reads fails the build, and the synthetic marks are enforced', { skip: !has(FILES.safetyNet) || !has(FILES.flareGate) }, () => {
  const s = read(FILES.safetyNet), g = read(FILES.flareGate);
  assert.doesNotThrow(() => buildSafetyNet(clone(s), regions));
  assert.doesNotThrow(() => buildFlareGate(clone(g), regions));
  for (const path of ['text.legal', 'text.governance', 'rule.caveat', 'suppression.below', 'pilotRegionId', 'cohort.imaging_loops.errors.missed_recommendation']) {
    assert.throws(() => buildSafetyNet(del(clone(s), path), regions), new RegExp(`required field "${path.replace(/\./g, '\\.')}" is missing`), path);
  }
  const noCount = clone(s); delete noCount.counties[0].counts.overdue;
  assert.throws(() => buildSafetyNet(noCount, regions), /counts\.overdue/);
  const notSynth = clone(s); notSynth.synthetic = false;
  assert.throws(() => buildSafetyNet(notSynth, regions), /not marked synthetic/);
  const rowNotSynth = clone(s); const withRow = rowNotSynth.counties.find((c) => c.examples.length); withRow.examples[0].synthetic = false;
  assert.throws(() => buildSafetyNet(rowNotSynth, regions), /not marked synthetic/);
  const four = clone(s); const c0 = four.counties.find((c) => c.examples.length); while (c0.examples.length < 4) c0.examples.push(clone(c0.examples[0]));
  assert.throws(() => buildSafetyNet(four, regions), /at most three/);
  const unlabelled = clone(s); unlabelled.thresholds.find((t) => typeof t.days === 'number').label = 'TARGET';
  assert.throws(() => buildSafetyNet(unlabelled, regions), /not labelled PLACEHOLDER/);
  const noPilot = clone(s); noPilot.pilotRegionId = 'HVA00';
  assert.throws(() => buildSafetyNet(noPilot, regions), /pilot county/);
  const stranger = clone(s); stranger.counties[0].regionId = 'HVA00';
  assert.throws(() => buildSafetyNet(stranger, regions), /not an area of the public snapshot/);

  for (const path of ['clock.threshold_label', 'rule.bias_limit_days', 'summary.raw.not_comparable', 'national.share_within', 'limits']) {
    assert.throws(() => buildFlareGate(del(clone(g), path), regions), new RegExp(`required field "${path.replace(/\./g, '\\.')}" is missing`), path);
  }
  const noVerdict = clone(g); delete noVerdict.counties[0].scribe.raw.comparable;
  assert.throws(() => buildFlareGate(noVerdict, regions), /comparable/);
  const gNotSynth = clone(g); gNotSynth.synthetic = false;
  assert.throws(() => buildFlareGate(gNotSynth, regions), /not marked synthetic/);
  const gTarget = clone(g); gTarget.clock.threshold_label = 'six-week target';
  assert.throws(() => buildFlareGate(gTarget, regions), /not labelled a placeholder/);
  const ranNoEq = clone(g); ranNoEq.flare.ran = true; delete ranNoEq.flare.equivalence;
  assert.throws(() => buildFlareGate(ranNoEq, regions), /flare\.equivalence/);
  const notRan = clone(g); notRan.flare = { ran: false }; delete notRan.realData;
  assert.doesNotThrow(() => buildFlareGate(notRan, regions), 'FLARE not run and no public chip: the panel shows its fallback wording');
  assert.match(flareGateHtml(buildFlareGate(notRan, regions)), /FLARE-ready, not run in FLARE/);
  const realUnlabelled = clone(g); realUnlabelled.realData.kind = 'SYNTHETIC';
  assert.throws(() => buildFlareGate(realUnlabelled, regions), /PUBLISHED/);
});

test('missing file: an absent result file leaves its panel out of app.json and names the reason', () => {
  const out = buildTracks(regions, { safetyNet: 'data/safetynet/absent-v0.json', flareGate: 'data/flare/absent-v0.json' });
  assert.ok(!('safetyNet' in out) && !('flareGate' in out));
  assert.deepEqual(out.trackProblems.filter((p) => ['safetyNet', 'flareGate'].includes(p.track)), [
    { track: 'safetyNet', problem: 'source file missing: data/safetynet/absent-v0.json' },
    { track: 'flareGate', problem: 'source file missing: data/flare/absent-v0.json' },
  ]);
  assert.deepEqual(app.trackProblems, [], 'the shipped build has no missing part');
});

// ------------------------------------------------------------------ page shell
test('page shell: both mount points sit in section 05 after the pilot card, app.mjs fills them from app.json and the nav links to them', () => {
  const html = text('web/index.html'), appJs = text('web/app.mjs');
  const action = html.slice(html.indexOf('<section id="action"'), html.indexOf('</section>', html.indexOf('<section id="action"')));
  const at = (s) => action.indexOf(s);
  assert.ok(at('<div id="pilot">') > 0 && at('<div id="safety-net"') > at('<div id="pilot">') && at('<div id="comparability-gate"') > at('<div id="safety-net"'), 'order: pilot card, safety net, gate');
  for (const id of ['safety-net', 'comparability-gate']) {
    assert.match(action, new RegExp(`<div id="${id}" class="mount-point" data-mount="${id}" hidden></div>`));
    assert.ok(html.slice(html.indexOf('<nav'), html.indexOf('</nav>')).includes(`href="#${id}"`), `nav links to #${id}`);
  }
  assert.match(appJs, /import \{safetyNetHtml\} from '\.\/safetynet\.mjs'/);
  assert.match(appJs, /import \{flareGateHtml\} from '\.\/flare\.mjs'/);
  assert.match(appJs, /safetyNetHtml\(s,selected\)/, 'the worklist follows the selected county');
  assert.match(appJs, /flareGateHtml\(app\.flareGate\)/);
  assert.match(appJs, /el\.hidden=false/);
  assert.match(appJs, /renderPlanner\(\);renderSafetyNet\(\);\}/, 'selecting a county re-renders the worklist');
  assert.ok(!/fetch\('\/data\/(safetynet|flare)\//.test(appJs), 'the panels read the bundle in app.json, not the raw files');
  assert.match(text('web/styles.css'), /\.mount-point\{scroll-margin-top/);
  for (const w of BANNED) assert.ok(!(html + appJs).toLowerCase().includes(w), w);
});

// ------------------------------------------------------------------ wording over the whole page
// A person confirms every extracted event (NVIDIA_OPTIONS.md 3). The banned phrases are checked in every
// rendered panel, in every page module, in the built app.json on disk and in a fresh build.
test('wording: no rendered panel, page module or app.json says notes skip review or claims clinical accuracy', () => {
  const rendered = [whoHtml, processHtml, pilotHtml, scribeHtml, dataPlanHtml].map((f) => f(clone(app))).join('')
    + (app.safetyNet ? regions.map((r) => safetyNetHtml(app.safetyNet, r.regionId)).join('') : '')
    + (app.flareGate ? flareGateHtml(app.flareGate) : '');
  const modules = readdirSync(url('web')).filter((f) => f.endsWith('.mjs')).map((f) => text(`web/${f}`)).join('\n') + text('web/index.html');
  const bodies = [['rendered panels', rendered], ['web/*.mjs and web/index.html', modules], ['fresh build', JSON.stringify(app)]];
  if (has('web/data/app.json')) bodies.push(['web/data/app.json', text('web/data/app.json')]);
  for (const [where, body] of bodies) for (const w of BANNED) assert.ok(!body.toLowerCase().includes(w), `${where}: ${w}`);
});
