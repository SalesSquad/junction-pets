/** Original, deliberately invented fixture. Not copied from Stoa sponsor data. */
export function makeDemo() {
  let next = 0;
  const entities = [];
  const polygon = (layer, x, y, w, h) => {
    const e = { id: `e${++next}`, type: 'LWPOLYLINE', layer, closed: true,
      points: [{ x, y }, { x: x + w, y }, { x: x + w, y: y + h }, { x, y: y + h }] };
    entities.push(e);
    return e;
  };
  const text = (value, x, y) => entities.push({ id: `e${++next}`, type: 'TEXT', layer: 'ROOM_TEXT', text: value, x, y });
  const room = (name, id, x, y, w, h) => {
    polygon('ROOM_OUTLINE', x, y, w, h);
    text(name, x + w / 2, y + h / 2 + 0.7);
    text(id, x + w / 2, y + h / 2);
    text(`${(w * h).toFixed(2)} m²`, x + w / 2, y + h / 2 - 0.7);
  };
  polygon('UNIT_OUTLINE', 0, 0, 6, 8);
  polygon('UNIT_OUTLINE', 6, 0, 6, 8);
  room('Stanza', 'A-101', 0.15, 0.15, 3.7, 3.7);
  room('Cucina', 'A-102', 3.9, 0.15, 1.95, 3.7);
  room('Corridoio', 'A-103', 0.15, 4.05, 5.7, 3.8);
  room('Stanza', 'B-201', 6.15, 0.15, 3.7, 3.7);
  room('Balcone', 'B-202', 9.9, 0.15, 1.95, 3.7);
  room('Stanza', 'B-203', 6.15, 4.05, 5.7, 3.8);
  return {
    id: 'demo', filename: 'Moss Court — handmade training drawing',
    format: 'Synthetic 2D fixture', units: 6, unitsLabel: 'meters',
    dimensions: { minX: 0, minY: 0, maxX: 12, maxY: 8, width: 12, height: 8 },
    parserVersion: 'stoa-demo/1', sha256: null,
    sourceNotice: 'HANDCRAFTED DEMO · NOT VERIFIED SPONSOR DATA',
    entities,
  };
}
