// Builds web/data/app.json from the public snapshot, the evidence table and
// (when present) the early-warning forecast. Run: `node src/build.mjs`.
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { analyse } from './analysis.mjs';
import { recommend } from './recommend.mjs';
import { buildTracks } from './tracks.mjs';
import { getPilotCard, getRoadmapMeasure, getThresholdRelabels, listActionIds, ROADMAP } from './roadmap.mjs';

// The roadmap measure each action serves (data/roadmap/mapping-v1.json via src/roadmap.mjs), the pilot card
// and the threshold relabels, so the page can show measure ids without reading files in the browser.
const brief = (m) => (m ? { id: m.id, title_en: m.title_en, pages: m.pages, owner_en: m.owner_en, url: m.url } : null);
export function buildRoadmap() {
  const actions = Object.fromEntries(listActionIds().map((id) => {
    const r = getRoadmapMeasure(id);
    return [id, { fit: r.fit, statement: r.statement, primary: brief(r.primaryMeasure), related: r.relatedMeasures.map(brief), noRoadmapMeasureFor: r.noRoadmapMeasureFor ?? null }];
  }));
  const extra = Object.fromEntries(['1.3.1', '2.3.4', '3.2.1'].map((id) => [id, brief(getRoadmapMeasure(id).measure)]));
  return { source: { title: ROADMAP.sourceUrl && getRoadmapMeasure('3.2.1').source.titleEn, url: ROADMAP.sourceUrl, sha256: ROADMAP.sourceSha256 }, actions, measures: extra, pilotCard: getPilotCard(), thresholdRelabels: getThresholdRelabels() };
}

const at = (p) => new URL(p, import.meta.url);
const readJson = (p) => JSON.parse(readFileSync(at(p), 'utf8'));
const sha256 = (p) => createHash('sha256').update(readFileSync(at(p))).digest('hex');

export function buildApp() {
  const snapshot = readJson('../data/snapshot/public-v1.json');
  const evidence = readJson('../data/evidence/literature-v1.json');
  const analysis = analyse(snapshot);
  const recommendation = recommend(analysis);
  const forecastPath = '../data/ml/forecast-v1.json';
  const forecast = existsSync(at(forecastPath)) ? readJson(forecastPath) : null;
  const optional = (path) => (existsSync(at(path)) ? readJson(path) : null);
  const evalRun = optional('../data/claim-check/eval-v1.json');
  // Stored verdicts are only valid for the snapshot they were computed on.
  const claimCheck = evalRun && evalRun.snapshotSha256 === sha256('../data/snapshot/public-v1.json') && { service: evalRun.service, model: evalRun.model, ranAt: evalRun.ranAt, autoAccept: evalRun.autoAccept, cases: evalRun.cases, summary: evalRun.summary, overall: evalRun.overall, verdicts: evalRun.verdicts, note: evalRun.note };
  const narrativeRun = optional('../data/narratives/fi-v1.json');
  const narratives = narrativeRun && narrativeRun.status === 'CHECKED' ? { generatedAt: narrativeRun.generatedAt, verifier: narrativeRun.verifier, totals: narrativeRun.totals, counties: narrativeRun.counties } : null;
  const known = new Set(evidence.rows.map((r) => r.id));
  const cited = new Set([
    ...recommendation.interventions.flatMap((i) => i.evidence),
    ...Object.values(recommendation.assumptions).flatMap((a) => a.evidence || []),
    recommendation.validation.evidence, analysis.goal3.source,
  ]);
  const missing = [...cited].filter((id) => !known.has(id));
  const unverifiedCited = [...cited].filter((id) => evidence.rows.find((r) => r.id === id)?.verified === false);
  if (missing.length || unverifiedCited.length) {
    throw new Error(`evidence binding failed: missing=${missing.join(',')} unverified=${unverifiedCited.join(',')}`);
  }
  return {
    schemaVersion: 'care-equity-app-v1',
    builtAt: new Date().toISOString(),
    provenance: {
      dataClass: snapshot.dataClass, snapshotGeneratedAt: snapshot.generatedAt, snapshotSha256: sha256('../data/snapshot/public-v1.json'),
      evidenceSha256: sha256('../data/evidence/literature-v1.json'), forecastSha256: forecast ? sha256(forecastPath) : null,
      sources: snapshot.sources, requests: snapshot.manifest.length, notes: snapshot.notes,
    },
    analysis, recommendation, forecast, claimCheck, narratives,
    evidence: evidence.rows, evidenceMethod: evidence.method,
    roadmap: buildRoadmap(),
    // Optional side tracks (present only when their result files exist): eventLog and scribe are
    // SYNTHETIC, genomics is research-only. They never feed the analysis or the recommendations above.
    // safetyNet (DO #2 worklist) and flareGate (DO #3 comparability gate) are the SYNTHETIC panels mounted
    // in section 05; they too are display-only and never change a county figure or a recommendation.
    ...buildTracks(analysis.regions),
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const app = buildApp();
  mkdirSync(at('../web/data/'), { recursive: true });
  writeFileSync(at('../web/data/app.json'), `${JSON.stringify(app)}\n`);
  const r = app.recommendation;
  console.log(JSON.stringify({
    out: 'web/data/app.json', regions: app.analysis.regions.length, evidenceRows: app.evidence.length, forecast: !!app.forecast, claimCheck: !!app.claimCheck, narratives: app.narratives ? Object.keys(app.narratives.counties).length : 0,
    tracks: { eventLog: !!app.eventLog, scribe: !!app.scribe, genomics: app.genomics ? app.genomics.status : false, safetyNet: !!app.safetyNet, flareGate: !!app.flareGate, problems: app.trackProblems },
    portfolio: { budget: r.budget, picks: r.portfolio.picks.length, deathsPostponed: r.portfolio.deathsPostponed, range: [r.portfolio.low, r.portfolio.high] },
  }));
}
