// SAMA deck: data loading, provenance and SVG chart builders.
// Every number placed on a slide goes through val()/kn() so it is recorded with its file and path
// in numbers.json. Charts are built from the same values. No number is typed by hand here.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

export const ROOT = resolve(new URL('../..', import.meta.url).pathname);
const cache = new Map();
export function load(file) {
  if (!cache.has(file)) cache.set(file, JSON.parse(readFileSync(resolve(ROOT, file), 'utf8')));
  return cache.get(file);
}
export function rawText(file) { return readFileSync(resolve(ROOT, file), 'utf8'); }

export const ledger = [];
// get(file, 'a.b[3].c') with a check that the value exists.
export function get(file, path) {
  let o = load(file);
  for (const part of (Array.isArray(path) ? path : path.match(/[^.[\]]+/g))) {
    if (o == null || !(part in Object(o))) throw new Error(`missing ${file} :: ${path} (at ${part})`);
    o = o[part];
  }
  return o;
}
export function val(file, path, fmt = (x) => String(x)) {
  const v = get(file, path);
  ledger.push({ file, path, value: v });
  return fmt(v);
}
// A number that appears only inside a source's text field: assert it is there, then record it.
export function inText(file, path, re, group = 1) {
  const s = get(file, path);
  const m = String(s).match(re);
  if (!m) throw new Error(`pattern ${re} not in ${file} :: ${path}`);
  ledger.push({ file, path, value: m[group], from: 'text' });
  return m[group];
}
export const find = (arr, pred, what) => { const r = arr.find(pred); if (!r) throw new Error(`not found: ${what}`); return r; };
export const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
export const nf = (x, d = 0) => Number(x).toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d });
export const pct = (x, d = 1) => `${nf(x * 100, d)}%`;

// ------------------------------------------------------------------ palette (validated: #B8213F,#2C6FAE pass all six checks)
export const C = {
  ink: '#13202A', ink2: '#4A5862', muted: '#7A868F', rule: '#DCE2E6', grid: '#E7ECEF',
  paper: '#FFFFFF', panel: '#F1F4F5', spruce: '#17463F',
  lake: '#2C6FAE', lakeWash: 'rgba(44,111,174,0.10)', lingon: '#B8213F', lingonWash: 'rgba(184,33,63,0.10)',
  neutral: '#AEB8BF', amber: '#D08A00',
};
const F = { body: "Seravek, 'Avenir Next', sans-serif", num: "'DIN Alternate', 'Avenir Next Condensed', sans-serif", cond: "'Avenir Next Condensed', 'Avenir Next', sans-serif" };
const t = (x, y, s, o = {}) => `<text x="${x}" y="${y}" font-family="${o.ff || F.body}" font-size="${o.fs || 14}" font-weight="${o.fw || 400}" fill="${o.fill || C.ink}"${o.anchor ? ` text-anchor="${o.anchor}"` : ''}${o.ls ? ` letter-spacing="${o.ls}"` : ''}${o.extra || ''}>${s}</text>`;
const svg = (w, h, body, label) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${esc(label)}">${body}</svg>`;
// bar with 4px rounded data end, square at baseline (horizontal)
const hbar = (x, y, w, h, fill, r = 4) => {
  if (w <= 0) return '';
  const rr = Math.min(r, w, h / 2);
  return `<path d="M${x},${y} h${w - rr} a${rr},${rr} 0 0 1 ${rr},${rr} v${h - 2 * rr} a${rr},${rr} 0 0 1 -${rr},${rr} h-${w - rr} z" fill="${fill}"/>`;
};
const hatchDef = (id, color) => `<pattern id="${id}" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)"><rect width="6" height="6" fill="${color}" opacity="0.18"/><line x1="0" y1="0" x2="0" y2="6" stroke="${color}" stroke-width="2.2"/></pattern>`;

