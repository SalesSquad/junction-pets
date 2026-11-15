/**
 * Deterministic quantity take-off for layered architectural DXF (Swiss Dwellings convention:
 * ROOM_OUTLINE, ROOM_TEXT, UNIT_OUTLINE, DOOR, WINDOW, FIXTURE). Every count and area cites the
 * exact source entities. Questions may be English, German, French or Italian.
 * Conventions were measured on development drawings only (see bench/swiss-dxf.mjs):
 *   door    = one opening polyline per door: DOOR polylines − DOOR swing arcs
 *   window  = three parallel WINDOW polylines per window
 *   shower  = FIXTURE drain circle r ≈ 0.04 m
 *   basin   = drain circle r ≈ 0.02–0.03 m in a narrow fixture (short side < 0.65 m)
 *   bathtub = drain circle r ≈ 0.03 m in a tub-sized fixture (≥ 0.65 × 1.3 m)
 *   WC      = circle-free fixture of WC-bowl size (≈ 0.3–0.48 × 0.45–0.72 m)
 *   room area = area of the smallest closed ROOM_OUTLINE enclosing the room-number text
 * Anything outside these conventions returns null so the caller can abstain.
 */
import { answerDrawing, pointInPolygon, polygonArea } from './grounding.mjs';

const UNIT_TO_M = Object.freeze({ 1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1 });
const OUTDOOR = /^(balkon|balcon|balcone|loggia|terrasse|terrazza|dachterrasse|sitzplatz|veranda|schacht|luftraum|vide|vuoto|cavedio|gaine|shaft|void)\b/i;
const ROOM_NUMBER = /^[A-Z]?\d+(?:\.\d+)+$/;
const UNIT_LABEL = /^(Whg|App|Apt|Log|Wohnung|Appartamento|Appartement)\.?\s+([A-Z0-9]{1,3})$/i;

const ev = (e, detail) => ({ entityId: e.id, layer: e.layer, kind: e.type, detail });
const ok = (drawing, answer, explanation, evidence, metric) => ({
  status: 'supported', answer: String(answer), explanation, metric, evidence,
  source: { filename: drawing.filename, sha256: drawing.sha256 || null, format: drawing.format, units: drawing.unitsLabel },
  inference: 'deterministic; no external model',
});
const no = (drawing, reason) => ({
  status: 'abstained', answer: null, explanation: reason, metric: null, evidence: [],
  source: { filename: drawing.filename, sha256: drawing.sha256 || null }, inference: 'deterministic; no external model',
});

function bbox(e) {
  if (e.points) {
    const xs = e.points.map(p => p.x), ys = e.points.map(p => p.y);
    return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  }
  return [e.x - e.radius, e.y - e.radius, e.x + e.radius, e.y + e.radius];
}

const isRect = e => e.type === 'LWPOLYLINE' && e.points.length >= 4 && e.points.length <= 5 &&
  (e.closed || Math.hypot(e.points[0].x - e.points.at(-1).x, e.points[0].y - e.points.at(-1).y) < 1e-6);
const inside = (b, r, tol) => b[0] >= r[0] - tol && b[1] >= r[1] - tol && b[2] <= r[2] + tol && b[3] <= r[3] + tol;

/**
 * Fixture symbols: a closed outline rectangle plus the primitives drawn inside it. Each inner
 * primitive belongs to its smallest enclosing rectangle, so adjacent fixtures never merge and a
 * sink inside a kitchen counter stays separate from the counter.
 */
export function fixtureSymbols(entities, scale) {
  const fx = entities.filter(e => e.layer === 'FIXTURE' && (e.points || e.radius));
  const rects = fx.filter(isRect).map(e => ({ e, box: bbox(e), inner: [] }));
  const area = b => (b[2] - b[0]) * (b[3] - b[1]);
  for (const p of fx) {
    if (rects.some(r => r.e === p)) continue;
    const b = bbox(p);
    const owner = rects.filter(r => inside(b, r.box, 0.01 / scale)).sort((x, y) => area(x.box) - area(y.box))[0];
    if (owner) owner.inner.push(p);
  }
  return rects.map(({ e, box, inner }) => {
    const w = (box[2] - box[0]) * scale, h = (box[3] - box[1]) * scale;
    const radii = inner.filter(p => p.type === 'CIRCLE').map(c => c.radius * scale);
    const curved = inner.some(p => p.points && p.points.length >= 8);
    const short = Math.min(w, h), long = Math.max(w, h);
    let kind = null;
    if (radii.some(r => r >= 0.035 && r <= 0.045)) kind = 'shower';
    else if (radii.filter(r => r >= 0.06).length >= 2) kind = 'stove';
    else if (radii.some(r => r >= 0.015 && r < 0.035)) kind = short >= 0.6 && long >= 1.3 ? 'bathtub' : 'basin';
    else if (curved && long <= 0.9) kind = 'wc';
    return { kind, parts: [e, ...inner], short, long };
  });
}

