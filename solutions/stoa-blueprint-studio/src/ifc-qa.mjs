/**
 * Deterministic IFC question answering for the Stoa ifc_models templates in nine languages
 * (EN, ET, DA, NL, DE, ES, PL, RO, IT). Counts come from typed elements contained in a storey;
 * areas, lengths and volumes from the model's stored base quantities (NetFloorArea, Length,
 * NetSideArea, NetVolume), else the measured plan area of the space geometry, else an area
 * property. Every answer cites IFC entity ids (#id) and GUIDs.
 */
const TYPES = {
  door: ['IFCDOOR', 'IFCDOORSTANDARDCASE'],
  window: ['IFCWINDOW', 'IFCWINDOWSTANDARDCASE'],
  wall: ['IFCWALL', 'IFCWALLSTANDARDCASE', 'IFCWALLELEMENTEDCASE'],
  column: ['IFCCOLUMN', 'IFCCOLUMNSTANDARDCASE'],
  beam: ['IFCBEAM', 'IFCBEAMSTANDARDCASE'],
  stair: ['IFCSTAIR'],
  slab: ['IFCSLAB', 'IFCSLABSTANDARDCASE'],
  space: ['IFCSPACE'],
  sanitary: ['IFCSANITARYTERMINAL', 'IFCFLOWTERMINAL'],
  light: ['IFCLIGHTFIXTURE', 'IFCFLOWTERMINAL'],
};
const L = (...w) => new RegExp(`(^|[^\\p{L}])(${w.join('|')})($|[^\\p{L}])`, 'iu');
const WORDS = [
  ['light', /light fixtures?|corpuri de iluminat|verlichtingsarmaturen|leuchten|luminarias|lampade|oprawy|armaturer|valgusti/i],
  ['sanitary', /sanitary|sanitaire|sanitär|sanitet|sanitaar|sanitari|sanitarios|sanitarne/i],
  ['door', L('doors?', 'døre?', 'uks', 'ust', 'uksi', 'deuren', 'türen', 'puertas', 'porte', 'uși', 'usi', 'drzwi')],
  ['window', L('windows?', 'vinduer', 'vindue', 'aken', 'akent', 'akna', 'ramen', 'fenster', 'ventanas', 'finestre', 'ferestre', 'okien', 'okna')],
  ['wall', L('walls?', 'vægge?', 'sein', 'seina', 'seinu', 'wanden', 'wände', 'muros', 'muri', 'pereți', 'pereti', 'ścian', 'ściany')],
  ['column', L('columns?', 'søjler?', 'post', 'posti', 'poste', 'kolommen', 'stützen', 'pilares', 'pilastri', 'colonne', 'stâlpi', 'stalpi', 'słupów', 'słupy')],
  ['beam', L('beams?', 'bjælker?', 'tala', 'talasid', 'balken', 'träger', 'vigas', 'travi', 'grinzi', 'belek', 'belki')],
  ['stair', L('stairs?', 'staircases?', 'trapper?', 'trepp', 'treppi', 'treppe', 'trappen', 'treppen', 'escaleras', 'scale', 'scări', 'scari', 'schodów', 'schody')],
  ['space', L('rooms?', 'spaces?', 'rum', 'ruumi', 'ruume', 'ruimtes', 'räume', 'locales', 'locali', 'încăperi', 'incaperi', 'pomieszczeń', 'pomieszczen')],
];
const COUNT = /how many|hvor mange|mitu|hoeveel|wie viele|cuál es el número|qual è il numero|care este numărul|^ile /i;
const MODEL = /\b(model|modellen|mudelis|modell|modelo|modello|modelul|modelu)\b/i;
const ROOM = L('room', 'rummet', 'ruumi', 'ruimte', 'raums', 'local', 'locale', 'pomieszczenia', 'încăperii');
const AREA = /area|areal|pind|vloeroppervlakte|grundfläche|superficie|powierzchnia|suprafa/i;

// Quoted spans: '…' (closing quote must end the span), „…“ / „…”, "…", «…».
const quoted = q => [...q.matchAll(/'(.+?)'(?=[\s,?.]|$)|„([^“”]+)[“”]|"([^"]+)"|«\s*([^»]+?)\s*»/g)].map(m => m.slice(1).find(Boolean).trim());
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

/** IFC2X3 exports sanitary and light fixtures as IfcFlowTerminal; their type object tells which. */
function terminalKind(m, e) {
  if (e.type === 'IFCSANITARYTERMINAL') return 'sanitary';
  if (e.type === 'IFCLIGHTFIXTURE') return 'light';
  const t = m.typeOf?.get(e.id)?.type ?? '';
  return t.includes('SANITARY') ? 'sanitary' : t.includes('LIGHTFIXTURE') || t.includes('LAMP') ? 'light' : 'other';
}