// ------------------------------------------------------------------ 1. the unequal equals sign (title signature)
export function equalsMark(bench, fin) {
  const W = 560, H = 230, x0 = 0, max = 34, sc = (v) => (v / max) * W, bh = 56;
  return svg(W, H, [
    hbar(x0, 20, sc(bench), bh, C.ink, 6),
    hbar(x0, 20 + bh + 34, sc(fin), bh, C.lingon, 6),
    t(sc(bench) - 14, 20 + bh / 2 + 12, `${bench}%`, { ff: F.num, fs: 34, fw: 700, fill: '#fff', anchor: 'end' }),
    t(sc(fin) + 14, 20 + bh + 34 + bh / 2 + 12, `${fin}%`, { ff: F.num, fs: 34, fw: 700, fill: C.lingon }),
    t(0, 12, 'SWEDEN AND NORWAY, AVERAGE', { fs: 11.5, fw: 600, fill: C.ink2, ls: 1.2 }),
    t(0, 20 + bh + 26, 'FINLAND', { fs: 11.5, fw: 600, fill: C.lingon, ls: 1.2 }),
    t(0, H - 6, 'Five-year relative survival, lung cancer, men, 2020-2024 (NORDCAN)', { fs: 13, fill: C.ink2 }),
  ].join(''), 'Two bars that should be equal: lung cancer five-year survival for men, Sweden and Norway against Finland');
}

