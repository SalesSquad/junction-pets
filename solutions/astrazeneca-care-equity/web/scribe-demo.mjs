// Scribe demo: renders one POST /api/scribe response as HTML. Pure function, no DOM access, so it can be
// tested in Node and called from app.mjs. The note, highlighted date phrases, what Gemma wrote, the dates code
// computed, and "a person confirms every event". Every value is escaped. Uses classes already in styles.css only
// (the Content-Security-Policy blocks inline styles).

const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
// Event and route codes as words; acronyms stay upper case (MDT_DECISION -> "MDT decision").
const ACRONYMS = new Set(['mdt', 'ct', 'mri', 'pet', 'gp']);
const typeLabel = (t) => { const s = String(t ?? '').toLowerCase().split('_').map((w) => (ACRONYMS.has(w) ? w.toUpperCase() : w)).join(' '); return s.charAt(0).toUpperCase() + s.slice(1); };
const fmtDate = (d, precision) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(d ?? ''));
  if (!m) return esc(d ?? '—');
  return precision === 'MONTH' ? `${Number(m[2])}/${m[1]}` : `${Number(m[3])}.${Number(m[2])}.${m[1]}`;
};
const PERSON = 'A person confirms every event.';
const PREFILLED = 'pre-filled for one-click confirmation';
const NEEDS_EDITING = 'needs editing';
const NOT_RUN = 'second reader not run offline';
const sameAnswer = (a, b) => !!a && !!b && a.entry_route === b.entry_route && Array.isArray(a.events) && Array.isArray(b.events)
  && a.events.length === b.events.length
  && a.events.every((e, i) => e.type === b.events[i].type && e.date === b.events[i].date && e.precision === b.events[i].precision);

// Two-reader rule, same as serve/demo/engine.py apply_second_reader: pre-filled for one-click confirmation only when the
// first reader's answer is usable with no flag AND the second reader's stored answer for the same note is exactly equal.
// second: {available, prediction, how, source} or null (free text, or a note rewritten by code: never read by it).
// Returns a new result; a person confirms every event either way.
export function applySecondReader(result, second) {
  const r = {...result};
  const first = r.single_reader_review ?? r.review;
  const available = !!second?.available;
  const agrees = available && sameAnswer(r.resolved?.prediction, second.prediction);
  r.single_reader_review = first;
  r.second_reader = {model: 'nemotron-3.5-super-vl', version: 'v3', how: available ? second.how : NOT_RUN, source: available ? second.source ?? null : null,
    available, prediction: available ? second.prediction ?? null : null, agrees: available ? agrees : null};
  r.review = first === PREFILLED && agrees ? PREFILLED : NEEDS_EDITING;
  r.review_reason = !available ? NOT_RUN : first !== PREFILLED ? `the first reader's answer needs editing (${[...(r.flags ?? []), ...(r.errors ?? [])].join(', ') || 'not usable'})`
    : agrees ? 'both readers agree exactly' : 'readers disagree';
  return r;
}

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
  // data-label: on a phone (styles.css, below 600 px) each row becomes a card of label/value lines.
  return `<tr><th scope="row" data-label="Event">${esc(typeLabel(e.type))}</th><td data-label="Date proposed"><strong>${fmtDate(e.date, e.precision)}</strong></td><td data-label="Phrase in the note">${e.phrase ? `“${esc(e.phrase)}”` : '—'}</td>`
    + `<td data-label="Gemma's own date">${changed ? `<s>${fmtDate(e.model_date, e.model_precision)}</s>` : fmtDate(e.model_date, e.model_precision)}</td>`
    + `<td data-label="How the date was set">${how}</td><td data-label="Status">Proposed; a person confirms</td></tr>`;
}

// The stored reason code stays as serve/demo/engine.py writes it (NOT_RUN); the page says it in plain words.
const reasonText = (r) => (r.review_reason === NOT_RUN
  ? `Nemotron, the second reader, has no stored answer for this ${r.demo?.rewritten_by_code ? 'rewritten note' : r.synthetic_note === true ? 'note' : 'typed text'}, so a person edits it`
  : r.review_reason);