/** Group touching fixture primitives into objects (union-find on expanded boxes). */
export function fixtureObjects(entities, scale) {
  const fx = entities.filter(e => e.layer === 'FIXTURE' && (e.points || e.radius));
  const boxes = fx.map(bbox), tol = 0.02 / scale, parent = fx.map((_, i) => i);
  const find = i => (parent[i] === i ? i : (parent[i] = find(parent[i])));
  for (let i = 0; i < fx.length; i++) for (let j = i + 1; j < fx.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (a[0] - tol <= b[2] && b[0] - tol <= a[2] && a[1] - tol <= b[3] && b[1] - tol <= a[3]) parent[find(i)] = find(j);
  }
  const groups = new Map();
  fx.forEach((e, i) => { const r = find(i); groups.set(r, [...(groups.get(r) ?? []), i]); });
  return [...groups.values()].map(ix => {
    const bb = ix.map(i => boxes[i]);
    const w = (Math.max(...bb.map(b => b[2])) - Math.min(...bb.map(b => b[0]))) * scale;
    const h = (Math.max(...bb.map(b => b[3])) - Math.min(...bb.map(b => b[1]))) * scale;
    const parts = ix.map(i => fx[i]);
    return { parts, short: Math.min(w, h), long: Math.max(w, h), circles: parts.filter(p => p.type === 'CIRCLE').map(c => ({ e: c, r: c.radius * scale })) };
  });
}

function intent(question) {
  const q = question.toLowerCase();
  const count = /how many|wie viele|combien|quant[ie]/.test(q);
  if (count && /\b(doors?|türen|porte|portes)\b/.test(q)) return 'door';
  if (count && /\b(windows?|fenster|finestre|fenêtres)\b/.test(q)) return 'window';
  if (count && /\b(showers?|duschen|docce|douches?)\b/.test(q)) return 'shower';
  if (count && /\b(bathtubs?|badewannen?|vasche da bagno|baignoires?)\b/.test(q)) return 'bathtub';
  if (count && /\b(washbasins?|lavabos?|lavabi|lavandini|waschbecken)\b/.test(q)) return 'basin';
  if (count && /\b(toilets?|wcs?|toilettes?|gabinetti)\b/.test(q) && !/room|räume|locali|pièces/.test(q)) return 'wc';
  if (count && /apartments?|residential units?|wohnungen|appartamenti|appartements?|logements?|unità abitative/.test(q)) return 'apartments';
  if (/m²|m2|area|fläche|surface|superficie/.test(q)) {
    const apt = question.match(/\b(?:apartment|wohnung|appartamento|appartement|dell'appartamento|de l'appartement)\s+([A-Z0-9]{1,3})\b/i);
    if (apt) return { kind: 'apartmentArea', unit: apt[1] };
    if (/numbered|nummerierten|numérotées|numerati/i.test(q)) return 'numberedArea';
    const room = question.match(/\b([A-Z]?\d+(?:\.\d+)+)\b/);
    if (room) return { kind: 'roomArea', number: room[1] };
    const label = question.match(/['‘«„"]([^'’»“"]{2,40})['’»“"]/);
    if (label && /total|gesamte|totale/i.test(q)) return { kind: 'labelArea', label: label[1].trim() };
  }
  return null;
}

/** Each numbered room: its number text, the smallest enclosing closed outline, and its name label. */
function rooms(drawing, scale) {
  const outlines = drawing.entities.filter(e => e.layer === 'ROOM_OUTLINE' && e.points?.length >= 3);
  const texts = drawing.entities.filter(e => e.layer === 'ROOM_TEXT' && e.text);
  const smallest = p => outlines.filter(o => pointInPolygon(p, o.points)).sort((a, b) => polygonArea(a.points) - polygonArea(b.points))[0];
  const nameOf = outline => texts.find(t => !ROOM_NUMBER.test(t.text.trim()) && !/m²|m2$/.test(t.text) && !UNIT_LABEL.test(t.text.trim()) && smallest(t) === outline);
  return texts.filter(t => ROOM_NUMBER.test(t.text.trim())).map(t => {
    const outline = smallest(t);
    return outline && { number: t.text.trim(), numberText: t, outline, name: nameOf(outline), area: polygonArea(outline.points) * scale * scale };
  }).filter(Boolean);
}
const round2 = v => Math.round(v * 100) / 100;