// ------------------------------------------------------------------ 2. survival history, Finland vs Sweden-Norway
export function historyChart(hist) {
  const W = 700, H = 396, m = { l: 46, r: 120, t: 20, b: 56 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b, ymax = 35;
  const X = (i) => m.l + (i / (hist.length - 1)) * iw, Y = (v) => m.t + ih - (v / ymax) * ih;
  const grid = [0, 10, 20, 30].map((v) => `<line x1="${m.l}" x2="${m.l + iw}" y1="${Y(v)}" y2="${Y(v)}" stroke="${C.grid}" stroke-width="1"/>${t(m.l - 10, Y(v) + 5, `${v}%`, { fs: 13, fill: C.muted, anchor: 'end' })}`).join('');
  const line = (k, col) => `<path d="${hist.map((h, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(h[k]).toFixed(1)}`).join('')}" fill="none" stroke="${col}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`;
  const dots = (k, col) => hist.map((h, i) => `<circle cx="${X(i)}" cy="${Y(h[k])}" r="4.5" fill="${col}" stroke="#fff" stroke-width="2"/>`).join('');
  const xl = hist.map((h, i) => (i % 2 === 0 || i === hist.length - 1) ? t(X(i), m.t + ih + 26, h.period.slice(0, 4), { fs: 13, fill: C.muted, anchor: 'middle' }) : '').join('');
  const last = hist[hist.length - 1], li = hist.length - 1;
  const gapBand = `<path d="${hist.map((h, i) => `${i ? 'L' : 'M'}${X(i)},${Y(h.benchmark)}`).join('')}${[...hist].reverse().map((h, j) => `L${X(hist.length - 1 - j)},${Y(h.finland)}`).join('')}Z" fill="${C.lingonWash}"/>`;
  return svg(W, H, [grid, gapBand, line('benchmark', C.ink), line('finland', C.lingon), dots('benchmark', C.ink), dots('finland', C.lingon), xl,
    t(X(li) + 12, Y(last.benchmark) + 6, 'Sweden and', { fs: 14, fw: 600, fill: C.ink }), t(X(li) + 12, Y(last.benchmark) + 23, 'Norway', { fs: 14, fw: 600, fill: C.ink }),
    t(X(li) + 12, Y(last.finland) + 6, 'Finland', { fs: 14, fw: 600, fill: C.lingon === C.lingon ? C.ink : C.ink }),
    `<line x1="${X(li) + 8}" x2="${X(li) + 8}" y1="${Y(last.benchmark)}" y2="${Y(last.finland)}" stroke="${C.ink2}" stroke-width="1"/>`,
    t(X(li) + 12, (Y(last.benchmark) + Y(last.finland)) / 2 + 22, `gap ${nf(last.benchmark - last.finland, 1)} pts`, { fs: 13, fill: C.ink2 }),
    t(m.l, H - 6, 'Five-year period of diagnosis, start year', { fs: 12, fill: C.muted }),
  ].join(''), 'Line chart: lung cancer five-year survival, men, Finland against the Sweden-Norway average, 1980 to 2024');
}

// ------------------------------------------------------------------ 3. dumbbell: the group left behind vs the comparison group
export function dumbbell(rows) {
  const W = 700, rowH = 46, m = { l: 300, r: 40, t: 34, b: 34 }, H = m.t + rows.length * rowH + m.b;
  const lo = 40, hi = 90, iw = W - m.l - m.r, X = (v) => m.l + ((v - lo) / (hi - lo)) * iw;
  const grid = [40, 50, 60, 70, 80, 90].map((v) => `<line x1="${X(v)}" x2="${X(v)}" y1="${m.t - 8}" y2="${H - m.b + 4}" stroke="${C.grid}"/>${t(X(v), H - m.b + 22, `${v}%`, { fs: 12.5, fill: C.muted, anchor: 'middle' })}`).join('');
  const body = rows.map((r, i) => {
    const y = m.t + i * rowH + rowH / 2;
    return [r.group ? `<line x1="0" x2="${W}" y1="${y - rowH / 2}" y2="${y - rowH / 2}" stroke="${C.rule}"/>` : '',
      t(0, y - 2, esc(r.label), { fs: 15, fw: 600 }), t(0, y + 15, esc(r.sub), { fs: 12.5, fill: C.ink2 }),
      `<line x1="${X(r.low)}" x2="${X(r.high)}" y1="${y}" y2="${y}" stroke="${C.neutral}" stroke-width="3"/>`,
      `<circle cx="${X(r.low)}" cy="${y}" r="8" fill="${C.lingon}" stroke="#fff" stroke-width="2"/>`,
      `<circle cx="${X(r.high)}" cy="${y}" r="8" fill="${C.lake}" stroke="#fff" stroke-width="2"/>`,
      t(X(r.low) - 13, y + 5, `${r.low}`, { ff: F.num, fs: 16, fw: 700, anchor: 'end' }),
      t(X(r.high) + 13, y + 5, `${r.high}`, { ff: F.num, fs: 16, fw: 700 }),
    ].join('');
  }).join('');
  const legend = `<circle cx="7" cy="12" r="7" fill="${C.lingon}"/>${t(19, 17, 'Lower education / other mother tongue', { fs: 13, fill: C.ink2 })}<circle cx="${m.l + 8}" cy="12" r="7" fill="${C.lake}"/>${t(m.l + 20, 17, 'Higher education / Finnish, Swedish or Sámi', { fs: 13, fill: C.ink2, anchor: 'start' })}`;
  return svg(W, H, grid + body + legend, 'Dumbbell chart: survival and screening participation by education and mother tongue');
}

// ------------------------------------------------------------------ 3b. route medians (days)
export function routeBars(pub, fast, nPub, nFast) {
  const W = 360, H = 170, x0 = 0, max = 140, sc = (v) => (v / max) * (W - 70), bh = 26;
  return svg(W, H, [
    t(0, 16, 'Public health-centre appointment first', { fs: 13.5, fw: 600 }), t(0, 32, `${nPub} patients`, { fs: 12, fill: C.ink2 }),
    hbar(x0, 40, sc(pub), bh, C.lingon), t(sc(pub) + 8, 40 + bh / 2 + 7, `${pub} days`, { ff: F.num, fs: 19, fw: 700 }),
    t(0, 100, 'Private or occupational care first', { fs: 13.5, fw: 600 }), t(0, 116, `${nFast} patients`, { fs: 12, fill: C.ink2 }),
    hbar(x0, 124, sc(fast), bh, C.lake), t(sc(fast) + 8, 124 + bh / 2 + 7, `${fast} days`, { ff: F.num, fs: 19, fw: 700 }),
  ].join(''), 'Median days from first symptom to treatment by entry route');
}

// ------------------------------------------------------------------ 4. the law vs the reported target, on one day axis
export function lawTimeline(marks) {
  const W = 1150, H = 210, m = { l: 20, r: 30 }, max = 190, X = (d) => m.l + (d / max) * (W - m.l - m.r), y = 120;
  const near = (d) => marks.some((mk) => !mk.up && Math.abs(mk.days - d) < 8);
  const ticks = [0, 30, 60, 90, 120, 150, 180].map((d) => `<line x1="${X(d)}" x2="${X(d)}" y1="${y - 5}" y2="${y + 5}" stroke="${C.muted}"/>${near(d) ? '' : t(X(d), y + 26, d === 0 ? 'referral' : `day ${d}`, { fs: 12.5, fill: C.muted, anchor: 'middle' })}`).join('');
  const body = marks.map((mk, i) => {
    const x = X(mk.days), up = mk.up;
    const col = mk.kind === 'target' ? C.lingon : C.ink;
    const ly = up ? y - 60 : y + 64;
    return `<line x1="${x}" x2="${x}" y1="${up ? y - 46 : y + 34}" y2="${y}" stroke="${col}" stroke-width="1.5"/><circle cx="${x}" cy="${y}" r="${mk.kind === 'target' ? 9 : 7}" fill="${col}" stroke="#fff" stroke-width="2"/>`
      + t(x + (mk.anchor === 'end' ? 0 : 0), ly - (up ? 16 : 0), esc(mk.big), { ff: F.num, fs: 22, fw: 700, fill: col, anchor: mk.anchor || 'middle' })
      + t(x, ly + (up ? 4 : 20), esc(mk.text), { fs: 13, fill: C.ink2, anchor: mk.anchor || 'middle' });
  }).join('');
  return svg(W, H, `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}" stroke="${C.ink}" stroke-width="2"/>${ticks}${body}`, 'Timeline in days from referral: the legal limits against the OECD/EU-reported six-week target; the six-month treatment limit is counted from the date the need is established');
}

