// County action-plan draft panel. Renders cached plans from data/planner/plans-v1.json (pass the
// parsed object). Pure function returning an HTML string, so it works without a browser and the
// demo needs no live model call. Only sentences that passed the gate are shown; dropped sentences
// are counted, never shown or edited. The action title and the roadmap measure come from SAMA's
// own tools (get_evidence, get_roadmap_measure), not from the model.
const LABEL = 'Draft for a planner, drafted by Nemotron 3.5 Super VL; numbers checked';
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const link = (label, url) => (/^https?:\/\//.test(url || '') ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : esc(label));
const ORDER = ['action', 'rationale', 'owner_role', 'indicator'];

// opts.withhold(sentence) -> true withholds a kept sentence that the current brief no longer supports (for example
// a flag SAMA has since downgraded to a possible signal); withheld sentences are counted with opts.withheldWhy.
export function plannerHtml(plans, regionId, opts = {}) {
  const withhold = typeof opts.withhold === 'function' ? opts.withhold : () => false;
  const head = `<p class="kicker"><span class="chip draft">DRAFT</span> ${esc(plans?.label || LABEL)}</p>`;
  const c = plans?.counties?.[regionId];
  if (!c || !c.plan) return `<section class="planner" data-kind="DRAFT">${head}<p class="missing-label">No checked draft is stored for this county.</p></section>`;
  const actions = c.plan.actions.map((a) => {
    const sentences = ORDER.map((f) => a.sentences.find((s) => s.field === f)).filter(Boolean);
    const kept = sentences.filter((s) => s.kept);
    const shown = kept.filter((s) => !withhold(s)), held = kept.length - shown.length;
    const rm = a.roadmap_measure?.ok && a.roadmap
      ? `<p class="roadmap">Roadmap measure ${esc(a.roadmap.id)}: ${link(a.roadmap.title_en, a.roadmap.url)} (page ${esc((a.roadmap.pages || []).join('-'))})</p>`
      : '<p class="roadmap missing-label">Roadmap measure not confirmed by code.</p>';
    return `<li class="planner-action"><h4>${esc(a.title || a.action_id)}</h4>${shown.map((s) => `<p data-field="${esc(s.field)}">${esc(s.text)}</p>`).join('')}${rm}<p class="caption">${sentences.length - kept.length} of ${sentences.length} sentences dropped by the check${held ? `; ${held} more withheld because ${esc(opts.withheldWhy || 'the current brief no longer supports it')}` : ''}.</p></li>`;
  }).join('');
  const lim = c.plan.evidenceLimit;
  const limit = lim?.kept
    ? `<p class="evidence-limit"><strong>What the evidence does not support:</strong> ${esc(lim.text)}</p>`
    : '<p class="evidence-limit missing-label">The line on what the evidence does not support was dropped by the check.</p>';
  const s = plans.summary || {};
  const measured = s.countiesWithAtLeast3Kept != null
    ? `<p class="caption">Across ${esc(s.counties)} counties: ${esc(s.keptSentences)} of ${esc(s.sentences)} drafted sentences kept; ${esc(s.keptSentencesWithUnmatchedNumber)} kept sentences with a number that is not in a tool output; ${esc(s.offLimits?.pass)} of ${esc(s.offLimits?.prompts)} off-limits requests produced no plan.</p>`
    : '';
  return `<section class="planner" data-kind="DRAFT">${head}<h3>Action plan draft: ${esc(c.name)}</h3><ol class="planner-actions">${actions}</ol>${limit}`
    + `<p class="caption">Each sentence shown passed two checks: code confirmed that every number equals a tool output of the same run, and TypeSafe ${esc(c.plan.evidenceLimit?.jev?.model || 'Jev')} judged it faithful to those outputs and free of overclaim. Sentences that failed were dropped, not edited. Model results are scenarios under stated assumptions. A planner decides what to do; this is not advice about any patient.</p>`
    + `${measured}<p class="caption">Drafted ${esc(String(plans.generatedAt || '').slice(0, 10))} with ${esc(plans.model)}, prompt ${esc(plans.promptVersion)}, on app data ${esc(String(plans.appSha256?.[0] || '').slice(0, 12))}.</p></section>`;
}
