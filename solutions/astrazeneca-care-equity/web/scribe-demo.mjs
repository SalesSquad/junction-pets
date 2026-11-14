// Offline scribe demo: renders one POST /api/scribe response as HTML. Pure function, no DOM access, so it can be
// tested in Node and called from app.mjs. The note, highlighted date phrases, what Gemma wrote, the dates code
// computed, and "a person confirms every event". Every value is escaped. Uses classes already in styles.css only
// (the Content-Security-Policy blocks inline styles).

const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const typeLabel = (t) => { const s = String(t ?? '').toLowerCase().replaceAll('_', ' '); return s.charAt(0).toUpperCase() + s.slice(1); };
const fmtDate = (d, precision) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(d ?? ''));
  if (!m) return esc(d ?? '—');
  return precision === 'MONTH' ? `${Number(m[2])}/${m[1]}` : `${Number(m[3])}.${Number(m[2])}.${m[1]}`;
};
const PERSON = 'A person confirms every event.';

// The note text with every date phrase wrapped in <mark data-kind=...>; relative phrases carry the computed date.
export function highlightNote(text, highlights) {
  const t = String(text ?? '');
  const spans = (Array.isArray(highlights) ? highlights : [])
    .filter((h) => Number.isInteger(h?.start) && Number.isInteger(h?.end) && h.start >= 0 && h.end <= t.length && h.start < h.end)
    .sort((a, b) => a.start - b.start);
  let out = '', at = 0;
  for (const h of spans) {
    if (h.start < at) continue; // overlapping spans are dropped, never nested
    out += esc(t.slice(at, h.start));
    const phrase = esc(t.slice(h.start, h.end));
    if (h.kind === 'relative') {
      out += `<mark data-kind="relative" title="${esc(`${h.days_before_note} days before the note date; computed by code`)}">${phrase}</mark> <small>(= ${fmtDate(h.date, 'DAY')}, computed by code)</small>`;
    } else if (h.kind === 'needs_person') {
      out += `<mark data-kind="needs-person" title="No single exact day">${phrase}</mark> <small>(no single day: a person sets this date)</small>`;
    } else {
      out += `<mark data-kind="absolute" title="Date written in the note">${phrase}</mark>`;
    }
    at = h.end;
  }
  return out + esc(t.slice(at));
}

function eventRow(e) {
  const how = e.date_computed_by_code
    ? `Code: “${esc(e.phrase)}” counted back from the note date`
    : e.phrase_kind === 'absolute' ? 'Copied from the date written in the note'
      : e.phrase_kind === 'relative' ? `Gemma's date equals “${esc(e.phrase)}” counted back by code`
        : '<span class="flag">No date phrase in the note carries this date: check it</span>';
  const changed = e.date_computed_by_code && (e.model_date !== e.date || e.model_precision !== e.precision);
  // Date proposed comes second, so it stays on screen on a phone; the table scrolls for the rest.
  return `<tr><th scope="row">${esc(typeLabel(e.type))}</th><td><strong>${fmtDate(e.date, e.precision)}</strong></td><td>${e.phrase ? `“${esc(e.phrase)}”` : '—'}</td>`
    + `<td>${changed ? `<s>${fmtDate(e.model_date, e.model_precision)}</s>` : fmtDate(e.model_date, e.model_precision)}</td>`
    + `<td>${how}</td><td>Proposed; a person confirms</td></tr>`;
}