// ------------------------------------------------------------------ 5. how many counties could see a 20% slowdown (23 cells)
export function reachGrid(rows, total) {
  const cell = 22, gap = 4, W = 23 * (cell + gap) + 150, H = rows.length * 46 + 6;
  return svg(W, H, rows.map((r, i) => {
    const y = i * 46 + 4;
    return Array.from({ length: total }, (_, k) => `<rect x="${150 + k * (cell + gap)}" y="${y}" width="${cell}" height="${cell}" rx="3" fill="${k < r.k ? C.lake : C.panel}" stroke="${k < r.k ? 'none' : C.rule}"/>`).join('')
      + t(0, y + 16, esc(r.label), { fs: 14, fw: 600 }) + t(150 + total * (cell + gap) - gap, y + cell + 16, `${r.k} of ${total}`, { ff: F.num, fs: 15, fw: 700, anchor: 'end' });
  }).join(''), 'Grid of 23 areas: how many could see a 20% slowdown within a quarter and within a year');
}

// ------------------------------------------------------------------ 6. the comparability gate: two small multiples, one dot per county
// x = the county's rank by error (sorted), y = median error in days (shared axis, clipped), band = comparable limit.
export function gateStrip(arms, lim) {
  const W = 760, H = 370, m = { l: 44, t: 84, b: 34 }, gapP = 36, pw = (W - m.l - gapP) / arms.length - 4, ih = H - m.t - m.b;
  const lo = -36, hi = 36, Y = (v) => m.t + ((hi - Math.max(lo, Math.min(hi, v))) / (hi - lo)) * ih, r = 6;
  const yTicks = [-30, -20, -10, 0, 10, 20, 30];
  const axis = yTicks.map((v) => t(m.l - 8, Y(v) + 4.5, v > 0 ? `+${v}` : `${v}`, { fs: 12, fill: C.muted, anchor: 'end' })).join('')
    + `<text x="12" y="${m.t + ih / 2}" font-family="${F.body}" font-size="12" fill="${C.muted}" text-anchor="middle" transform="rotate(-90 12 ${m.t + ih / 2})">error, days</text>`;
  const panels = arms.map((a, i) => {
    const px = m.l + i * (pw + gapP), X = (k) => px + 8 + (k / (a.points.length - 1)) * (pw - 16);
    const grid = yTicks.map((v) => `<line x1="${px}" x2="${px + pw}" y1="${Y(v)}" y2="${Y(v)}" stroke="${v === 0 ? C.neutral : C.grid}" stroke-width="1"/>`).join('');
    const band = `<rect x="${px}" y="${Y(lim)}" width="${pw}" height="${Y(-lim) - Y(lim)}" fill="${C.lakeWash}"/>`;
    const pts = [...a.points].sort((p, q) => p.bias - q.bias).map((p, k) => {
      const x = X(k), y = Y(p.bias), clipped = p.bias < lo || p.bias > hi;
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}" fill="${p.comparable ? C.lake : C.lingon}" stroke="#fff" stroke-width="1.5"/>`
        + (clipped ? t(x + 9, y + 4, `${p.bias > 0 ? '+' : '−'}${Math.abs(p.bias)} (off scale)`, { fs: 11.5, fill: C.ink2 }) : '');
    }).join('');
    const head = t(px, 18, esc(a.label), { fs: 16, fw: 700 }) + t(px, 37, esc(a.sub), { fs: 12.5, fill: C.ink2 })
      + t(px, 62, `${a.nc} of ${a.of} not comparable`, { ff: F.num, fs: 19, fw: 700, fill: a.nc > 1 ? C.lingon : C.ink });
    return head + band + grid + pts + t(px + pw / 2, H - 10, 'counties, sorted by error', { fs: 12, fill: C.muted, anchor: 'middle' });
  }).join('');
  const bandLab = t(m.l + 6, Y(lim) - 6, `band: comparable, within ±${lim} days`, { fs: 11.5, fill: C.ink2 });
  return svg(W, H, axis + panels + bandLab, 'Two panels, one dot per simulated county sorted by error: the median error of its referral-to-treatment interval when the model writes dates itself and when code computes them');
}