/** The longest room name on the drawing that the question quotes (handles "/", apostrophes, «», „“). */
function quotedRoomName(drawing, question) {
  const names = new Set(drawing.entities.filter(e => e.layer === 'ROOM_TEXT' && e.text).map(e => e.text.trim())
    .filter(t => t.length >= 2 && !ROOM_NUMBER.test(t) && !/m²|m2$/.test(t) && !UNIT_LABEL.test(t)));
  // Prefer the quoted span: «…», „…“, "…", or the outermost '…' (names may contain an apostrophe).
  const quoted = (question.match(/«\s*(.+?)\s*»/) ?? question.match(/„(.+?)“/) ?? question.match(/"(.+?)"/) ?? question.match(/'(.+)'/))?.[1]?.trim().toLowerCase();
  if (quoted) return [...names].find(n => n.toLowerCase() === quoted) ?? null;
  const q = question.toLowerCase();
  return [...names].filter(n => new RegExp(`(^|[^\\p{L}])${n.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^\\p{L}]|$)`, 'u').test(q))
    .sort((a, b) => b.length - a.length)[0] ?? null;
}
const LABEL_WORDS = /labell?ed|bezeichnung|désignation|désignées|denominazione|denominati/i;

export function answerQuantities(drawing, question) {
  let what = intent(question);
  if (LABEL_WORDS.test(question)) {
    const name = quotedRoomName(drawing, question);
    if (!name) return null;
    const isArea = /m²|m2|area|fläche|surface|superficie/i.test(question);
    what = isArea ? { kind: 'labelArea', label: name } : { kind: 'labelCount', label: name };
  }
  if (!what) return null;
  const scale = UNIT_TO_M[drawing.units];
  if (!scale) return no(drawing, 'DXF units are missing or unsupported; quantities cannot be measured.');
  const E = drawing.entities;

  if (what === 'door') {
    const polys = E.filter(e => e.layer === 'DOOR' && e.type === 'LWPOLYLINE'), arcs = E.filter(e => e.layer === 'DOOR' && e.type === 'ARC');
    const n = polys.length - arcs.length;
    if (!arcs.length || n <= 0 || n > arcs.length) return no(drawing, 'DOOR layer does not follow the one-opening-per-door convention.');
    return ok(drawing, n, `${n} doors: ${polys.length} DOOR polylines minus ${arcs.length} leaf swing arcs (one opening line per door; double doors have two leaves). Every door part is highlighted.`,
      [...arcs.map(e => ev(e, 'Door leaf swing')), ...polys.map(e => ev(e, 'Door leaf or opening'))], { type: 'count', value: n, unit: 'doors' });
  }
  if (what === 'window') {
    const w = E.filter(e => e.layer === 'WINDOW' && e.type === 'LWPOLYLINE');
    if (!w.length || w.length % 3) return no(drawing, 'WINDOW layer does not follow the three-line-per-window convention.');
    return ok(drawing, w.length / 3, `${w.length / 3} windows: ${w.length} WINDOW lines, three per window (frame, glass, frame).`,
      w.map(e => ev(e, 'Window line')), { type: 'count', value: w.length / 3, unit: 'windows' });
  }
  if (['shower', 'bathtub', 'basin', 'wc'].includes(what)) {
    const hits = fixtureSymbols(E, scale).filter(s => s.kind === what);
    const label = { shower: 'showers', bathtub: 'bathtubs', basin: 'washbasins', wc: 'toilets' }[what];
    const detail = { shower: 'Shower tray and drain', bathtub: 'Bathtub and drain', basin: 'Washbasin bowl and drain', wc: 'WC bowl' }[what];
    return ok(drawing, hits.length, `${hits.length} ${label}: FIXTURE outline rectangles whose own inner symbol matches (bowl, drain size, tub size). Each counted fixture is highlighted.`,
      hits.flatMap(h => h.parts.map(e => ev(e, detail))), { type: 'count', value: hits.length, unit: label });
  }
  if (what === 'apartments') {
    const labels = E.filter(e => e.layer === 'ROOM_TEXT' && UNIT_LABEL.test(e.text?.trim() ?? ''));
    if (!labels.length) return null; // fall back to UNIT_OUTLINE counting in grounding.mjs
    return ok(drawing, labels.length, `${labels.length} apartment labels (${labels.map(l => l.text.trim()).join(', ')}).`,
      labels.map(e => ev(e, `Apartment label ${e.text.trim()}`)), { type: 'count', value: labels.length, unit: 'apartments' });
  }

  const all = rooms(drawing, scale);
  const cite = rs => rs.flatMap(r => [ev(r.outline, `Room ${r.number} outline, ${round2(r.area)} m²`), ev(r.numberText, `Room number ${r.number}`)]);
  const indoor = r => !(r.name && OUTDOOR.test(r.name.text.trim()));
  if (what.kind === 'roomArea') {
    const r = all.filter(x => x.number === what.number);
    if (r.length !== 1) return no(drawing, `Room ${what.number} is absent or not uniquely enclosed by one closed outline.`);
    const a = round2(r[0].area);
    return ok(drawing, `${a} m²`, `Room ${what.number}: measured area of its smallest enclosing closed outline.`, cite(r), { type: 'area', value: a, unit: 'm²', tolerancePercent: 2 });
  }
  if (what.kind === 'labelCount') {
    const target = what.label.toLowerCase();
    const hits = E.filter(e => e.layer === 'ROOM_TEXT' && e.text?.trim().toLowerCase() === target);
    return ok(drawing, hits.length, `${hits.length} ROOM_TEXT labels read exactly “${what.label}”. Each label position is highlighted.`,
      hits.map(e => ev(e, `ROOM_TEXT: ${e.text}`)), { type: 'count', value: hits.length, unit: what.label });
  }
  if (what.kind === 'labelArea') {
    const target = what.label.toLowerCase();
    const rs = [...new Map(all.filter(r => r.name?.text.trim().toLowerCase() === target).map(r => [r.outline.id, r])).values()];
    if (!rs.length) return no(drawing, `No numbered room labelled ${what.label}.`);
    const a = round2(rs.reduce((s, r) => s + r.area, 0));
    return ok(drawing, `${a} m²`, `Sum of ${rs.length} rooms labelled ${what.label}.`, cite(rs), { type: 'area', value: a, unit: 'm²', tolerancePercent: 2 });
  }
  if (what === 'numberedArea') {
    const rs = [...new Map(all.filter(indoor).map(r => [r.outline.id, r])).values()];
    if (!rs.length) return no(drawing, 'No numbered rooms with closed outlines.');
    const a = round2(rs.reduce((s, r) => s + r.area, 0));
    return ok(drawing, `${a} m²`, `Sum of ${rs.length} numbered indoor rooms (balconies, loggias, terraces, shafts and voids excluded).`, cite(rs), { type: 'area', value: a, unit: 'm²', tolerancePercent: 2 });
  }
  if (what.kind === 'apartmentArea') {
    const label = E.find(e => e.layer === 'ROOM_TEXT' && UNIT_LABEL.test(e.text?.trim() ?? '') && e.text.trim().match(UNIT_LABEL)[2].toUpperCase() === what.unit.toUpperCase());
    if (!label) return no(drawing, `No apartment labelled ${what.unit}.`);
    const units = E.filter(e => e.layer === 'UNIT_OUTLINE' && e.points?.length >= 3 && pointInPolygon(label, e.points))
      .sort((a, b) => polygonArea(a.points) - polygonArea(b.points));
    if (!units.length) return no(drawing, `Apartment ${what.unit} has no enclosing unit outline.`);
    const unit = units[0];
    const rs = [...new Map(all.filter(r => indoor(r) && pointInPolygon(r.numberText, unit.points)).map(r => [r.outline.id, r])).values()];
    const a = round2(rs.reduce((s, r) => s + r.area, 0));
    return ok(drawing, `${a} m²`, `Apartment ${what.unit}: sum of ${rs.length} indoor rooms inside its unit outline.`,
      [ev(unit, `Apartment ${what.unit} outline`), ev(label, `Label ${label.text.trim()}`), ...cite(rs)], { type: 'area', value: a, unit: 'm²', tolerancePercent: 2 });
  }
  return null;
}

/** Quantity take-off first, then the original label/area/unit engine. */
export function answerDrawingV2(drawing, question) {
  return answerQuantities(drawing, question) ?? answerDrawing(drawing, question);
}
