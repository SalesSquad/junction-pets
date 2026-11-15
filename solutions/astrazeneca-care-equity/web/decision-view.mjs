// Shared visible/print rendering; all inputs remain escaped.
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[c]));
const number = value => Number.isFinite(value) ? value.toLocaleString('en-GB', { maximumFractionDigits: 2 }) : 'Not measured';
const sourceLink = source => source?.url?.startsWith('https://')
  ? `<a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.publisher || source.title || 'Source')}</a>`
  : esc(source?.publisher || source?.title || 'Source unavailable');

export function renderRegistryContext(records) {
  return records.map(record => `<article class="context-card">
    <p class="kicker">${esc(record.kind.replaceAll('_', ' '))} · National context</p>
    <h4>${esc(record.title)}</h4>
    ${record.measure ? `<p class="context-number">${number(record.measure.reportedValue)}% <span>${number(record.measure.numerator)} / ${number(record.measure.denominator)} cases</span></p><p>${esc(record.measure.definition)}</p>` : ''}
    <p class="caption">${esc(record.scope.population)} · ${esc(record.scope.cancerCodes.join(', '))} · ${record.scope.period.start}–${record.scope.period.end} · ${esc(record.scope.geography)}</p>
    <ul>${record.limitations.map(text => `<li>${esc(text)}</li>`).join('')}</ul>
    <p><strong>Before comparing:</strong> ${esc(record.nextEvidenceNeeded)}</p>
    <p class="caption">${sourceLink(record.source)} · ${esc(record.source.locator)} · checked ${esc(record.source.retrievedAt)}</p>
  </article>`).join('');
}

export function renderDecisionCard(decision, { detailed = false } = {}) {
  const d = decision, a = d.action, s = d.signal, o = d.observation;
  const outcome = o.kind === 'observed_aggregate'
    ? `<p class="decision-number">${number(o.value)} <span>mortality ratio</span></p><p>95% interval ${number(o.low)}–${number(o.high)} · Finland = 1.</p><p class="caption">${esc(o.period.join(', '))} · age standardised and shrunk.</p><p>${esc(o.interpretation)}</p><p class="caption">${sourceLink(o.source)}</p>`
    : `<p>${esc(o.reason)}</p>`;
  const signal = s
    ? `<p><strong>${esc(s.title)}</strong></p><p>County ${number(s.county)} ${esc(s.unit)} · national ${number(s.national)} ${esc(s.unit)}.</p><p class="caption">Means over the same years: ${esc(s.years.join(', '))}.</p><p>${esc(s.interpretation)}</p><p class="caption">${sourceLink(s.source)}</p>`
    : '<p>No usable, comparable flagged signal identifies a service change here. Start with the cancer-pathway data that is missing.</p>';
  return `<article class="decision-card" data-decision-region="${esc(d.regionId)}">
    <div class="decision-topline"><p class="kicker">${esc(d.regionName)} / ${s ? 'Investigate a signal' : 'Measurement first'}</p><span class="review-tag">Proposal · human review required</span></div>
    <h3>${esc(a.title)}</h3><p class="decision-intent">${esc(a.decision)}</p>
    <div class="decision-evidence">
      <section><h4>01 · Observed outcome</h4>${outcome}</section>
      <section><h4>02 · Pathway question</h4>${signal}</section>
      <section><h4>03 · What is still missing</h4><p>Cancer-specific diagnosis and treatment-start times are unavailable in this snapshot.</p><p>Missing records require investigation. They do not establish that care was absent.</p><p class="caption">Goal 3.1: timely pathways. Goal 3.2: comparable quality information.</p></section>
    </div>
    <div class="decision-plan"><div><h4>Proposed first 30 days</h4><ol>${a.first30Days.map(text => `<li>${esc(text)}</li>`).join('')}</ol></div>
    <dl><dt>Proposed owner</dt><dd>${esc(a.owner)}</dd><dt>90-day review</dt><dd>${esc(a.reviewAt90Days)}</dd><dt>Cost</dt><dd>${esc(a.cost.note)}</dd></dl></div>
    <details ${detailed ? 'open' : ''}><summary>Inspect the action, evidence and measurement plan</summary>
      <p><strong>Candidate change:</strong> ${esc(a.proposedChange)}</p>
      <p><strong>Proposed mechanism:</strong> ${esc(a.mechanism)} <span class="review-tag">Hypothesis</span></p>
      <dl><dt>Measure</dt><dd>${esc(a.monitoring.metric)}</dd><dt>Numerator</dt><dd>${esc(a.monitoring.numerator)}</dd><dt>Denominator</dt><dd>${esc(a.monitoring.denominator)}</dd><dt>Baseline / target</dt><dd>Not yet measured / to be agreed before the pilot.</dd><dt>Missing data</dt><dd>${esc(a.monitoring.missingness)}</dd></dl>
      <p>${esc(a.monitoring.design)}</p><p>${esc(a.goal3)}</p>
      <ul>${a.unknowns.map(text => `<li>${esc(text)}</li>`).join('')}</ul>
      <p class="caption">${a.sources.map(sourceLink).join(' · ')}</p>
      <p class="caption">${esc(d.prioritisation)}</p>
    </details>
    <details ${detailed ? 'open' : ''}><summary>Check national recording gaps and source scope</summary>
      <div class="registry-context">${renderRegistryContext(d.nationalContext)}</div>
    </details>
  </article>`;
}

export function renderFuture(future) {
  return `<details class="future-context"><summary>Future direction: ${esc(future.title)}</summary>
    <p class="kicker">Future capability · not implemented · Goal 4.3</p>
    <p>${esc(future.proposal)}</p><ul>${future.requiredEvidence.map(text => `<li>${esc(text)}</li>`).join('')}</ul>
    <p>${esc(future.boundary)}</p><p class="caption">${sourceLink(future.source)} · ${esc(future.source.locator)}</p></details>`;
}