export function answerIfc(m, question) {
  const q = question.toLowerCase();
  const [first, second] = quoted(question);
  const norm = s => String(s ?? '').trim().toLowerCase().replace(/\s+/g, ' ');
  const storeyOf = name => m.storeys.find(s => norm(s.name) === norm(name))?.e;
  // Whole-model counts use elements placed in the spatial structure; parts nested inside an
  // aggregate (e.g. stair components exported as IfcStair) are not separate objects.
  const elems = (kind, storey) => {
    let all = m.of(...TYPES[kind]).filter(e => !m.isPart?.has(e.id));
    if (kind === 'sanitary' || kind === 'light') all = all.filter(e => terminalKind(m, e) === kind);
    if (storey) return all.filter(e => m.storeyOf.get(e.id) === storey);
    const placed = all.filter(e => m.storeyOf.has(e.id));
    return placed.length ? placed : all;
  };

  // Room area: "net floor area of the room 'LongName (Number)' on 'Storey'" (any language).
  if (ROOM.test(question) && AREA.test(q) && second && !/total|samlede|kõigi|totale|gesamte|łączna|útil total/i.test(q)) {
    const storey = storeyOf(second);
    if (!storey) return no(`Storey ${second} not found.`);
    const label = norm(first);
    const cands = elems('space', storey).filter(s => {
      const name = String(s.args[2] ?? '').trim(), long = String(s.args[7] ?? '').trim();
      return [`${long} (${name})`, `${name} (${long})`, long, name].some(x => norm(x) === label);
    });
    if (cands.length !== 1) return no(`Room ${first} on ${second} is ${cands.length ? 'ambiguous' : 'absent'}.`);
    const a = spaceArea(m, cands[0]);
    if (!a) return no('The space carries no stored net floor area.');
    return ok(`${round(a.value, 2)} m²`, `Space ${first}: ${a.source}.`, [ev(m, cands[0], `IfcSpace ${first}`)], { type: 'area', value: round(a.value, 2), unit: 'm²' });
  }

  const storeyName = !MODEL.test(q) && (first || second) ? (second ?? first) : null;
  const storey = storeyName ? storeyOf(storeyName) : null;
  if (storeyName && !storey) return no(`Storey ${storeyName} not found.`);
  const scope = storey ? `on ${storeyName}` : 'in the model';

  // Totals per storey (or model) from base quantities.
  const WALLS = /walls|vægge|sein|wanden|wände|muros|muri|pereți|ścian/;
  const totals = [
    [/(net floor area|nettoareal|netopõrandapind|vloeroppervlakte|grundfläche|superficie útil total|powierzchnia netto wszystkich|suprafața)/, 'space', ['NetFloorArea'], 'm²'],
    [/(length|længde|lengte|wie lang|longitud|lunghezza|lungime|długość)/, 'wall', ['Length'], 'm', WALLS],
    [/(net side area|nettosideareal|zijoppervlakte|seitenfläche|superficie lateral|powierzchnia boczna)/, 'wall', ['NetSideArea'], 'm²'],
    [/(net volume|nettovolumen|netto volume|netto-volumen|volumen neto|volume netto|objętość)/, 'wall', ['NetVolume'], 'm³', WALLS],
    [/(net volume|nettovolumen|netto volume|netto-volumen|volumen neto|volume netto|objętość)/, 'slab', ['NetVolume'], 'm³', /slabs|dæk|plader|vloeren|decken|bodenplatten|forjados|losas|solai|plăci|stropów|plaat/],
  ];
  if (!COUNT.test(q)) for (const [rx, kind, names, unit, also] of totals) {
    if (!rx.test(q) || (also && !also.test(q))) continue;
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
  if (COUNT.test(q)) {
    const kind = WORDS.find(([, rx]) => rx.test(question))?.[0];
    if (!kind) return no('Unsupported element class.');
    const items = elems(kind, storey);
    return ok(items.length, `${items.length} ${kind} elements (${TYPES[kind].join('/')}) ${scope}.`, items.slice(0, 400).map(e => ev(m, e, kind)), { type: 'count', value: items.length, unit: kind });
  }
  return null;
}

/** ifc_models floor-plan PDFs/SVGs `<model>_plan-…` are renderings of `<model>.ifc`. */
export const ifcSiblingOf = path => path.endsWith('.ifc') ? path : path.replace(/_plan-[^/]*\.(pdf|svg)$/i, '.ifc');
