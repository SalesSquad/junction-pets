// Ties every SAMA action to a measure of the national cancer strategy's
// implementation roadmap 2026-2031 (data/roadmap/, PDF pinned by sha256).
// Each Finnish quote is verbatim from the pdftotext output; English text is
// the SAMA team's own reading. Used by the Nemotron planner tool
// get_roadmap_measure and by the integrator.
//
//   node src/roadmap.mjs <actionId>     e.g. timed-pathways, four-timestamps
//   node src/roadmap.mjs <measureId>    e.g. 3.1.2
//   node src/roadmap.mjs pilot | relabels | list
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const at = (p) => new URL(p, import.meta.url);
// Loaded once; a missing or unreadable file leaves ROADMAP null instead of breaking every importer (the build, the
// planner tools). ROADMAP_PROBLEM then names the file, and every function below answers "roadmap not available".
const load = (file) => JSON.parse(readFileSync(at(`../data/roadmap/${file}`), 'utf8'));
let roadmap = null, manifest = null, problem = null;
try { roadmap = load('mapping-v1.json'); } catch (e) { problem = `source file missing or unreadable: data/roadmap/mapping-v1.json (${e.code || e.message})`; }
if (!problem) { try { manifest = load('manifest.json'); } catch (e) { roadmap = null; problem = `source file missing or unreadable: data/roadmap/manifest.json (${e.code || e.message})`; } }
export const ROADMAP = roadmap;
export const MANIFEST = manifest;
export const ROADMAP_PROBLEM = problem;
const UNAVAILABLE = { error: 'roadmap not available', problem };

const MEASURE_ID = /^\d\.\d\.\d+$/;
const pageUrl = (page) => `${ROADMAP.sourceUrl}#page=${page}`;
const SOURCE = ROADMAP ? {
  title: MANIFEST.title,
  titleEn: MANIFEST.titleEn,
  url: ROADMAP.sourceUrl,
  pdfSha256: MANIFEST.pdf.sha256,
  note: ROADMAP.readingNote,
} : null;

function measureView(id) {
  const m = ROADMAP.measures[id];
  if (!m) return null;
  return { ...m, url: pageUrl(m.pages[0]) };
}

const brief = (id) => {
  const m = ROADMAP.measures[id];
  return { id, title_en: m.title_en, pages: m.pages, owner_en: m.owner_en, url: pageUrl(m.pages[0]) };
};

function findAction(actionId) {
  const key = String(actionId ?? '').trim();
  return ROADMAP.actions.find((a) => a.actionId === key || (a.aliases || []).includes(key)) || null;
}

export function listActionIds() {
  if (!ROADMAP) return [];
  return ROADMAP.actions.map((a) => a.actionId);
}

export function getThresholdRelabels() {
  if (!ROADMAP) return [];
  return ROADMAP.thresholdRelabels.map((r) => ({ ...r }));
}

export function getPilotCard() {
  if (!ROADMAP) return null;
  const card = ROADMAP.pilotCard;
  return { ...card, roadmapHooks: card.roadmapHooks.map((h) => ({ ...h, ...brief(h.measure) })), source: SOURCE };
}

// Returns the roadmap measure an action serves, with page, owner, schedule and
// metric quoted from the PDF, or fit 'none' with 'no roadmap measure'.
// Accepts an action id (INTERVENTIONS id or 'four-timestamps') or a measure id.
export function getRoadmapMeasure(actionId) {
  const key = String(actionId ?? '').trim();
  if (!ROADMAP) return { query: key, ...UNAVAILABLE };
  if (MEASURE_ID.test(key)) {
    const m = measureView(key);
    if (!m) return { query: key, error: 'measure not in the SAMA mapping', knownMeasureIds: Object.keys(ROADMAP.measures), source: SOURCE };
    const servedBy = ROADMAP.actions.filter((a) => a.primary === key || a.related.includes(key)).map((a) => a.actionId);
    return { query: key, measure: m, servedBy, source: SOURCE };
  }
  const a = findAction(key);
  if (!a) return { query: key, error: 'unknown action', knownActionIds: listActionIds(), source: SOURCE };
  const statement = a.fit === 'none'
    ? 'no roadmap measure'
    : a.fit === 'named'
      ? `Roadmap measure ${a.primary} names this action.`
      : `Serves roadmap measure ${a.primary}; the roadmap does not name this specific action.`;
  const thresholds = ROADMAP.thresholdRelabels.filter((r) => r.actions.includes(a.actionId));
  return {
    query: key,
    actionId: a.actionId,
    source: a.source,
    fit: a.fit,
    statement,
    primaryMeasure: a.primary ? measureView(a.primary) : null,
    relatedMeasures: a.related.map(brief),
    reading_en: a.reading_en,
    gap_en: a.gap_en,
    noRoadmapMeasureFor: a.noRoadmapMeasureFor,
    ...(thresholds.length ? { thresholdRelabels: thresholds } : {}),
    roadmap: SOURCE,
  };
}

function main(argv) {
  const [arg] = argv;
  if (!arg || arg === '--help' || arg === '-h') {
    process.stderr.write('usage: node src/roadmap.mjs <actionId|measureId|pilot|relabels|list>\n');
    return 2;
  }
  let out;
  if (!ROADMAP) out = UNAVAILABLE;
  else if (arg === 'list') out = { actionIds: listActionIds(), measureIds: Object.keys(ROADMAP.measures) };
  else if (arg === 'pilot') out = getPilotCard();
  else if (arg === 'relabels') out = getThresholdRelabels();
  else out = getRoadmapMeasure(arg);
  process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
  return out && out.error ? 2 : 0;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  process.exitCode = main(process.argv.slice(2));
}
