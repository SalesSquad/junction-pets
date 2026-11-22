/**
 * Bounded, dependency-free ASCII DXF evidence extractor. Geometry remains in
 * source coordinates. This is NOT an OCR/IFC/DWG engine.
 */
export const DXF_LIMITS = Object.freeze({ bytes: 6 * 1024 * 1024, groups: 300000, entities: 12000 });

export function parseDxf(input, filename = 'uploaded.dxf') {
  if (typeof input !== 'string' || new TextEncoder().encode(input).length > DXF_LIMITS.bytes) {
    throw new Error('DXF source exceeds the 6 MiB import limit.');
  }
  if (!/\.dxf$/i.test(filename)) throw new Error('Only ASCII .dxf drawings are supported.');
  if (input.includes('\0') || input.startsWith('AutoCAD Binary DXF')) {
    throw new Error('Binary DXF is not supported; export as ASCII DXF.');
  }
  const lines = input.replace(/^\uFEFF/, '').split(/\r\n|\n|\r/);
  if (lines.at(-1) === '') lines.pop();
  if (lines.length % 2) throw new Error('Incomplete DXF group pair.');
  const n = lines.length / 2;
  if (n > DXF_LIMITS.groups) throw new Error('DXF group limit reached.');
  if (n < 4) throw new Error('Not an ASCII DXF drawing.');

  const entities = [];
  let section = '', entering = false, current = null, headerVariable = '', units = 0;
  const pushEntity = () => {
    if (!current || section !== 'ENTITIES') return;
    if (entities.length >= DXF_LIMITS.entities) throw new Error('DXF entity limit reached.');
    const e = finalizeEntity(current, entities.length);
    if (e) entities.push(e);
    else if (['ROOM_OUTLINE', 'ROOM_TEXT'].includes(current.layer)) {
      throw new Error('Unsupported or incomplete entity on a room evidence layer.');
    }
    current = null;
  };
  for (let i = 0; i < n; i++) {
    const group = lines[i * 2].trim();
    const code = /^\d+$/.test(group) ? Number(group) : NaN;
    const value = lines[i * 2 + 1].trim();
    if (!Number.isInteger(code) || code < 0 || code > 1071) {
      throw new Error(`Malformed DXF group at pair ${i + 1}.`);
    }
    if (code === 0) {
      pushEntity();
      if (value === 'SECTION') { entering = true; continue; }
      if (value === 'ENDSEC') { section = ''; continue; }
      if (value === 'EOF') break;
      if (section === 'ENTITIES') current = { type: value, layer: '0', points: [], _last: null };
      continue;
    }
    if (entering && code === 2) { section = value; entering = false; continue; }
    if (section === 'HEADER') {
      if (code === 9) headerVariable = value;
      else if (headerVariable === '$INSUNITS' && code === 70) units = Number(value);
      continue;
    }
    if (section !== 'ENTITIES' || !current) continue;
    switch (code) {
      case 210: if (finite(value) !== 0) current.unsupportedGeometry = 'non-default extrusion'; break;
      case 220: if (finite(value) !== 0) current.unsupportedGeometry = 'non-default extrusion'; break;
      case 230: if (finite(value) !== 1) current.unsupportedGeometry = 'non-default extrusion'; break;
      case 91: if (current.type === 'HATCH') current.hatchLoops = Number(value); break;
      case 92: if (current.type === 'HATCH') { current.hatchBoundary = true; current.hatchPolyline = Boolean(Number(value) & 2); } break;
      case 73: if (current.type === 'HATCH') current.hatchClosed = Number(value) === 1; break;
      case 93: if (current.type === 'HATCH') current.hatchVertices = Number(value); break;
      case 97: if (current.type === 'HATCH') current.hatchBoundary = false; break;
      case 5: current.handle = value; break;
      case 8: current.layer = value.slice(0, 80); break;
      case 42: if (finite(value) !== 0) current.unsupportedGeometry = 'curved polyline (bulge)'; break;
      case 70: current.flags = Number(value); break;
      case 1: current.text = (current.text || '') + value; break;
      case 3: current.text = (current.text || '') + value; break;
      case 10:
        if ((current.type === 'LWPOLYLINE' || (current.type === 'HATCH' && current.hatchBoundary))) {
          if (current._last && current._last.y === undefined) throw new Error('DXF vertex is missing its Y coordinate.');
          current._last = { x: finite(value) };
          current.points.push(current._last);
        } else current.x = finite(value);
        break;
      case 20:
        if ((current.type === 'LWPOLYLINE' || (current.type === 'HATCH' && current.hatchBoundary))) {
          if (!current._last || current._last.y !== undefined) throw new Error('DXF vertex has an unexpected Y coordinate.');
          current._last.y = finite(value);
        }
        else current.y = finite(value);
        break;
      case 11: current.x2 = finite(value); break;
      case 21: current.y2 = finite(value); break;
      case 40: current.radius = finite(value); break;
      case 50: current.start = finite(value); break;
      case 51: current.end = finite(value); break;
    }
  }
  pushEntity();
  if (!entities.length) throw new Error('No supported geometric or text entities in this DXF.');
  const dimensions = boundsOf(entities);
  if (!dimensions || dimensions.width < 0.000001 || dimensions.height < 0.000001) {
    throw new Error('DXF has no measurable 2D extents.');
  }
  return {
    filename: filename.replace(/[\\/\u0000-\u001F]/g, '_').slice(0, 120),
    format: 'ASCII DXF',
    units,
    unitsLabel: ({ 1: 'inches', 2: 'feet', 4: 'millimeters', 5: 'centimeters', 6: 'meters' })[units] || 'unverified',
    dimensions,
    entities,
    parserVersion: 'stoa-dxf/1',
  };
}

