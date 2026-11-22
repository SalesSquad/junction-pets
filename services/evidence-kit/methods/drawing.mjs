import {createClaim} from '../src/claim.mjs';
import {fail, text} from '../src/json.mjs';
const area = points => {
  const origin = points[0];
  return Math.abs(points.reduce((sum, p, i) => {
    const q = points[(i + 1) % points.length];
    return sum + (p.x - origin.x) * (q.y - origin.y) - (q.x - origin.x) * (p.y - origin.y);
  }, 0)) / 2;
};
const inside = (p, points) => {
  let hit = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const a = points[i], b = points[j];
    const cross = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x);
    if (cross === 0 && p.x >= Math.min(a.x, b.x) && p.x <= Math.max(a.x, b.x) &&
      p.y >= Math.min(a.y, b.y) && p.y <= Math.max(a.y, b.y)) return false;
    if ((a.y > p.y) !== (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x) hit = !hit;
  }
  return hit;
};
function simplePolygon(points) {
  const p = [...points];
  if (p.length > 1 && p[0].x === p.at(-1).x && p[0].y === p.at(-1).y) p.pop();
  if (p.length < 3 || p.length > 1000 || area(p) <= 0) return false;
  const cross = (a, b, c) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  const on = (a, b, c) => cross(a,b,c) === 0 && c.x >= Math.min(a.x,b.x) && c.x <= Math.max(a.x,b.x) && c.y >= Math.min(a.y,b.y) && c.y <= Math.max(a.y,b.y);
  const intersects = (a,b,c,d) => (cross(a,b,c)*cross(a,b,d)<0 && cross(c,d,a)*cross(c,d,b)<0) || on(a,b,c) || on(a,b,d) || on(c,d,a) || on(c,d,b);
  for (let i = 0; i < p.length; i++) {
    const a = p[i], b = p[(i+1)%p.length];
    if (a.x === b.x && a.y === b.y) return false;
    for (let j=i+1;j<p.length;j++) {
      if (j === i+1 || (i === 0 && j === p.length-1)) continue;
      if (intersects(a,b,p[j],p[(j+1)%p.length])) return false;
    }
  }
  return true;
}
export async function measureRoom(dataset, {roomNumber, tolerance = .02}) {
  text(roomNumber, 'room number', 40);
  if (!Number.isFinite(tolerance) || tolerance <= 0 || tolerance > .02) fail('INVALID_TOLERANCE', 'Area tolerance must be in (0,0.02].');
  if (dataset.manifest().source.adapter.id !== 'ascii-dxf') fail('WRONG_ADAPTER', 'Room measurement requires the DXF adapter.');
  const entities = dataset.entities(), data = entities.map(e => e.data), factor = dataset.manifest().source.units?.toMetres;
  const spec = {method: {id: 'room-area', version: '1.1.0', parameters: {roomNumber, tolerance}},
    question: `Area of room ${roomNumber}`, status: 'abstained', level: 'unavailable', value: null, refs: [], checks: [], reason: ''};
  const abstain = reason => createClaim(dataset, {...spec, reason});
  if (!factor) return abstain('Missing or unsupported coordinate units.');
  const numbers = data.filter(e => e.layer === 'ROOM_TEXT' && e.text === roomNumber);
  if (numbers.length !== 1) return abstain('Room number is absent or ambiguous.');
  const boundaries = data.filter(e => e.layer === 'ROOM_OUTLINE');
  if (numbers[0].unsupportedGeometry || boundaries.some(e => e.unsupportedGeometry)) {
    return abstain('Room evidence uses unsupported geometry.');
  }
  const outlines = boundaries.filter(e => e.points?.length >= 3 && e.closed && inside(numbers[0], e.points));
  if (outlines.length !== 1) return abstain('No unique closed straight room boundary.');
  const outline = outlines[0];
  if (!simplePolygon(outline.points)) return abstain('Boundary is degenerate, self-intersecting or exceeds the simple-polygon work budget.');
  const labels = data.filter(e => e.layer === 'ROOM_TEXT' && typeof e.text === 'string' && /\d+(?:[.,]\d+)?\s*m(?:²|2)/i.test(e.text) && inside(e, outline.points));
  if (labels.length !== 1) return abstain('No unique source area annotation.');
  const annotation = labels[0];
  const match = /^(\d+(?:[.,]\d+)?)\s*m(?:²|2)$/i.exec(annotation.text);
  if (!match || annotation.unsupportedGeometry) return abstain('Unsupported area annotation.');
  const stated = Number(match[1].replace(',', '.')), measured = area(outline.points) * factor ** 2;
  if (!Number.isFinite(stated) || !Number.isFinite(measured) || !(stated > 0) || Math.abs(stated - measured) / stated > tolerance) return abstain('Annotation conflicts with measured polygon area.');
  return createClaim(dataset, {...spec, status: 'supported', level: 'cross_checked', value: `${stated.toFixed(2)} m²`,
    refs: [outline, numbers[0], labels[0]].map(e => dataset.ref(e.id)),
    checks: [{kind: 'area-agreement', stated, measured, tolerance}], reason: 'Closed polygon and separately cited source annotation agree within declared tolerance.'});
}
