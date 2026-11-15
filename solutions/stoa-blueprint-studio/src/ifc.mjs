/**
 * Dependency-free IFC (ISO-10303-21 STEP) reader for quantity take-off.
 * Reads only the entity types needed for spatial structure, elements and stored quantities;
 * no geometry kernel. Strings are decoded from STEP escapes (\X2\…\X0\, \X\HH, '').
 */
import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';

const KEEP = new Set([
  'IFCPROJECT', 'IFCBUILDING', 'IFCBUILDINGSTOREY', 'IFCSPACE', 'IFCRELAGGREGATES', 'IFCRELCONTAINEDINSPATIALSTRUCTURE',
  'IFCRELDEFINESBYPROPERTIES', 'IFCELEMENTQUANTITY', 'IFCQUANTITYAREA', 'IFCQUANTITYLENGTH', 'IFCQUANTITYVOLUME', 'IFCQUANTITYCOUNT',
  'IFCPROPERTYSET', 'IFCPROPERTYSINGLEVALUE', 'IFCSIUNIT', 'IFCUNITASSIGNMENT', 'IFCRELSPACEBOUNDARY',
  'IFCDOOR', 'IFCDOORSTANDARDCASE', 'IFCWINDOW', 'IFCWINDOWSTANDARDCASE', 'IFCWALL', 'IFCWALLSTANDARDCASE', 'IFCWALLELEMENTEDCASE',
  'IFCCOLUMN', 'IFCCOLUMNSTANDARDCASE', 'IFCSTAIR', 'IFCSTAIRFLIGHT', 'IFCSLAB', 'IFCSLABSTANDARDCASE', 'IFCBEAM', 'IFCROOF',
  'IFCSANITARYTERMINAL', 'IFCFLOWTERMINAL', 'IFCLIGHTFIXTURE', 'IFCBEAMSTANDARDCASE', 'IFCRELDEFINESBYTYPE', 'IFCRELFILLSELEMENT', 'IFCRELVOIDSELEMENT', 'IFCOPENINGELEMENT', 'IFCELEMENTASSEMBLY', 'IFCRAILING', 'IFCCOVERING', 'IFCFURNISHINGELEMENT', 'IFCPLATE', 'IFCMEMBER',
]);
// Geometry needed for plan areas of spaces; parsed lazily because files hold many of these.
const GEOMETRY = new Set([
  'IFCPRODUCTDEFINITIONSHAPE', 'IFCSHAPEREPRESENTATION', 'IFCEXTRUDEDAREASOLID', 'IFCARBITRARYCLOSEDPROFILEDEF',
  'IFCARBITRARYPROFILEDEFWITHVOIDS', 'IFCRECTANGLEPROFILEDEF', 'IFCPOLYLINE', 'IFCCARTESIANPOINT', 'IFCFACETEDBREP',
  'IFCCLOSEDSHELL', 'IFCFACE', 'IFCFACEOUTERBOUND', 'IFCFACEBOUND', 'IFCPOLYLOOP',
]);
function lazyEntity(id, type, body) {
  let args;
  return { id, type, get args() { return (args ??= parseArgs(body)); } };
}

export function decodeStepString(s) {
  return s.replace(/''/g, "'")
    .replace(/\\X2\\([0-9A-F]+)\\X0\\/gi, (_, hex) => String.fromCharCode(...hex.match(/.{4}/g).map(h => parseInt(h, 16))))
    .replace(/\\X\\([0-9A-F]{2})/gi, (_, h) => String.fromCharCode(parseInt(h, 16)))
    .replace(/\\S\\(.)/g, (_, c) => String.fromCharCode(c.charCodeAt(0) + 128));
}