// ------------------------------------------------------------------ 7. unit chart: open loops and the overdue ones
export function unitChart(total, imagingOverdue, referralOverdue) {
  total = Number(total); imagingOverdue = Number(imagingOverdue); referralOverdue = Number(referralOverdue);
  const cols = 20, cell = 20, gap = 4, rows = Math.ceil(total / cols), W = cols * (cell + gap), H = rows * (cell + gap) + 2;
  const cells = Array.from({ length: total }, (_, k) => {
    const x = (k % cols) * (cell + gap), y = Math.floor(k / cols) * (cell + gap);
    const kind = k < imagingOverdue ? 'img' : k < imagingOverdue + referralOverdue ? 'ref' : 'open';
    const fill = kind === 'img' ? C.lingon : kind === 'ref' ? 'url(#hatchL)' : C.panel;
    return `<rect x="${x}" y="${y}" width="${cell}" height="${cell}" rx="3" fill="${fill}" stroke="${kind === 'open' ? C.rule : kind === 'ref' ? C.lingon : 'none'}" stroke-width="${kind === 'ref' ? 1.5 : 1}"/>`;
  }).join('');
  return svg(W, H, `<defs>${hatchDef('hatchL', C.lingon)}</defs>${cells}`, `${total} open loops, ${imagingOverdue + referralOverdue} overdue`);
}

// ------------------------------------------------------------------ 8. stress set by system: two small multiples, one series each
export function stressPanels(systems, W = 1152) {
  const rowH = 44, m = { l: 430, t: 48, b: 6 }, H = m.t + systems.length * rowH + m.b, gapP = 70, pw = (W - m.l - gapP - 60) / 2;
  const panel = (px, key, nKey, title, sub) => {
    const sc = (v) => v * pw;
    const head = t(px, 16, esc(title), { fs: 15, fw: 700 }) + t(px, 34, esc(sub), { fs: 12.5, fill: C.ink2 });
    const grid = [0, 0.5, 1].map((v) => `<line x1="${px + sc(v)}" x2="${px + sc(v)}" y1="${m.t - 6}" y2="${H - m.b}" stroke="${C.grid}"/>`).join('')
      + t(px + sc(1), H - m.b - 2 - systems.length * rowH + 0, '', {});
    const bars = systems.map((s, i) => {
      const y = m.t + i * rowH + 7, v = s[key] / s[nKey], bh = 24;
      const fill = s.optimistic ? 'url(#hatchB)' : C.lake;
      return hbar(px, y, Math.max(sc(v), s[key] === 0 ? 0 : 2), bh, fill)
        + (s[key] === 0 ? `<line x1="${px}" x2="${px}" y1="${y}" y2="${y + bh}" stroke="${C.lake}" stroke-width="2"/>` : '')
        + t(px + sc(v) + 8, y + 18, `${s[key]}`, { ff: F.num, fs: 19, fw: 700 });
    }).join('');
    return head + grid + bars;
  };
  const labels = systems.map((s, i) => {
    const y = m.t + i * rowH + 7;
    return t(0, y + 10, esc(s.label), { fs: 15, fw: 600 }) + t(0, y + 27, esc(s.sub), { fs: 12.5, fill: C.ink2 });
  }).join('');
  return svg(W, H, `<defs>${hatchDef('hatchB', C.lake)}</defs>` + labels
    + panel(m.l, 'k', 'n', `All ${systems[0].n} stress notes`, 'whole note exactly right')
    + panel(m.l + pw + gapP, 'hk', 'hn', `${systems[0].hn} notes with new phrasings`, 'phrasings no model was trained on'),
  'Exact match by system on the frozen synthetic stress set, all notes and notes with new phrasings');
}

