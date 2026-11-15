/**
 * Deterministic IFC question answering (English, Estonian, Danish templates of the Stoa preview).
 * Counts come from typed elements contained in a storey; areas, lengths and volumes from the
 * model's stored base quantities (NetFloorArea, Length, NetSideArea, NetVolume), falling back to
 * an area property only when no quantity exists. Every answer cites IFC entity ids (#id) and GUIDs.
 */
const TYPES = {
  door: ['IFCDOOR', 'IFCDOORSTANDARDCASE'],
  window: ['IFCWINDOW', 'IFCWINDOWSTANDARDCASE'],
  wall: ['IFCWALL', 'IFCWALLSTANDARDCASE', 'IFCWALLELEMENTEDCASE'],
  column: ['IFCCOLUMN', 'IFCCOLUMNSTANDARDCASE'],
  beam: ['IFCBEAM'],
  stair: ['IFCSTAIR'],
  slab: ['IFCSLAB', 'IFCSLABSTANDARDCASE'],
  space: ['IFCSPACE'],
  sanitary: ['IFCSANITARYTERMINAL', 'IFCFLOWTERMINAL'],
};
const WORDS = [
  ['door', /\b(doors?|døre?|uks|ust|uksi)\b/i],
  ['window', /\b(windows?|vinduer|vindue|aken|akent|akna)\b/i],
  ['wall', /\b(walls?|vægge?|sein|seina|seinu)\b/i],
  ['column', /\b(columns?|søjler?|post|posti|poste)\b/i],
  ['beam', /\b(beams?|bjælker?|tala|talasid)\b/i],
  ['stair', /\b(stairs?|staircases?|trapper?|trepp|treppi|treppe)\b/i],
  ['sanitary', /sanitary|sanitet|sanitaar/i],
  ['space', /\b(rooms?|spaces?|rum|ruumi|ruume)\b/i],
];

const quoted = q => [...q.matchAll(/'([^']+)'|„([^“]+)“|"([^"]+)"|«([^»]+)»/g)].map(m => m.slice(1).find(Boolean).trim());
const ev = (m, e, detail) => ({ entityId: `#${e.id}`, guid: typeof e.args[0] === 'string' ? e.args[0] : null, kind: e.type, detail });
const ok = (answer, explanation, evidence, metric) => ({ status: 'supported', answer: String(answer), explanation, evidence, metric, inference: 'deterministic; no external model' });
const no = reason => ({ status: 'abstained', answer: null, explanation: reason, evidence: [], metric: null, inference: 'deterministic; no external model' });
const round = (v, d = 3) => Math.round(v * 10 ** d) / 10 ** d;

function quantity(m, e, names) {
  const qs = m.quantities.get(e.id) ?? [];
  for (const n of names) {
    const hit = qs.find(q => q.name === n && typeof q.value === 'number');
    if (hit) return { value: hit.value, kind: hit.kind, source: `${hit.set}/${hit.name}` };
  }
  return null;
}
const toSI = (m, q) => (q.kind === 'IFCQUANTITYLENGTH' ? q.value * (m.units.LENGTHUNIT?.factor ?? 1) : q.value);

function spaceArea(m, s) {
  const q = quantity(m, s, ['NetFloorArea']);
  if (q) return { value: toSI(m, q), source: q.source };
  const g = m.planArea(s);
  if (g != null && g > 0) return { value: g, source: 'measured plan area of the space body geometry' };
  const p = (m.props.get(s.id) ?? []).find(x => /pindala|net.?area|nettoareal|^area$/i.test(String(x.name).replace(/^\d+_/, '')));
  const v = p ? Number(String(p.value).replace(',', '.')) : NaN;
  return Number.isFinite(v) && v > 0 ? { value: v, source: `${p.set}/${p.name} (property)` } : null;
}