// The stored "how" of the second reader was written before the page could ask Nemotron live; its last clause is dropped.
const howText = (how) => String(how ?? '').replace(/; the page does not call it$/, '');
const seconds = (ms) => (Number.isFinite(ms) ? (ms / 1000).toFixed(1) : '?');
const eventKey = (e) => `${typeLabel(e?.type)} ${fmtDate(e?.date, e?.precision)}`;
// What differs between two answers, in words (entry route, events only one reader lists).
function answerDiff(gemma, nemo) {
  const parts = [];
  if (gemma.entry_route !== nemo.entry_route) parts.push(`entry route: Gemma ${esc(typeLabel(gemma.entry_route))}, Nemotron ${esc(typeLabel(nemo.entry_route))}`);
  const a = (gemma.events ?? []).map(eventKey), b = (nemo.events ?? []).map(eventKey);
  const onlyA = a.filter((k) => !b.includes(k)), onlyB = b.filter((k) => !a.includes(k));
  if (onlyA.length) parts.push(`only Gemma lists ${onlyA.map(esc).join(', ')}`);
  if (onlyB.length) parts.push(`only Nemotron lists ${onlyB.map(esc).join(', ')}`);
  return parts.length ? parts.join('; ') : 'the same events in a different order';
}

// The page's "Ask Nemotron live (second reader)" button: the POST /api/scribe/second answer
// ({served:'live'|'stored'|'none', prediction, model, latency_ms, how, source, reason}) applied to the Gemma answer on
// screen with the same two-reader rule. 'none' (no answer at all) leaves the result on screen as it is.
export function withSecondCall(response, call) {
  const r = response?.result ?? (response?.note ? response : null);
  const usable = !!call && (call.served === 'live' || call.served === 'stored');
  const how = call?.served === 'live' ? `${call.how ?? 'asked live'}, ${seconds(call.latency_ms)} s` : call?.how;
  const result = r && usable ? applySecondReader(r, {available: true, prediction: call.prediction ?? null, how, source: call.source ?? null}) : r;
  return {...(response?.result ? response : {}), result, second_call: call ?? null};
}

// The second reader's own answer, whether it agrees with the Gemma answer on screen, and the verdict of the rule.
export function secondCallHtml(call, result) {
  if (!call || typeof call !== 'object') return '';
  const pred = call.prediction ?? null;
  const gemma = result?.resolved?.prediction ?? null;
  const answered = call.served === 'live' || call.served === 'stored';
  const out = [`<div class="second-call" data-served="${esc(call.served)}">`];
  out.push(`<h4>Second reader: Nemotron 3.5 Super VL${call.served === 'live' ? ', asked live' : ''}</h4>`);
  if (call.served === 'live') {
    out.push(`<p>Answered in <strong>${esc(seconds(call.latency_ms))} s</strong> on the hosted endpoint (${esc(call.model ?? 'nemotron-3.5-super-vl')}, reader ${esc(call.version ?? 'v3')}${Number.isInteger(call.calls) ? `, ${call.calls === 1 ? 'one call' : `${call.calls} calls: a read and one repair`}` : ''}). Code resolved the dates.</p>`);
  } else if (call.served === 'stored') {
    out.push(`<p>The live call was not used (${esc(call.reason ?? 'unavailable')}), so Nemotron's stored answer for this note is shown.</p>`);
  } else {
    out.push(`<p>No second answer: ${esc(call.reason ?? call.error ?? 'unavailable')}.</p>`);
  }
  if (answered) {
    if (!pred) out.push(`<p class="flag">Nemotron's answer could not be read as the expected JSON, so it counts as a different answer.</p>`);
    else if (pred.events?.length) out.push(`<div class="table-wrap"><table class="demo-events"><thead><tr><th scope="col">Event</th><th scope="col">Date</th></tr></thead><tbody>${pred.events.map((e) => `<tr><th scope="row" data-label="Event">${esc(typeLabel(e.type))}</th><td data-label="Date">${fmtDate(e.date, e.precision)}</td></tr>`).join('')}</tbody></table></div><p class="caption">Entry route: ${esc(typeLabel(pred.entry_route))}.</p>`);
    else out.push(`<p>No pathway event (entry route ${esc(typeLabel(pred.entry_route))}).</p>`);
    if (call.flagged) out.push(`<p class="caption">The reader's own check flagged this answer after one repair (a date it returned is not printed in the note in digits). The two-reader rule compares the answers only.</p>`);
    if (gemma && pred) out.push(`<p><strong>${sameAnswer(gemma, pred) ? 'Same answer as the Gemma answer on screen' : 'A different answer from the Gemma answer on screen'}</strong>${sameAnswer(gemma, pred) ? ': every event, date and the entry route match exactly.' : `: ${answerDiff(gemma, pred)}.`}</p>`);
    else if (!gemma) out.push(`<p class="caption">There is no Gemma answer on screen to compare with.</p>`);
  }
  if (result) out.push(`<p class="large-claim">Two-reader rule: ${result.review === PREFILLED && result.second_reader?.agrees === true ? 'pre-filled for one-click confirmation' : 'needs editing'}. ${PERSON}</p>`);
  else out.push(`<p>${PERSON}</p>`);
  out.push('</div>');
  return out.join('');
}