// response: the JSON body of POST /api/scribe ({served, result, fallback_reason?, server_seconds?}) or a bare result.
export function scribeDemoHtml(response) {
  const r = response?.result ?? response;
  if (!r || typeof r !== 'object' || !r.note) {
    const reason = response?.error ?? 'no scribe result';
    return `<p class="missing-label">The scribe demo has no result to show: ${esc(reason)}. ${PERSON}</p>`;
  }
  const served = response?.served ?? 'precomputed';
  const p = r.provenance ?? {};
  const res = p.resolver ?? {};
  const t = r.timing ?? {};
  const synthetic = r.synthetic_note === true;
  const events = r.resolved?.events ?? [];
  const errors = [...(r.errors ?? []), ...(r.model?.errors ?? [])];
  const needs = r.date_resolution?.needs_person ?? [];
  const label = synthetic ? '<span class="chip synthetic">SYNTHETIC</span>' : '<span class="chip assumption">TYPED TEXT</span>';
  const servedLine = served === 'live'
    ? `Run live on this computer's CPU: ${esc(t.total_seconds ?? '?')} s for this note${response?.server_seconds != null ? ` (${esc(response.server_seconds)} s at the server)` : ''}.`
    : `Precomputed output of the same CPU process${response?.fallback_reason ? ` (live run not used: ${esc(response.fallback_reason)})` : ''}.`;
  const rewrite = r.demo?.rewritten_by_code && r.demo.rewrite
    ? `<p class="caption">This note was rewritten by code from a validation note: “${esc(r.demo.rewrite.from_phrase)}” became “${esc(r.demo.rewrite.to_phrase)}”, a phrasing the synthetic training notes never use.</p>` : '';
  const out = [];
  out.push(`<div class="scribe-demo" data-served="${esc(served)}">`);
  out.push(`<p class="kicker">${label} Gemma reads, code counts · ${esc(r.note.id ?? 'note')}</p>`);
  out.push(`<h4>The note (date ${fmtDate(r.note.note_date, 'DAY')})</h4>`);
  out.push(`<blockquote class="note" lang="fi"><p>${highlightNote(r.note.note_text, r.highlights)}</p></blockquote>${rewrite}`);
  out.push(`<p class="caption">Marked: every date phrase in the note. A relative phrase (“kolme viikkoa sitten”, “eilen”) gets its calendar date from code, counted back from the note date. Gemma's own date for a relative phrase is not used; where it differed, it is struck through below.</p>`);
  out.push(`<h4>What Gemma wrote</h4><pre><code>${esc(r.model?.raw ?? '')}</code></pre>`);
  if (errors.length) out.push(`<p class="flag">The answer could not be used as it is (${esc(errors.join('; '))}). It needs editing.</p>`);
  out.push(`<h4>Proposed events</h4>`);
  if (events.length) {
    out.push(`<div class="table-wrap"><table><thead><tr><th scope="col">Event</th><th scope="col">Date proposed</th><th scope="col">Phrase in the note</th><th scope="col">Gemma's own date</th><th scope="col">How the date was set</th><th scope="col">Status</th></tr></thead><tbody>${events.map(eventRow).join('')}</tbody></table></div>`);
  } else {
    out.push(`<p>No pathway event proposed${r.resolved?.entry_route ? ` (entry route ${esc(typeLabel(r.resolved.entry_route))})` : ''}.</p>`);
  }
  if (r.resolved?.entry_route && events.length) out.push(`<p class="caption">Entry route proposed: ${esc(typeLabel(r.resolved.entry_route))}.</p>`);
  if (needs.length) out.push(`<p class="flag">A person sets the date for: ${needs.map((n) => `“${esc(n.phrase)}”`).join(', ')}.</p>`);
  const review = r.review === 'pre-filled for one-click confirmation' ? 'Pre-filled for one-click confirmation' : 'Needs editing';
  out.push(`<div class="headline-box"><p class="large-claim">${esc(review)}. ${PERSON}</p>`);
  if ((r.flags ?? []).length) out.push(`<p class="caption">Why: ${esc(r.flags.join(', '))}.</p>`);
  if (r.answer_key) out.push(`<p class="caption">Against the note's SYNTHETIC answer key: ${r.exact_match_with_answer_key ? 'every event and date matches' : 'does not match; the person confirming would have to edit it'}.</p>`);
  out.push(`</div>`);
  out.push(`<p class="caption">${servedLine} Model: ${esc(p.base_model?.repo)} (revision ${esc(String(p.base_model?.revision ?? '').slice(0, 8))}) with the LoRA adapter ${esc(p.adapter?.run)}, ${esc(p.decoding?.dtype)} on ${esc(p.decoding?.device)}, greedy. Dates: ${esc(res.rule)}, arm ${esc(res.arm)}${res.frozen ? ' (frozen, hashes checked)' : ' (not the frozen arm)'}. Trained and tested on SYNTHETIC notes only; research demo, not a medical device.</p>`);
  out.push(`</div>`);
  return out.join('');
}