/** Parse a STEP argument list "a,'b',(#1,#2),$,.X.,IFCLABEL('y')" into JS values. */
export function parseArgs(src) {
  let i = 0;
  const ws = () => { while (/\s/.test(src[i] ?? '') && i < src.length) i++; };
  const value = (depth = 0) => {
    if (depth > 64) throw new Error('STEP nesting limit exceeded.');
    ws();
    const c = src[i];
    if (c === "'") {
      let out = ''; i++;
      while (i < src.length) {
        if (src[i] === "'" && src[i + 1] === "'") { out += "''"; i += 2; continue; }
        if (src[i] === "'") { i++; return decodeStepString(out); }
        out += src[i++];
      }
      throw new Error('Unterminated STEP string.');
    }
    if (c === '(') {
      i++; const list = []; ws();
      if (src[i] === ')') { i++; return list; }
      while (i < src.length) {
        list.push(value(depth + 1)); ws();
        if (src[i] === ')') { i++; return list; }
        if (src[i++] !== ',') throw new Error('Malformed STEP list.');
      }
      throw new Error('Unterminated STEP list.');
    }
    if (c === '#') {
      const m = /^#(\d+)/.exec(src.slice(i));
      if (!m) throw new Error('Malformed STEP reference.');
      i += m[0].length; return { ref: Number(m[1]) };
    }
    if (c === '$' || c === '*') { i++; return null; }
    if (c === '.' && !/\d/.test(src[i + 1] ?? '')) {
      const m = /^\.([A-Z0-9_]+)\./i.exec(src.slice(i));
      if (!m) throw new Error('Malformed STEP enum.');
      i += m[0].length; return m[1] === 'T' ? true : m[1] === 'F' ? false : m[1];
    }
    const typed = /^([A-Z][A-Z0-9_]*)\(/.exec(src.slice(i));
    if (typed) {
      i += typed[0].length; const v = value(depth + 1); ws();
      if (src[i++] !== ')') throw new Error('Unterminated STEP typed value.');
      return v;
    }
    const num = /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?/.exec(src.slice(i));
    if (num) {
      i += num[0].length; const n = Number(num[0]);
      if (!Number.isFinite(n)) throw new Error('Non-finite STEP number.');
      return n;
    }
    throw new Error('Malformed STEP value.');
  };
  const out = []; ws();
  while (i < src.length) {
    out.push(value()); ws();
    if (i === src.length) break;
    if (src[i++] !== ',') throw new Error('Malformed STEP arguments.');
    ws(); if (i === src.length) throw new Error('Missing STEP argument.');
  }
  return out;
}

export const IFC_LIMITS = Object.freeze({ bytes: 16 * 1024 * 1024, entities: 100000, record: 512 * 1024 });

/** Bounded upload parser. Semicolons in quoted STEP strings are data, not record delimiters. */
export function parseIfc(input) {
  if (typeof input !== 'string' || Buffer.byteLength(input, 'latin1') > IFC_LIMITS.bytes || !input.startsWith('ISO-10303-21;')) throw new Error('Use an IFC STEP file up to 16 MiB.');
  input = input.replace(/'(?:[^']|'')*'|\/\*[\s\S]*?\*\//g, part => part.startsWith("'") ? part : ' ');
  const entities = new Map(), seen = new Set();
  let start = 0, quoted = false, schema = null, count = 0;
  for (let i = 0; i < input.length; i++) {
    if (i - start > IFC_LIMITS.record) throw new Error('IFC record limit exceeded.');
    if (input[i] === "'") {
      if (quoted && input[i + 1] === "'") { i++; continue; }
      quoted = !quoted;
    }
    if (input[i] !== ';' || quoted) continue;
    const record = input.slice(start, i).trim(); start = i + 1;
    const sm = /FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'/.exec(record); if (sm) schema = sm[1];
    const m = /^#(\d+)\s*=\s*([A-Z0-9_]+)\s*\(/.exec(record);
    if (!m) continue;
    if (++count > IFC_LIMITS.entities) throw new Error('IFC entity limit exceeded.');
    const id = Number(m[1]);
    if (seen.has(id)) throw new Error('Duplicate IFC entity ID.');
    seen.add(id);
    if (!record.endsWith(')')) throw new Error('Malformed IFC entity.');
    if (KEEP.has(m[2]) || GEOMETRY.has(m[2]) || m[2].endsWith('TYPE')) {
      const args = parseArgs(record.slice(m[0].length, -1));
      entities.set(id, { id, type: m[2], args, sourceRecord: record + ';' });
    }
  }
  if (quoted || input.slice(start).trim() || !schema || !entities.size || !input.trimEnd().endsWith('END-ISO-10303-21;')) throw new Error('Incomplete IFC STEP file.');
  return model(entities, schema);
}