// ------------------------------------------------------------------ 9. two-reader agreement: 100% stacked bars
export function cascadeBars(rows, W = 640) {
  const m = { l: 170, r: 6, t: 34 }, rowH = 66, H = m.t + rows.length * rowH, iw = W - m.l - m.r, bh = 30;
  const legend = [[C.lake, 'Pre-filled, correct'], [C.lingon, 'Pre-filled, wrong'], [C.neutral, 'Needs editing']]
    .map(([c, l], i) => `<rect x="${m.l + i * 150}" y="4" width="14" height="14" rx="3" fill="${c}"/>${t(m.l + i * 150 + 20, 16, l, { fs: 13, fill: C.ink2 })}`).join('');
  const body = rows.map((r, i) => {
    const y = m.t + i * rowH + 4, segs = [[r.ok, C.lake], [r.wrong, C.lingon], [r.edit, C.neutral]];
    let x = m.l; const out = [];
    segs.forEach(([v, c], j) => {
      const w = (v / r.n) * iw - (j < 2 ? 2 : 0);
      out.push(j === 2 ? hbar(x, y, Math.max(w, 0), bh, c) : `<rect x="${x}" y="${y}" width="${Math.max(w, 2)}" height="${bh}" fill="${c}"/>`);
      x += Math.max(w, 2) + 2;
    });
    return out.join('') + t(m.l + 10, y + 21, `${r.prefilled} of ${r.n} pre-filled`, { ff: F.num, fs: 17, fw: 700, fill: '#fff' })
      + t(W - m.r, y + bh + 17, `${r.wrong} wrong among pre-filled · ${r.edit} need editing`, { fs: 13, fw: 600, fill: C.ink, anchor: 'end' })
      + t(0, y + 13, esc(r.label), { fs: 14.5, fw: 600 }) + t(0, y + 30, esc(r.sub), { fs: 12, fill: C.ink2 });
  }).join('');
  return svg(W, H, legend + body, 'Two-reader agreement: share of notes pre-filled for one-click confirmation, wrong among them, and needing editing');
}

// ------------------------------------------------------------------ 10. Helsinki pre-booked times
export function slope(before, after) {
  const W = 400, H = 260, m = { l: 34, r: 30, t: 44, b: 50 }, lo = 55, hi = 78, ih = H - m.t - m.b;
  const Y = (v) => m.t + ih - ((v - lo) / (hi - lo)) * ih, xs = [m.l + 30, m.l + 170, m.l + 310];
  const pts = [[xs[0], before, `${before}%`, 'Pre-booked time'], [xs[1], after, `about ${after}%`, 'Times removed'], [xs[2], before, 'back to the original level', 'Times returned']];
  return svg(W, H, [
    `<path d="M${xs[0]},${Y(before)} L${xs[1]},${Y(after)} L${xs[2]},${Y(before)}" fill="none" stroke="${C.lake}" stroke-width="2.5" stroke-dasharray="0"/>`,
    ...pts.map(([x, v, lab, cap], i) => `<circle cx="${x}" cy="${Y(v)}" r="7" fill="${i === 1 ? C.lingon : C.lake}" stroke="#fff" stroke-width="2"/>`
      + (i === 2 ? t(x, Y(v) - 32, 'back to the', { fs: 13.5, fw: 700, anchor: 'middle' }) + t(x, Y(v) - 14, 'original level', { fs: 13.5, fw: 700, anchor: 'middle' })
        : t(x, Y(v) + (i === 1 ? 28 : -14), lab, { ff: F.num, fs: 20, fw: 700, anchor: 'middle' }))
      + t(x, H - 18, cap, { fs: 12.5, fill: C.ink2, anchor: 'middle' })),
  ].join(''), 'Helsinki cervical screening participation when pre-booked appointment times were removed and returned');
}