function finite(value) {
  const n = value === '' ? NaN : Number(value);
  if (!Number.isFinite(n) || Math.abs(n) > 1e9) throw new Error('DXF has invalid or unbounded coordinates.');
  return n;
}

function finalizeEntity(raw, index) {
  const { type, layer } = raw;
  if (raw.points.some(point => point.y === undefined)) throw new Error('DXF vertex is missing its Y coordinate.');
  const common = { id: `e${index + 1}`, type, layer, handle: raw.handle ?? null };
  if (type === 'HATCH') {
    if (raw.hatchLoops !== 1 || !raw.hatchPolyline || !raw.hatchClosed || raw.points.length !== raw.hatchVertices || raw.points.length < 3 || raw.unsupportedGeometry) throw new Error('Unsupported HATCH boundary: use one closed straight polyline loop without holes.');
    return { ...common, points: raw.points, closed: true };
  }
  if (type === 'LWPOLYLINE' && raw.points.length >= 2) {
    return { ...common, points: raw.points, closed: Boolean(raw.flags & 1), ...(raw.unsupportedGeometry ? { unsupportedGeometry: raw.unsupportedGeometry } : {}) };
  }
  if (type === 'LINE' && Number.isFinite(raw.x) && Number.isFinite(raw.y) && Number.isFinite(raw.x2) && Number.isFinite(raw.y2)) {
    return { ...common, points: [{ x: raw.x, y: raw.y }, { x: raw.x2, y: raw.y2 }], closed: false };
  }
  if (['TEXT', 'MTEXT'].includes(type) && raw.text && Number.isFinite(raw.x) && Number.isFinite(raw.y)) {
    return { ...common, x: raw.x, y: raw.y, text: raw.text, ...(raw.unsupportedGeometry ? { unsupportedGeometry: raw.unsupportedGeometry } : {}) };
  }
  if (['CIRCLE', 'ARC'].includes(type) && Number.isFinite(raw.x) && Number.isFinite(raw.y) && raw.radius > 0) {
    return { ...common, x: raw.x, y: raw.y, radius: raw.radius, start: raw.start, end: raw.end };
  }
  return null;
}

function boundsOf(entities) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const add = (x, y) => {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    minX = Math.min(minX, x); minY = Math.min(minY, y);
    maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
  };
  for (const e of entities) {
    if (e.points) for (const p of e.points) add(p.x, p.y);
    else if (e.radius) { add(e.x - e.radius, e.y - e.radius); add(e.x + e.radius, e.y + e.radius); }
    else add(e.x, e.y);
  }
  if (!Number.isFinite(minX)) return null;
  return { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY };
}