export async function readIfc(path) {
  const entities = new Map();
  const rl = createInterface({ input: createReadStream(path, { encoding: 'latin1' }), crlfDelay: Infinity });
  let buf = '', schema = null;
  for await (const line of rl) {
    if (!schema) { const m = /FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'/.exec(line); if (m) schema = m[1]; }
    buf = buf ? buf + line : line;
    if (!buf.trimEnd().endsWith(';')) continue;
    const m = /^#(\d+)\s*=\s*([A-Z0-9_]+)\s*\(/.exec(buf);
    if (m && (KEEP.has(m[2]) || GEOMETRY.has(m[2]) || m[2].endsWith('TYPE'))) {
      const body = buf.slice(m[0].length, buf.lastIndexOf(')'));
      entities.set(Number(m[1]), GEOMETRY.has(m[2]) ? lazyEntity(Number(m[1]), m[2], body) : { id: Number(m[1]), type: m[2], args: parseArgs(body) });
    }
    buf = '';
  }
  return model(entities, schema);
}

/** SI prefix applies to the base metre before squaring/cubing. Unsupported units stay unknown. */
export function siUnit(u) {
  if (u?.type !== 'IFCSIUNIT') return null;
  const prefix = { MILLI: 1e-3, CENTI: 1e-2, DECI: 1e-1, KILO: 1e3 };
  const exponent = { METRE: 1, SQUARE_METRE: 2, CUBIC_METRE: 3 }[u.args[3]];
  const factor = u.args[2] == null ? 1 : prefix[u.args[2]];
  return exponent && factor ? { kind: u.args[1], prefix: u.args[2], name: u.args[3], factor: factor ** exponent } : null;
}

/** Build spatial and quantity indexes over the kept entities. */
function model(E, schema) {
  const get = r => (r && r.ref != null ? E.get(r.ref) : null);
  const of = (...types) => [...E.values()].filter(e => types.includes(e.type));
  const storeys = of('IFCBUILDINGSTOREY').map(e => ({ e, name: e.args[2], elevation: e.args[9] }));
  // Element id -> storey. Direct containment first; otherwise climb: aggregate parent, the
  // space that contains it, or (doors/windows) the wall whose opening the element fills.
  const container = new Map(), parent = new Map(), filledOpening = new Map(), openingHost = new Map();
  for (const rel of of('IFCRELCONTAINEDINSPATIALSTRUCTURE')) for (const r of rel.args[4] ?? []) container.set(r.ref, rel.args[5]?.ref);
  for (const rel of of('IFCRELAGGREGATES')) for (const r of rel.args[5] ?? []) parent.set(r.ref, rel.args[4]?.ref);
  for (const rel of of('IFCRELFILLSELEMENT')) filledOpening.set(rel.args[5]?.ref, rel.args[4]?.ref);
  for (const rel of of('IFCRELVOIDSELEMENT')) openingHost.set(rel.args[5]?.ref, rel.args[4]?.ref);
  const resolve = (id, depth = 0) => {
    if (id == null || depth > 8) return null;
    const e = E.get(id);
    if (e?.type === 'IFCBUILDINGSTOREY') return e;
    const next = container.get(id) ?? parent.get(id) ?? openingHost.get(filledOpening.get(id));
    return next == null ? null : resolve(next, depth + 1);
  };
  // Parts of another element (e.g. stair flights nested in a stair) are not separate objects.
  const SPATIAL = new Set(['IFCPROJECT', 'IFCSITE', 'IFCBUILDING', 'IFCBUILDINGSTOREY', 'IFCSPACE']);
  const isPart = new Set([...parent].filter(([, p]) => { const t = E.get(p)?.type; return t ? !SPATIAL.has(t) : true; }).map(([id]) => id));
  const storeyOf = new Map();
  for (const id of new Set([...container.keys(), ...parent.keys(), ...filledOpening.keys()])) {
    const s = resolve(id);
    if (s && s.id !== id) storeyOf.set(id, s);
  }
  const quantities = new Map(); // element id -> [{set, name, value, kind}]
  const props = new Map();      // element id -> [{set, name, value}]
  for (const rel of of('IFCRELDEFINESBYPROPERTIES')) {
    const def = get(rel.args[5]);
    if (!def) continue;
    const rows = [];
    if (def.type === 'IFCELEMENTQUANTITY') {
      for (const q of (def.args[5] ?? []).map(get).filter(Boolean)) rows.push({ set: def.args[2], name: q.args[0], value: q.args[3], kind: q.type, entityId: q.id, unitDeclared: q.args[2] != null, unit: get(q.args[2]) });
      for (const r of rel.args[4] ?? []) quantities.set(r.ref, [...(quantities.get(r.ref) ?? []), ...rows]);
    } else if (def.type === 'IFCPROPERTYSET') {
      for (const p of (def.args[4] ?? []).map(get).filter(Boolean)) if (p.type === 'IFCPROPERTYSINGLEVALUE') rows.push({ set: def.args[2], name: p.args[0], value: p.args[2], entityId: p.id });
      for (const r of rel.args[4] ?? []) props.set(r.ref, [...(props.get(r.ref) ?? []), ...rows]);
    }
  }
  // Project units come from the IfcUnitAssignment (a file may define several SI units of one kind).
  const assigned = (of('IFCUNITASSIGNMENT')[0]?.args[0] ?? []).map(get).filter(u => u?.type === 'IFCSIUNIT');
  const units = Object.fromEntries(assigned.map(u => [u.args[1], siUnit(u)]));
  // Element id -> its type object (IfcRelDefinesByType), e.g. IfcSanitaryTerminalType.
  const typeOf = new Map();
  for (const rel of of('IFCRELDEFINESBYTYPE')) { const t = get(rel.args[5]); for (const r of rel.args[4] ?? []) if (t) typeOf.set(r.ref, t); }
  const byType = new Map();
  for (const e of E.values()) if (!GEOMETRY.has(e.type)) byType.set(e.type, [...(byType.get(e.type) ?? []), e]);
  const ofFast = (...types) => types.flatMap(t => byType.get(t) ?? []);
  const lengthFactor = units.LENGTHUNIT?.factor;
  return { schema, entities: E, of: ofFast, get, storeys, storeyOf, isPart, quantities, props, units, typeOf,
    planArea: e => Number.isFinite(lengthFactor) ? planArea(E, e, lengthFactor) : null,
    project: ofFast('IFCPROJECT')[0], building: ofFast('IFCBUILDING')[0] };
}

const shoelace = pts => Math.abs(pts.reduce((s, p, i) => { const q = pts[(i + 1) % pts.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0)) / 2;

/**
 * Plan (floor) area of a product from its body geometry, in m²: extruded profile area for swept
 * solids; for faceted B-reps the downward-facing horizontal faces. null when neither is present.
 */
export function planArea(E, e, lengthFactor = 1) {
  const get = r => (r && r.ref != null ? E.get(r.ref) : null);
  const coords = pt => get(pt)?.args[0] ?? null;
  const polyArea = curve => {
    const c = get(curve);
    if (c?.type !== 'IFCPOLYLINE') return null;
    const pts = c.args[0].map(coords).filter(Boolean);
    if (pts.length > 2 && pts[0].every((v, i) => v === pts.at(-1)[i])) pts.pop();
    return pts.length >= 3 ? shoelace(pts) : null;
  };
  const profileArea = p => {
    if (!p) return null;
    if (p.type === 'IFCRECTANGLEPROFILEDEF') return p.args[3] * p.args[4];
    if (p.type === 'IFCARBITRARYCLOSEDPROFILEDEF') return polyArea(p.args[2]);
    if (p.type === 'IFCARBITRARYPROFILEDEFWITHVOIDS') {
      const outer = polyArea(p.args[2]);
      return outer == null ? null : outer - (p.args[3] ?? []).reduce((s, c) => s + (polyArea(c) ?? 0), 0);
    }
    return null;
  };
  const brepArea = b => {
    const shell = get(b.args[0]);
    let total = 0, found = false;
    for (const f of (shell?.args[0] ?? []).map(get)) {
      const bound = get(f?.args[0]?.[0]);
      const loop = get(bound?.args[0]);
      const pts = (loop?.args[0] ?? []).map(coords).filter(Boolean);
      if (pts.length < 3 || pts[0].length < 3) continue;
      // Newell normal; keep horizontal faces whose normal points down (floor side).
      let nx = 0, ny = 0, nz = 0;
      pts.forEach((p, i) => { const q = pts[(i + 1) % pts.length]; nx += (p[1] - q[1]) * (p[2] + q[2]); ny += (p[2] - q[2]) * (p[0] + q[0]); nz += (p[0] - q[0]) * (p[1] + q[1]); });
      const len = Math.hypot(nx, ny, nz) || 1;
      if (nz / len < -0.99 && bound.args[1] !== false) { total += shoelace(pts); found = true; }
    }
    return found ? total : null;
  };
  const rep = get(e.args[6]);
  for (const r of (rep?.args[2] ?? []).map(get)) {
    if (!r || (r.args[1] && !/body/i.test(r.args[1]))) continue;
    let sum = 0, any = false;
    for (const item of (r.args[3] ?? []).map(get)) {
      const a = item?.type === 'IFCEXTRUDEDAREASOLID' ? profileArea(get(item.args[0]))
        : item?.type === 'IFCFACETEDBREP' ? brepArea(item) : null;
      if (a != null) { sum += a; any = true; }
    }
    if (any) return sum * lengthFactor * lengthFactor;
  }
  return null;
}