// response: the JSON body of POST /api/scribe ({served, result, fallback_reason?, server_seconds?}) or a bare result;
// second_call (from withSecondCall) adds the second reader's own answer below the verdict.
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
    ? `<p class="caption">This note was rewritten by code from a validation note: “${esc(r.demo.rewrite.from_phrase)}” became “${esc(r.demo.rewrite.to_phrase)}”, a phrasing the hand-written Finnish lexicon of the code resolver covers by design (the synthetic training notes never use it).</p>` : '';
  const out = [];
  out.push(`<div class="scribe-demo" data-served="${esc(served)}">`);
  out.push(`<p class="kicker">${label} Gemma reads, code counts · ${esc(r.note.id ?? 'note')}</p>`);
  out.push(`<h4>The note (date ${fmtDate(r.note.note_date, 'DAY')})</h4>`);
  out.push(`<blockquote class="note" lang="fi"><p>${highlightNote(r.note.note_text, r.highlights)}</p></blockquote>${rewrite}`);
  out.push(`<p class="caption">Marked: every date phrase in the note. A relative phrase (“kolme viikkoa sitten”, “eilen”) gets its calendar date from code, counted back from the note date. Gemma's own date for a relative phrase is not used; where it differed, it is struck through below.</p>`);
  if (errors.length) out.push(`<p class="flag">The answer could not be used as it is (${esc(errors.join('; '))}). It needs editing.</p>`);
  out.push(`<h4>Proposed events</h4>`);
  if (events.length) {
    out.push(`<div class="table-wrap"><table class="demo-events"><thead><tr><th scope="col">Event</th><th scope="col">Date proposed</th><th scope="col">Phrase in the note</th><th scope="col">Gemma's own date</th><th scope="col">How the date was set</th><th scope="col">Status</th></tr></thead><tbody>${events.map(eventRow).join('')}</tbody></table></div>`);
  } else {
    out.push(`<p>No pathway event proposed${r.resolved?.entry_route ? ` (entry route ${esc(typeLabel(r.resolved.entry_route))})` : ''}.</p>`);
  }
  if (r.resolved?.entry_route && events.length) out.push(`<p class="caption">Entry route proposed: ${esc(typeLabel(r.resolved.entry_route))}.</p>`);
  if (needs.length) out.push(`<p class="flag">A person sets the date for: ${needs.map((n) => `“${esc(n.phrase)}”`).join(', ')}.</p>`);
  const review = r.review === PREFILLED && r.second_reader?.agrees === true ? 'Pre-filled for one-click confirmation' : 'Needs editing';
  const sr = r.second_reader;
  out.push(`<div class="headline-box"><p class="large-claim">${esc(review)}. ${PERSON}</p>`);
  if (r.review_reason) out.push(`<p class="caption">Why: ${esc(reasonText(r))}.</p>`);
  else if ((r.flags ?? []).length) out.push(`<p class="caption">Why: ${esc(r.flags.join(', '))}.</p>`);
  if (sr) out.push(`<p class="caption">Second reader, Nemotron 3.5 Super VL: ${sr.available ? `${sr.agrees ? 'same answer as Gemma' : 'a different answer from Gemma'} (${esc(howText(sr.how))})` : 'no stored answer for this text (Nemotron did not read it before the demo was built; “Ask Nemotron live” sends it now), so the note needs editing'}. A note is pre-filled only when both readers give exactly the same answer.</p>`);
  else out.push(`<p class="caption">No second reader was applied to this result, so it needs editing.</p>`);
  if (r.answer_key) out.push(`<p class="caption">Against the note's SYNTHETIC answer key: ${r.exact_match_with_answer_key ? 'every event and date matches' : 'does not match; the person confirming would have to edit it'}.</p>`);
  out.push(`</div>`);
  if (response?.second_call) out.push(secondCallHtml(response.second_call, r));
  out.push(`<details class="track-details"><summary>What Gemma wrote: the model's raw output</summary><pre><code>${esc(r.model?.raw ?? '')}</code></pre></details>`);
  out.push(`<p class="caption">${servedLine} Model: ${esc(p.base_model?.repo)} (revision ${esc(String(p.base_model?.revision ?? '').slice(0, 8))}) with the LoRA adapter ${esc(p.adapter?.run)}, ${esc(p.decoding?.dtype)} on ${esc(p.decoding?.device)}, greedy. Dates: ${esc(res.rule)}, arm ${esc(res.arm)}${res.frozen ? ' (frozen, hashes checked)' : ' (not the frozen arm)'}. Trained and tested on SYNTHETIC notes only; research demo, not a medical device.</p>`);
  out.push(`</div>`);
  return out.join('');
}