export function answerIfc(m, question) {
  const q = question.toLowerCase();
  const [first, second] = quoted(question);
  const storeyOf = name => m.storeys.find(s => s.name?.trim().toLowerCase() === name?.toLowerCase())?.e;
  // Whole-model counts use elements placed in the spatial structure; parts nested inside an
  // aggregate (e.g. stair components exported as IfcStair) are not separate objects.
  const elems = (kind, storey) => {
    const all = m.of(...TYPES[kind]);
    if (storey) return all.filter(e => m.storeyOf.get(e.id) === storey);
    const placed = all.filter(e => m.storeyOf.has(e.id));
    return placed.length ? placed : all;
  };

  // Room area: "net floor area of the room 'LongName (Number)' on 'Storey'".
  if (/\b(room|rummet|ruumi)\b/.test(q) && /area|areal|pind/.test(q) && second) {
    const storey = storeyOf(second);
    if (!storey) return no(`Storey ${second} not found.`);
    const label = first.toLowerCase();
    const cands = elems('space', storey).filter(s => {
      const name = String(s.args[2] ?? '').trim(), long = String(s.args[7] ?? '').trim();
      return [`${long} (${name})`, `${name} (${long})`, long, name].some(x => x.toLowerCase() === label);
    });
    if (cands.length !== 1) return no(`Room ${first} on ${second} is ${cands.length ? 'ambiguous' : 'absent'}.`);
    const a = spaceArea(m, cands[0]);
    if (!a) return no('The space carries no stored net floor area.');
    return ok(`${round(a.value, 2)} m²`, `Space ${first}: ${a.source}.`, [ev(m, cands[0], `IfcSpace ${first}`)], { type: 'area', value: round(a.value, 2), unit: 'm²' });
  }

  const storeyName = /storey|floor plan|on '|plantegningen|korruse|på '|på „| on „/i.test(question) && !/model|modellen|mudelis/i.test(q) ? (second ?? first) : null;
  const storey = storeyName ? storeyOf(storeyName) : null;
  if (storeyName && !storey) return no(`Storey ${storeyName} not found.`);
  const scope = storey ? `on ${storeyName}` : 'in the model';

  // Totals per storey (or model) from base quantities.
  const totals = [
    [/(total|samlede|kogu|kõigi).*(net floor area|nettoareal|netopõrandapind)|(net floor area|nettoareal|netopõrandapind).*(kokku)/, 'space', ['NetFloorArea'], 'm²'],
    [/(total|samlede|kogu).*(length|længde|pikkus).*(walls|vægge|sein)/, 'wall', ['Length'], 'm'],
    [/(net side area|nettosideareal|netokülgpind)/, 'wall', ['NetSideArea'], 'm²'],
    [/(net volume|nettovolumen|netomaht).*(walls|vægge|sein)/, 'wall', ['NetVolume'], 'm³'],
    [/(net volume|nettovolumen|netomaht).*(slabs|dæk|plader|plaat)/, 'slab', ['NetVolume'], 'm³'],
  ];
  for (const [rx, kind, names, unit] of totals) {
    if (!rx.test(q)) continue;
    const items = elems(kind, storey);
    let sum = 0; const used = [];
    for (const e of items) {
      const v = kind === 'space' ? spaceArea(m, e) : (x => x && { value: toSI(m, x), source: x.source })(quantity(m, e, names));
      if (v) { sum += v.value; used.push(e); }
    }
    if (!used.length) return no(`No stored ${names.join('/')} quantities ${scope}.`);
    const v = round(sum, 3);
    return ok(`${v} ${unit}`, `Sum of ${names.join('/')} over ${used.length} of ${items.length} ${kind} elements ${scope}.`,
      used.slice(0, 400).map(e => ev(m, e, kind)), { type: unit === 'm' ? 'length' : unit === 'm³' ? 'volume' : 'area', value: v, unit });
  }

  // Counts per storey or for the whole model.
  if (/how many|hvor mange|mitu/.test(q)) {
    const kind = WORDS.find(([, rx]) => rx.test(question))?.[0];
    if (!kind) return no('Unsupported element class.');
    const items = elems(kind, storey);
    return ok(items.length, `${items.length} ${TYPES[kind].join('/')} entities ${scope}.`, items.slice(0, 400).map(e => ev(m, e, kind)), { type: 'count', value: items.length, unit: kind });
  }
  return null;
}

/** ifc_models floor-plan PDFs/SVGs `<model>_plan-…` are renderings of `<model>.ifc`. */
export const ifcSiblingOf = path => path.endsWith('.ifc') ? path : path.replace(/_plan-[^/]*\.(pdf|svg)$/i, '.ifc');
