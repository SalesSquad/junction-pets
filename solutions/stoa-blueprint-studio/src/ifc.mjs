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
  'IFCSANITARYTERMINAL', 'IFCFLOWTERMINAL', 'IFCRAILING', 'IFCCOVERING', 'IFCFURNISHINGELEMENT', 'IFCPLATE', 'IFCMEMBER',
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
  const value = () => {
    while (src[i] === ' ') i++;
    const c = src[i];
    if (c === "'") {
      let j = i + 1, out = '';
      while (j < src.length) {
        if (src[j] === "'" && src[j + 1] === "'") { out += "''"; j += 2; continue; }
        if (src[j] === "'") break;
        out += src[j++];
      }
      i = j + 1;
      return decodeStepString(out);
    }
    if (c === '(') { i++; const list = []; while (src[i] !== ')') { list.push(value()); if (src[i] === ',') i++; } i++; return list; }
    if (c === '#') { const m = /^#(\d+)/.exec(src.slice(i)); i += m[0].length; return { ref: Number(m[1]) }; }
    if (c === '$' || c === '*') { i++; return null; }
    if (c === '.') { const j = src.indexOf('.', i + 1); const v = src.slice(i + 1, j); i = j + 1; return v === 'T' ? true : v === 'F' ? false : v; }
    const typed = /^([A-Z0-9_]+)\(/.exec(src.slice(i));
    if (typed) { i += typed[0].length; const v = value(); while (src[i] !== ')') i++; i++; return v; }
    const num = /^[-+0-9.Ee]+/.exec(src.slice(i));
    if (num) { i += num[0].length; return Number(num[0]); }
    throw new Error(`STEP parse error near: ${src.slice(i, i + 30)}`);
  };
  const out = [];
  while (i < src.length) { out.push(value()); while (src[i] === ' ') i++; if (src[i] === ',') i++; else break; }
  return out;
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
    if (m && (KEEP.has(m[2]) || GEOMETRY.has(m[2]))) {
      const body = buf.slice(m[0].length, buf.lastIndexOf(')'));
      entities.set(Number(m[1]), GEOMETRY.has(m[2]) ? lazyEntity(Number(m[1]), m[2], body) : { id: Number(m[1]), type: m[2], args: parseArgs(body) });
    }
    buf = '';
  }
  return model(entities, schema);
}

/** Build spatial and quantity indexes over the kept entities. */
function model(E, schema) {
  const get = r => (r && r.ref != null ? E.get(r.ref) : null);
  const of = (...types) => [...E.values()].filter(e => types.includes(e.type));
  const storeys = of('IFCBUILDINGSTOREY').map(e => ({ e, name: e.args[2], elevation: e.args[9] }));
  const storeyOf = new Map(); // element id -> storey entity
  for (const rel of of('IFCRELCONTAINEDINSPATIALSTRUCTURE')) {
    const host = get(rel.args[5]);
    for (const r of rel.args[4] ?? []) storeyOf.set(r.ref, host);
  }
  for (const rel of of('IFCRELAGGREGATES')) {
    const host = get(rel.args[4]);
    if (host?.type !== 'IFCBUILDINGSTOREY') continue;
    for (const r of rel.args[5] ?? []) storeyOf.set(r.ref, host);
  }
  const quantities = new Map(); // element id -> [{set, name, value, kind}]
  const props = new Map();      // element id -> [{set, name, value}]
  for (const rel of of('IFCRELDEFINESBYPROPERTIES')) {
    const def = get(rel.args[5]);
    if (!def) continue;
    const rows = [];
    if (def.type === 'IFCELEMENTQUANTITY') {
      for (const q of (def.args[5] ?? []).map(get).filter(Boolean)) rows.push({ set: def.args[2], name: q.args[0], value: q.args[3], kind: q.type });
      for (const r of rel.args[4] ?? []) quantities.set(r.ref, [...(quantities.get(r.ref) ?? []), ...rows]);
    } else if (def.type === 'IFCPROPERTYSET') {
      for (const p of (def.args[4] ?? []).map(get).filter(Boolean)) if (p.type === 'IFCPROPERTYSINGLEVALUE') rows.push({ set: def.args[2], name: p.args[0], value: p.args[2] });
      for (const r of rel.args[4] ?? []) props.set(r.ref, [...(props.get(r.ref) ?? []), ...rows]);
    }
  }
  // Project units come from the IfcUnitAssignment (a file may define several SI units of one kind).
  const assigned = (of('IFCUNITASSIGNMENT')[0]?.args[0] ?? []).map(get).filter(u => u?.type === 'IFCSIUNIT');
  const PREFIX = { MILLI: 1e-3, CENTI: 1e-2, DECI: 1e-1, KILO: 1e3 };
  const units = Object.fromEntries(assigned.map(u => [u.args[1], { prefix: u.args[2], name: u.args[3], factor: PREFIX[u.args[2]] ?? 1 }]));
  const byType = new Map();
  for (const e of E.values()) if (!GEOMETRY.has(e.type)) byType.set(e.type, [...(byType.get(e.type) ?? []), e]);
  const ofFast = (...types) => types.flatMap(t => byType.get(t) ?? []);
  const lengthFactor = units.LENGTHUNIT?.factor ?? 1;
  return { schema, entities: E, of: ofFast, get, storeys, storeyOf, quantities, props, units,
    planArea: e => planArea(E, e, lengthFactor),
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