// ------------------------------------------------------------------ 11. map of Finland, one area highlighted
export function finlandMap(geo, highlightId, W = 300, H = 520) {
  const lat0 = 64.5 * Math.PI / 180, kx = Math.cos(lat0);
  let minx = 1e9, maxx = -1e9, miny = 1e9, maxy = -1e9;
  const each = (f, cb) => { const g = f.geometry; const polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates; polys.forEach((p) => p.forEach((ring) => ring.forEach(cb))); };
  geo.features.forEach((f) => each(f, ([lo, la]) => { const x = lo * kx, y = -la; minx = Math.min(minx, x); maxx = Math.max(maxx, x); miny = Math.min(miny, y); maxy = Math.max(maxy, y); }));
  const s = Math.min((W - 8) / (maxx - minx), (H - 8) / (maxy - miny)), ox = (W - (maxx - minx) * s) / 2, oy = (H - (maxy - miny) * s) / 2;
  const P = ([lo, la]) => `${(ox + (lo * kx - minx) * s).toFixed(1)},${(oy + (-la - miny) * s).toFixed(1)}`;
  const paths = geo.features.map((f) => {
    const g = f.geometry, polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates;
    const d = polys.map((p) => p.map((ring) => `M${ring.map(P).join('L')}Z`).join('')).join('');
    const on = f.properties.regionId === highlightId;
    return `<path d="${d}" fill="${on ? C.lake : C.panel}" stroke="${on ? C.ink : '#fff'}" stroke-width="${on ? 1.5 : 1}" stroke-linejoin="round"/>`;
  });
  // draw highlight last
  const hi = geo.features.findIndex((f) => f.properties.regionId === highlightId);
  const ordered = paths.filter((_, i) => i !== hi).concat(hi >= 0 ? [paths[hi]] : []);
  return svg(W, H, ordered.join(''), 'Map of the 23 areas of Finland with the pilot area highlighted');
}

// ------------------------------------------------------------------ 12. lung mortality, shrunk estimate with interval, all areas
export function lungDots(rows, names, focus, labelled, caption = ['', '']) {
  const W = 420, rowH = 17.5, m = { l: 128, r: 44, t: 26, b: 54 }, H = m.t + rows.length * rowH + m.b;
  const lo = 0.75, hi = 1.4, iw = W - m.l - m.r, X = (v) => m.l + ((v - lo) / (hi - lo)) * iw;
  const sorted = [...rows].sort((a, b) => b.shrunk - a.shrunk);
  const grid = [0.8, 1.0, 1.2, 1.4].map((v) => `<line x1="${X(v)}" x2="${X(v)}" y1="${m.t - 6}" y2="${H - m.b + 2}" stroke="${v === 1 ? C.ink2 : C.grid}" stroke-width="${v === 1 ? 1.2 : 1}"/>${t(X(v), H - m.b + 20, v.toFixed(2), { fs: 12, fill: C.muted, anchor: 'middle' })}`).join('')
    + t(X(1.0) + 5, m.t - 10, 'national level = 1.00', { fs: 12, fill: C.ink2 });
  const body = sorted.map((r, i) => {
    const y = m.t + i * rowH + rowH / 2, on = r.regionId === focus, lab = labelled.includes(r.regionId) || on;
    const col = on ? C.lake : C.neutral;
    return `<line x1="${X(r.shrunkLow)}" x2="${X(r.shrunkHigh)}" y1="${y}" y2="${y}" stroke="${col}" stroke-width="${on ? 3 : 2}" stroke-linecap="round"/>`
      + `<circle cx="${X(r.shrunk)}" cy="${y}" r="${on ? 6 : 4.5}" fill="${on ? C.lake : C.ink2}" stroke="#fff" stroke-width="1.5"/>`
      + t(m.l - 10, y + 4.5, esc(names[r.regionId]), { fs: on ? 13 : 12, fw: on ? 700 : 400, fill: on || lab ? C.ink : C.muted, anchor: 'end' })
      + (lab ? t(X(r.shrunkHigh) + 6, y + 4.5, r.shrunk.toFixed(3), { ff: F.num, fs: on ? 14 : 12.5, fw: 700, fill: C.ink }) : '');
  }).join('');
  return svg(W, H, grid + body + t(0, H - 20, esc(caption[0]), { fs: 11.5, fill: C.muted }) + t(0, H - 5, esc(caption[1]), { fs: 11.5, fill: C.muted }),
    'Dot and interval chart of lung cancer mortality relative to the national level for 23 areas');
}
