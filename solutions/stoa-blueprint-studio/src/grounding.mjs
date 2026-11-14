/** Pure evidence-driven question resolver. Never synthesizes a region. */
const countIntent = /\b(how many|quanti|combien|wie viele|count|number of|montako)\b/i;
const areaIntent = /\b(area|surface|superficie|fläche|pinta-ala|m²|m2)\b/i;
const injection = /\b(ignore (?:the |all |previous )?(?:source|drawing|instructions|rules)|(?:just|always) answer \d+|override (?:the |all )?(?:evidence|instructions))\b/i;

export function polygonArea(points) {
  if (!Array.isArray(points) || points.length < 3) return 0;
  return Math.abs(points.reduce((sum, p, i) => {
    const q = points[(i + 1) % points.length];
    return sum + p.x * q.y - q.x * p.y;
  }, 0) / 2);
}

export function pointInPolygon(p, polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[i], b = polygon[j];
    if ((a.y > p.y) !== (b.y > p.y) && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

const normalize = (s) => String(s || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const cleanLabel = (s) => normalize(s).replace(/[^\p{L}\p{N}]/gu, '');
const exactMention = (question, label) => {
  const escaped = normalize(label).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(?<![\\p{L}\\p{N}])${escaped}(?![\\p{L}\\p{N}])`, 'iu').test(normalize(question));
};
const isLabel = (e) => e.layer === 'ROOM_TEXT' && /^(?:[\p{L}][\p{L}\s.-]{1,38})$/u.test(e.text) && !/^app\.?\s*[a-z]$/i.test(e.text);
const evidence = (e, detail) => ({ entityId: e.id, layer: e.layer, kind: e.type, detail });
const supportedUnits = Object.freeze({ 1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1 });

function answer(answer, explanation, drawing, sourceEntities, metric) {
  return { status: 'supported', answer, explanation, metric, evidence: sourceEntities, source: { filename: drawing.filename, sha256: drawing.sha256 || null, format: drawing.format, units: drawing.unitsLabel }, inference: 'deterministic; no external model' };
}
function abstain(reason, drawing) {
  return { status: 'abstained', answer: null, explanation: reason, metric: null, evidence: [], source: { filename: drawing.filename, sha256: drawing.sha256 || null }, inference: 'deterministic; no external model' };
}

export function answerDrawing(drawing, question) {
  if (!drawing || !Array.isArray(drawing.entities) || drawing.entities.length > 12000) throw new Error('Invalid drawing payload.');
  if (typeof question !== 'string' || question.trim().length < 4 || question.length > 400) return abstain('Ask one short question about this sheet.', drawing);
  if (injection.test(question)) return abstain('Instruction-like text is not drawing evidence. Ask a verifiable drawing question.', drawing);
  const entities = drawing.entities;
  const q = normalize(question);
  const labelTexts = entities.filter(isLabel);
  const roomOutlines = entities.filter(e => e.layer === 'ROOM_OUTLINE' && e.type === 'LWPOLYLINE' && e.closed && e.points.length >= 3);

  if (areaIntent.test(q)) {
    const roomNumber = q.match(/\b(?:[a-z]-\d+|\d+(?:[.\-]\d+){1,2})\b/i)?.[0];
    if (!roomNumber) return abstain('Specify an exact room number. A room name alone can match several regions.', drawing);
    const identifiers = entities.filter(e => e.layer === 'ROOM_TEXT' && e.text && normalize(e.text) === roomNumber);
    if (identifiers.length !== 1) return abstain('The named room is absent or not uniquely identifiable on this drawing.', drawing);
    const location = identifiers[0];
    const enclosing = roomOutlines.filter(e => pointInPolygon(location, e.points));
    if (enclosing.length !== 1) return abstain('Unable to prove a unique closed room boundary around this room number.', drawing);
    const region = enclosing[0];
    const areaLabels = entities.filter(e => e.layer === 'ROOM_TEXT' && typeof e.text === 'string' && /\b\d+(?:[.,]\d+)?\s*m(?:²|2)(?!\w)/i.test(e.text) && pointInPolygon(e, region.points));
    if (areaLabels.length !== 1) return abstain('There is no unique area annotation inside that room boundary.', drawing);
    const areaText = areaLabels[0];
    const statedArea = Number(areaText.text.match(/\d+(?:[.,]\d+)?/)[0].replace(',', '.'));
    const factor = supportedUnits[drawing.units];
    if (!factor) return abstain('DXF units are missing or unsupported; the source area cannot be checked.', drawing);
    const computedArea = polygonArea(region.points) * factor ** 2;
    if (statedArea <= 0 || Math.abs(computedArea - statedArea) / statedArea > 0.02) {
      return abstain('The labeled area does not agree with the closed source polygon within 2%; review scale or geometry.', drawing);
    }
    const number = Number(statedArea.toFixed(2));
    return answer(`${number.toFixed(2)} m²`, `Room ${location.text}: the area annotation and measured closed polygon agree (computed ${computedArea.toFixed(2)} m²). Select the citation to inspect the exact boundary and both labels.`, drawing, [evidence(region, 'Measured closed room outline'), evidence(location, `Room identifier ${location.text}`), evidence(areaText, `Source area label ${areaText.text}`)], { type: 'area', value: number, unit: 'm²', tolerancePercent: 2 });
  }

  if (countIntent.test(q)) {
    if (/\b(apartments?|residential units?|appartamenti|wohnungen|unit[aà] abitative)\b/i.test(q)) {
      const units = entities.filter(e => e.layer === 'UNIT_OUTLINE');
      if (!units.length) return abstain('No distinct unit-outline entities are available; text labels alone are insufficient.', drawing);
      const validRing = e => {
        if (e.type !== 'LWPOLYLINE' || !Array.isArray(e.points) || e.points.length < 3) return false;
        const first = e.points[0], last = e.points[e.points.length - 1];
        const endpointsClose = Math.hypot(first.x - last.x, first.y - last.y) <= 1e-6;
        return (e.closed || endpointsClose) && polygonArea(e.points) > 1e-8;
      };
      if (!units.every(validRing)) return abstain('At least one UNIT_OUTLINE is not a provably closed, positive-area region; apartment count is unsafe.', drawing);
      return answer(String(units.length), `${units.length} separate, closed, positive-area UNIT_OUTLINE source geometries occur in this drawing. Each ring is highlighted; no apartment is inferred from open strokes.`, drawing, units.map(e => evidence(e, 'Closed source apartment/unit ring')), { type: 'count', value: units.length, unit: 'apartments' });
    }
    if (/\b(doors?|windows?|walls?|stairs?|columns?|fixtures?|beams?)\b/i.test(q)) {
      return abstain('This source contains primitives, not independently validated instances of that object class.', drawing);
    }
    const labels = new Map();
    for (const e of labelTexts) {
      const label = cleanLabel(e.text);
      if (label.length > 1) labels.set(label, e.text);
    }
    const mentions = [...labels].filter(([label, original]) => label.length >= 3 && exactMention(question, original));
    if (mentions.length > 1) return abstain('Name exactly one room label at a time; this question refers to multiple classes.', drawing);
    if (mentions.length === 1) {
      const target = mentions[0][0];
      const hits = labelTexts.filter(e => cleanLabel(e.text) === target);
      return answer(String(hits.length), `${hits.length} exact ROOM_TEXT labels reading “${labels.get(target)}” occur in this drawing. Each numbered marker is linked to its original DXF text insertion point.`, drawing, hits.map(e => evidence(e, `ROOM_TEXT: ${e.text}`)), { type: 'count', value: hits.length, unit: labels.get(target) });
    }
    return abstain('Cannot establish a traceable count for that object class. Door arcs, window segments and wall strokes are not one-to-one objects.', drawing);
  }
  return abstain('This question has no supported measurement method or unambiguous cited source region yet.', drawing);
}
