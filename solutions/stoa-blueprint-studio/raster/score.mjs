/** Sponsor scoring rule (preview README): counts exact; area/length/volume within 2%; text free-form. */
export function parseNumber(v) {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v !== 'string') return null;
  const m = v.replace(/ /g, ' ').match(/-?\d[\d\s]*(?:[.,]\d+)?/);
  if (!m) return null;
  let s = m[0].replace(/\s/g, '');
  // "12,5" → 12.5 ; "1,234" (thousands) stays ambiguous: treat 3-digit tail after comma as thousands.
  s = /,\d{3}$/.test(s) && !s.includes('.') ? s.replace(/,/g, '') : s.replace(',', '.');
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export function isCorrect(question, predicted) {
  const truth = question.answer;
  if (question.type === 'text') {
    return predicted != null && String(predicted).trim().toLowerCase() === String(truth).trim().toLowerCase();
  }
  const p = parseNumber(predicted), t = parseNumber(truth);
  if (p == null || t == null) return false;
  if (question.type === 'count') return Math.round(p) === p && p === t;
  return t === 0 ? p === 0 : Math.abs(p - t) / Math.abs(t) <= 0.02;
}

export function summarize(rows) {
  const by = new Map();
  for (const r of rows) {
    const k = r.template;
    const s = by.get(k) ?? { n: 0, correct: 0 };
    s.n++; s.correct += r.correct ? 1 : 0; by.set(k, s);
  }
  const n = rows.length, correct = rows.filter(r => r.correct).length;
  return { n, correct, accuracy: n ? +(correct / n).toFixed(3) : 0,
    perTemplate: Object.fromEntries([...by].sort((a, b) => b[1].n - a[1].n).map(([k, s]) => [k, `${s.correct}/${s.n}`])) };
}
