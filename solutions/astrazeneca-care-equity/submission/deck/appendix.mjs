// Technical appendix pages A1-A13. Every number, in tables and in prose, is read from a JSON file via val()/inText().
export function build(x) {
  const { val, get, inText, nf, pct, esc, code, stress, casTest, casStress, casVal, base, files: F } = x;
  const TF = 'data/scribe/v2/training-figures-v1.json', SMK = 'serve/smoke/smoke-guided.json', NL = 'data/scribe/nemotron/ledger.json', JL = 'data/planner/jev-ledger.json';
  const pages = [];
  const page = (id, title, body, sources) => pages.push({ id, kicker: 'Technical appendix', rubric: 'Data quality and transparency', title, body, sources, cls: 'appx', synthetic: /SYNTHETIC/.test(body) ? 'where marked' : false });
  const sec = (n, h, inner, cls = '') => `<div class="${cls}"><h2><span>${n}</span>${h}</h2>${inner}</div>`;
  const kn = (k, n) => `${k}/${n}`;

  // ---------------------------------------------------------------- A1 + A2
  const ind = (k, f) => val(F.APP, `analysis.indicators.${k}.${f}`);
  const pc = 'pilotCard.snapshotEvidence';
  const aiI = get(F.EV, 'rows').findIndex((r) => r.id === 'eu-ai-act-dates'), MON = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const aiD = (k) => { const [y, m, d] = val(F.EV, `rows[${aiI}].values.${k}`).split('-').map(Number); return `${d} ${MON[m - 1]} ${y}`; };
  const evI = get(F.EV, 'rows').findIndex((r) => r.id === 'kuitunen-2026-route-medians-groups');
  const kt = (k) => val(F.EV, `rows[${evI}].values.${k}`);
  const rec = (p) => val(F.APP, `recommendation.portfolio.${p}`);
  page('A1-A2', 'Data, statistics and the scenario model', `<div class="cols">
    ${sec('A1', 'Data and statistics', `<ul>
      <li><b>23 areas, ${Object.keys(get(F.APP, 'analysis.indicators')).length} indicators</b>, cancer deaths by site ${val(F.APP, 'analysis.mortality.lung.window[0]')}-${val(F.APP, `analysis.mortality.lung.window[${get(F.APP, 'analysis.mortality.lung.window').length - 1}]`)}, NORDCAN survival. Every request to THL Sotkanet, Statistics Finland and NORDCAN is stored with its retrieval time and SHA-256.</li>
      <li>Exact Poisson intervals, indirect age standardisation, gamma-Poisson empirical Bayes shrinkage, false-discovery-rate control (${code('src/stats.mjs')}, ${code('src/analysis.mjs')}). Small counts are suppressed, not ranked.</li>
      <li>Below the 80% screening target: colorectal in <b>${ind('screen_colorectal', 'countiesMissingTarget')} of ${ind('screen_colorectal', 'countiesWithData')}</b> counties with data, cervical in <b>${ind('screen_cervix', 'countiesMissingTarget')} of ${ind('screen_cervix', 'countiesWithData')}</b>.</li>
      <li>All-cancer mortality, shrunk estimate: Satakunta <b>${val(F.MAP, `${pc}.shrunk`)}</b> (${val(F.MAP, `${pc}.shrunkLow`)}-${val(F.MAP, `${pc}.shrunkHigh`)}) times the national level; the highest areas are too close to rank, so no rank is claimed. Regional lung mortality follows incidence, so excess mortality is not a count of deaths avoidable by better care.</li>
      <li>${code('gp_wait_over_7d')} is measured against a legal maximum that changed from 2025; values after 2024 are not comparable with earlier ones.</li></ul>`)}
    ${sec('A2', 'Scenario model and optimiser (upper-bound SCENARIO, not a headline)', `<ul>
      <li>The optimiser picks ${get(F.APP, 'recommendation.portfolio.picks').length} county actions for EUR ${nf(rec('spent') / 1e6, 2)} million of a EUR ${nf(val(F.APP, 'recommendation.budget') / 1e6, 1)} million yearly budget. SCENARIO: ${rec('deathsPostponed')} deaths postponed a year (${rec('low')}-${rec('high')}) over ${val(F.APP, 'recommendation.draws')} parameter draws; ${pct(rec('shareInHighMortalityCounties'), 1)} of it in counties with above-average cancer mortality.</li>
      <li>Disclosure: the route prior is read from the paper's Figure 1; the text's medians are ${kt('median_public')} against ${kt('median_fast')} days and its means ${kt('mean_public')} against ${kt('mean_fast')}.</li>
      <li>Check against Denmark: for a ${inText(F.APP, 'recommendation.validation.note', /For a (\d+)-day shorter/)}-day shorter interval the model implies a hazard ratio of ${val(F.APP, 'recommendation.validation.modelHazardRatio')}; Denmark observed ${val(F.APP, 'recommendation.validation.observedHazardRatio')} (${val(F.APP, 'recommendation.validation.observedLow')}-${val(F.APP, 'recommendation.validation.observedHigh')}).</li>
      <li>The 2027 pilot ask (slide 11) is separate from this scenario portfolio.</li></ul>`)}
  </div>`, `${code(F.APP)} analysis, recommendation; ${code(F.MAP)} pilotCard.snapshotEvidence; ${code(F.EV)} kuitunen-2026-route-medians-groups; ${code('ARCHITECTURE.md')}.`);

  // ---------------------------------------------------------------- A3 roadmap mapping
  const acts = get(F.MAP, 'actions');
  const measures = get(F.MAP, 'measures');
  const rows = acts.map((a, i) => {
    const m = measures[a.primary] || {};
    return `<tr><td>${esc(a.actionId)}</td><td>${esc(val(F.MAP, `actions[${i}].fit`))}</td><td class="n">${esc(val(F.MAP, `actions[${i}].primary`))}</td><td class="n">${esc((m.pages || []).join('-'))}</td><td>${esc(m.owner_en || '')}</td></tr>`;
  }).join('');
  page('A3', 'Roadmap mapping: every action names its national roadmap measure', `<div class="cols"><div class="wide">
    <table><thead><tr><th>SAMA action</th><th>Fit</th><th>Measure</th><th>Pages</th><th>Roadmap owner</th></tr></thead><tbody>${rows}</tbody></table>
    <ul><li>"Named": the roadmap names this action. "Serves": the action serves that measure, which does not name it. The ${code('ldct-pilot')} action means joining the national lung screening pilot (2.3.4).</li>
    <li>Finnish quotes from the roadmap are checked word for word against their page of the PDF. English text is the team's reading, not an official translation.</li></ul></div></div>`,
  `${code(F.MAP)} actions, measures; ${code('data/roadmap/manifest.json')}.`);

  // ---------------------------------------------------------------- A4 + A5
  const mv = (arm, k) => val(F.MLX, `arms.${arm}.${k}`);
  page('A4-A5', 'Gemma scribe: training, the code date resolver and the phrase arms (SYNTHETIC)', `<div class="cols">
    ${sec('A4', 'Training', `<ul>
      <li>Gemma 3 270M instruction-tuned, LoRA, ${val(TF, 'epochs.C-270m-all-v2data.steps')} steps at effective batch ${val(TF, 'epochs.C-270m-all-v2data.effective_batch')}. CUDA: trained in ${val(TF, 'gpu.runs.post-ablation C-270m-all-v2data.train_seconds', (v) => nf(v))} s on one A100 80 GB on Verda, on ${val(TF, 'epochs.C-270m-all-v2data.train_rows', (v) => nf(v))} SYNTHETIC notes (${val(TF, 'epochs.A-270m-lora-r16 (reference).train_rows', (v) => nf(v))} of them by Nemotron, the rest by Claude Haiku). MLX on this laptop: the phrase arm trained in ${val(F.MLX, 'arms.B-270m-expr-aug.training.wall_seconds', (v) => nf(v))} s.</li>
      <li>Mixing two writers in training lifted Haiku-written test notes from ${val(F.DIAG, 'runs.v2-selected.test.by_writer.haiku.value', (v) => pct(v, 1))} to ${val(F.DIAG, 'runs.C-270m-all-v2data.test.by_writer.haiku.value', (v) => pct(v, 1))} exact match.</li>
      <li>Gemma 3 1B (LoRA) did not fix the dates by itself either: ${val(F.DIAG, 'runs.S-1b-lora-r16.test.by_has_relative.True.k')} of ${val(F.DIAG, 'runs.S-1b-lora-r16.test.by_has_relative.True.n')} relative-date notes.</li>
      <li>Served with vLLM and structured outputs: ${val(SMK, 'requests.valid_output')} of ${val(SMK, 'valid_output_rate.n')} valid JSON, p95 latency ${val(SMK, 'latency_seconds.p95', (v) => nf(v, 2))} s.</li></ul>`)}
    ${sec('A5', 'Code date resolver and the phrase arms', `
      <table><thead><tr><th>Product adapter C-270m-all-v2data</th><th>Model alone</th><th>+ code resolver</th></tr></thead><tbody>
      <tr><td>Validation (selection), ${val(F.DS, 'measured_interval_extraction.note_exact_match.validation.as_is.n')} notes</td><td class="n">${val(F.DS, 'measured_interval_extraction.note_exact_match.validation.as_is.k')}</td><td class="n">${val(F.DS, 'measured_interval_extraction.note_exact_match.validation.resolver.k')}</td></tr>
      <tr><td>Test, ${val(F.DS, 'measured_interval_extraction.note_exact_match.test.as_is.n')} notes (read before, post hoc)</td><td class="n">${val(F.DS, 'measured_interval_extraction.note_exact_match.test.as_is.k')}</td><td class="n">${val(F.DS, 'measured_interval_extraction.note_exact_match.test.resolver.k')}</td></tr>
      </tbody></table>
      <table><thead><tr><th>Validation, ${val(F.RES, "sets.val.systems.A'.exact_match.n")} SYNTHETIC notes (MLX)</th><th>Exact</th><th>Test (post hoc)</th></tr></thead><tbody>
      <tr><td>A': model writes absolute dates + frozen Finnish lexicon rule</td><td class="n">${val(F.RES, "sets.val.systems.A'.exact_match.k")}/${val(F.RES, "sets.val.systems.A'.exact_match.n")}</td><td class="n">${val(F.RES, "sets.test.systems.A'.exact_match.k")}/${val(F.RES, "sets.test.systems.A'.exact_match.n")}</td></tr>
      <tr><td>B: Gemma 3 270M copies the phrase, code computes every date</td><td class="n">${val(F.RES, 'sets.val.systems.B.exact_match.k')}/${val(F.RES, "sets.val.systems.A'.exact_match.n")}</td><td class="n">${val(F.RES, 'sets.test.systems.B.exact_match.k')}/${val(F.RES, "sets.test.systems.A'.exact_match.n")}</td></tr>
      <tr><td>C: Gemma 3 1B, same method</td><td class="n">${val(F.RES, 'sets.val.systems.C.exact_match.k')}/${val(F.RES, "sets.val.systems.A'.exact_match.n")}</td><td class="n">${val(F.RES, 'sets.test.systems.C.exact_match.k')}/${val(F.RES, "sets.test.systems.A'.exact_match.n")}</td></tr>
      </tbody></table>
      <ul><li>0 notes made worse by the resolver, in every run and split. The lexicon rule A' was frozen before any stress note existed (its hash is re-checked in the results file); vague phrases such as "pari viikkoa sitten" go to a person.</li>
      <li>B met the preregistered validation rule (B ${val(F.RES, 'comparisons.val[0].b_correct')} vs A' ${val(F.RES, 'comparisons.val[0].a_correct')}, McNemar p = ${val(F.RES, 'comparisons.val[0].exact_mcnemar_p')}). On the frozen stress set B got <b>${val(F.RES, 'primary_result.b_correct')} of ${val(F.RES, 'primary_result.n')}</b> new phrasings against A' ${val(F.RES, 'primary_result.a_correct')} (p = ${val(F.RES, 'primary_result.exact_mcnemar_p')}, +${val(F.RES, 'primary_result.difference_b_minus_a_points')} points) and ${val(F.RES, 'primary_result.B_standard_slice.k')} of ${val(F.RES, 'primary_result.B_standard_slice.n')} standard phrasings: <b>the preregistered criterion is not met</b>, and A' does not win.</li></ul>`)}
  </div>`, `${code(TF)} epochs, gpu; ${code(SMK)}; ${code('data/scribe/v3/student/compare-v1.json')}; ${code(F.DIAG)}; ${code('serve/smoke/smoke-guided.json')}; ${code(F.DS)} measured_interval_extraction; ${code(F.RES)}; ${code(F.MLX)}; ${code('data/scribe/v4/resolver/reproduce-v1.json')}.`);

  // ---------------------------------------------------------------- A6 + A7
  const lad = (k, f) => val(F.NEMO, `validation_ladder.${k}.${f}`);
  page('A6-A7', 'What reading errors do to a county figure, and how the second reader was improved (SYNTHETIC)', `<div class="cols">
    ${sec('A6', `Extraction errors and the county indicator (simulation, ${val(F.APP, 'insight.falseFlag.confirmed.replications', (v) => nf(v))} runs per cell)`, `
      <table><thead><tr><th>Simulated county figure</th><th>Every event confirmed</th><th>Model as is</th><th>+ code resolver</th></tr></thead><tbody>
      <tr><td>False flag: county from text, country from structured fields</td><td class="n">${val(F.APP, 'insight.falseFlag.confirmed.rate', (v) => pct(v, 1))}</td><td class="n">${val(F.APP, 'insight.falseFlag.countyTextCountryStructured.asIs.rate', (v) => pct(v, 1))}</td><td class="n">${val(F.APP, 'insight.falseFlag.countyTextCountryStructured.resolver.rate', (v) => pct(v, 1))}</td></tr>
      <tr><td>False flag: county written like Haiku, country like Nemotron</td><td class="n">${val(F.APP, 'insight.falseFlag.confirmed.rate', (v) => pct(v, 1))}</td><td class="n">${val(F.APP, 'insight.falseFlag.writerStyle.asIs.rate', (v) => pct(v, 1))}</td><td class="n">${val(F.APP, 'insight.falseFlag.writerStyle.resolver.rate', (v) => pct(v, 1))}</td></tr>
      </tbody></table>
      <ul><li>Error profiles measured on ${val(F.DS, 'measured_interval_extraction.note_exact_match.test.as_is.n')} SYNTHETIC test notes (read before, post hoc) from the product adapter C-270m-all-v2data. Extra predicted events change the rates little (see the page).</li>
      <li>An equity indicator is fair only if its measurement errors are the same everywhere; a different writing style alone can manufacture a gap.</li></ul>`)}
    ${sec('A7', 'Nemotron second reader: one change at a time', `
      <table><thead><tr><th>Change</th><th>Validation exact</th><th>Paired</th></tr></thead><tbody>
      <tr><td>v0: Nemotron writes absolute dates itself</td><td class="n">${lad('v0->v1', 'before')}/${casVal.n}</td><td></td></tr>
      <tr><td>v1: copies the date as written; code computes it</td><td class="n">${lad('v0->v1', 'after')}/${casVal.n}</td><td class="n">+${lad('v0->v1', 'change_points')} pts, ${lad('v0->v1', 'gained')} fixed, ${lad('v0->v1', 'lost')} worse</td></tr>
      <tr><td>v1 rerun unchanged (noise floor)</td><td class="n">${lad('v1->v1rep', 'after')}/${casVal.n}</td><td class="n">${lad('v1->v1rep', 'gained')} up, ${lad('v1->v1rep', 'lost')} down</td></tr>
      <tr><td>v2: + schema validation and one repair retry</td><td class="n">${lad('v1->v2', 'after')}/${casVal.n}</td><td class="n">p = ${nf(lad('v1->v2', 'mcnemar_exact_p'), 2)}</td></tr>
      <tr><td>v2g: + every date must be printed in the note</td><td class="n">${lad('v2->v2g', 'after')}/${casVal.n}</td><td class="n">p = ${nf(lad('v2->v2g', 'mcnemar_exact_p'), 2)}</td></tr>
      <tr><td>v3: + enable_thinking</td><td class="n">${lad('v2g->v3', 'after')}/${casVal.n}</td><td class="n">+${lad('v2g->v3', 'change_points')} pts, p = ${nf(lad('v2g->v3', 'mcnemar_exact_p'), 4)}</td></tr>
      </tbody></table>
      <ul><li>Test, read once by v3: <b>${val(F.NEMO, 'test.exact_match.k')}/${val(F.NEMO, 'test.exact_match.n')}</b>; Haiku-written ${val(F.NEMO, 'test.by_writer.haiku_written.k')}/${val(F.NEMO, 'test.by_writer.haiku_written.n')}, Nemotron-written ${val(F.NEMO, 'test.by_writer.nemotron_written.k')}/${val(F.NEMO, 'test.by_writer.nemotron_written.n')}. Nemotron wrote most of these notes itself, so its score on them is optimistic.</li>
      <li>Vision input tested: ${val(F.VIS, 'summary.image_exact')} of ${val(F.VIS, 'summary.notes')} page images read exactly against ${val(F.VIS, 'summary.text_exact')} of ${val(F.VIS, 'summary.notes')} from text; the product keeps text input.</li></ul>`)}
  </div>`, `${code(F.APP)} insight.falseFlag; ${code(F.DS)} measured_interval_extraction; ${code(F.NEMO)} validation_ladder, test; ${code(F.VIS)} summary.`);

  // ---------------------------------------------------------------- A8 + vague gate + A9
  const LP = 'data/scribe/v4/eval/local-pairs-posthoc-v1.json';
  const vg = (p) => val(F.VAG, `sets.stress.cascade_C_agreement.${p}`);
  const pl = (p) => val(F.PLAN, `summary.${p}`);
  page('A8-A9', 'Two readers, the vague-date gate and the county planner (SYNTHETIC notes)', `<div class="cols">
    ${sec('A8', 'Two-reader agreement: Gemma 3 1B + Nemotron 3.5 Super VL', `
      <table><thead><tr><th></th><th>Validation</th><th>Test (post hoc)</th><th>Stress (frozen)</th></tr></thead><tbody>
      <tr><td>Pre-filled for one-click confirmation (both agree)</td><td class="n">${casVal.acc}/${casVal.n}</td><td class="n">${casTest.prefilled}/${casTest.n}</td><td class="n">${casStress.prefilled}/${casStress.n}</td></tr>
      <tr><td>Wrong among pre-filled</td><td class="n">${casVal.wrong}</td><td class="n">${casTest.wrong} (${val(F.RES, 'cascade.configurations[' + get(F.RES, 'cascade.configurations').findIndex((c) => c.gemma === 'C' && c.signal === 'agreement') + '].test.error_among_prefilled.value', (v) => pct(v, 1))})</td><td class="n">${casStress.wrong}</td></tr>
      <tr><td>Needs editing</td><td class="n">${casVal.n - casVal.acc}</td><td class="n">${casTest.edit}</td><td class="n">${casStress.edit}</td></tr>
      </tbody></table>
      <ul><li>Rule fixed in advance: exact agreement, no score threshold; pairing chosen on validation notes only (a leak guard rejects any test or stress id). Baseline before: ${base.pre}/${base.n} pre-filled with ${base.wrong} wrong.</li>
      <li>Every wrong pre-filled test note swapped "referral received" for "referral sent" on the right date.</li>
      <li>Local readers only (post hoc, stored outputs): Gemma 3 1B + Gemma 3 270M with the lexicon resolver pre-fill ${val(LP, 'sets.test.pairs[1].prefilled.k')}/${val(LP, 'sets.test.pairs[1].prefilled.n')} test notes (${val(LP, 'sets.test.pairs[1].wrong_among_prefilled.k')} wrong) but only ${val(LP, 'sets.stress.pairs[1].prefilled.k')}/${val(LP, 'sets.stress.pairs[1].prefilled.n')} stress notes (${val(LP, 'sets.stress.pairs[1].wrong_among_prefilled.k')} wrong).</li></ul>
      <h2><span>A8b</span>Vague-date gate (post hoc: designed after the stress results were seen)</h2>
      <ul><li>A frozen Finnish lexicon rule flags vague dates ("a couple of weeks ago", "last spring"). On stress notes the cascade goes from ${vg('without_gate.prefilled_for_one_click_confirmation.k')}/${casStress.n} pre-filled with ${vg('without_gate.error_among_prefilled.k')} wrong to ${vg('with_gate_rule_v1.prefilled_for_one_click_confirmation.k')}/${casStress.n} with ${vg('with_gate_rule_v1.error_among_prefilled.k')} wrong. On its own it caught ${val(F.VAG, 'sets.stress.detector_rule_v1.vague_notes_caught.k')} of ${val(F.VAG, 'sets.stress.detector_rule_v1.vague_notes_caught.n')} vague notes on a small SYNTHETIC phrase family; it misses "a month ago" (${get(F.VAG, 'sets.stress.detector_rule_v1.vague_notes_missed').length} of ${val(F.VAG, 'sets.stress.detector_rule_v1.vague_notes_caught.n')}). Shown on the page as a POST HOC line.</li></ul>`)}
    ${sec('A9', 'Nemotron county planner (public aggregate data)', `<ul>
      <li>Nemotron called four SAMA tools and drafted a plan for <b>${pl('countiesRun')} of ${pl('counties')}</b> areas. Code checked every number against the tool outputs; a TypeSafe check then judged each sentence. Failures were dropped, never repaired.</li>
      <li>Prompt v1 kept ${val(F.PLAN, 'summary.promptComparison.v1.keptSentences')}/${val(F.PLAN, 'summary.promptComparison.v1.sentences')} sentences; prompt v2 changed only the field formats and kept <b>${pl('keptSentences')}/${pl('sentences')}</b> under the same gate. ${pl('keptSentencesWithUnmatchedNumber')} kept sentences with a number not in a tool output. ${pl('roadmapMeasureCodeChecked')} roadmap measure ids confirmed by code.</li>
      <li>Off-limits: the model refused ${pl('offLimits.refusedByModel')} of ${pl('offLimits.prompts')} itself; code blocked ${pl('offLimits.blockedByCode')} (an invented county) with a county guard added after seeing prompt v1's answers to these same prompts (post hoc).</li>
      <li>${pl('nemotronUsage.calls')} Nemotron calls in the selected version. No patient data was sent: inputs were public aggregates, model scenarios, published evidence and roadmap text. Plans are English drafts for a planner, labelled "drafted by Nemotron 3.5 Super VL; numbers checked".</li></ul>`)}
  </div>`, `${code(F.RES)} cascade; ${code(LP)} (post hoc); ${code(F.VAG)} sets.stress; ${code(F.PLAN)} summary; ${code('runs/laneB-step6.jsonl')}.`);

  // ---------------------------------------------------------------- stress-set detail
  const sl = (sys, s, f = 'k') => val(F.RES, `sets.stress.systems.${sys}.slices.${s}.${f}`);
  const srow = stress.map((s) => `<tr><td>${esc(s.label)}</td><td class="n">${s.k}/${s.n}</td><td class="n">${sl(s.sys, 'standard')}/${sl(s.sys, 'standard', 'n')}</td><td class="n">${sl(s.sys, 'heldout')}/${sl(s.sys, 'heldout', 'n')}</td><td class="n">${sl(s.sys, 'no_event')}/${sl(s.sys, 'no_event', 'n')}</td><td class="n">${val(F.RES, `sets.stress.systems.${s.sys}.vague_outcome.sent_to_person.k`)}/${val(F.RES, `sets.stress.systems.${s.sys}.vague_outcome.facts`)}</td><td class="n">${val(F.RES, `sets.stress.systems.${s.sys}.vague_outcome.invented_precise_date.k`)}</td></tr>`).join('');
  page('A10', 'The frozen stress set, slice by slice, and how every number is checked', `<div class="cols">
    ${sec('A10a', `Stress set: ${casStress.n} SYNTHETIC notes frozen before any system read them`, `
      <table><thead><tr><th>System</th><th>All</th><th>Standard</th><th>New phrasings</th><th>No event</th><th>Vague to a person</th><th>Vague given a precise day</th></tr></thead><tbody>${srow}</tbody></table>
      <ul><li>Exact match is strict: one wrong date, type or entry route makes the whole note wrong. Nemotron wrote the stress notes, so its score is optimistic.</li>
      <li>The success criterion was written before the set existed (${code('data/scribe/stress/preregistration.json')}); hashes of the stress set, resolver and adapters are re-checked in the results file.</li></ul>`, 'wide')}
    ${sec('A10b', 'Every number has a source', `<ul>
      <li>No language model writes a number in the county brief. A TypeSafe check passed <b>${val(F.CC, 'summary.true.SUPPORTED')} of ${val(F.CC, 'summary.true.n')}</b> true sentences (${val(F.CC, 'summary.true.UNCLEAR')} held back as unclear, ${val(F.CC, 'summary.true.NOT_SUPPORTED')} judged unsupported) and stopped all ${['direction', 'place', 'causal', 'number'].reduce((a, k) => a + get(F.CC, `summary.${k}.n`), 0)} deliberately corrupted ones.</li>
      <li>Finnish summaries: <b>${val(F.NAR, 'totals.kept')} of ${val(F.NAR, 'totals.generated')}</b> generated sentences shown; the rest dropped, never repaired.</li>
      <li>Every number in this deck is read from a JSON file by ${code('submission/deck/build.mjs')}; ${code('submission/deck/numbers.json')} lists each with its file and path.</li></ul>`)}
    ${sec('A10c', 'External facts', `<ul><li>${code(F.EV)}: every link re-opened and its retrieval time recorded. Literature values: ${code(F.LIT)}.</li></ul>`)}
  </div>`, `${code(F.RES)} sets.stress.systems; ${code(F.CC)} summary; ${code(F.NAR)} totals; ${code(F.EV)}.`);

  // ---------------------------------------------------------------- A11 + A12 + A13
  page('A11-A13', 'Safety net, comparability gate, compute and limits', `<div class="cols">
    <div>${sec('A11', 'Safety net and gate (SYNTHETIC)', `<ul>
      <li>Safety net, all 23 simulated areas (replay): <b>${val(F.SN, 'national.open_loops', (v) => nf(v))}</b> open loops, <b>${val(F.SN, 'national.overdue')}</b> overdue; ${val(F.SN, 'national.referral.overdue_at_sensitivity_days')} referrals still without a diagnosis at the 90-day sensitivity count. Rule ${code(val(F.SN, 'rule.version'))}, no model.</li>
      <li>Gate: NVIDIA FLARE ${val(F.GATE, 'flare.nvflare')} simulator, ${val(F.GATE, 'flare.sites')} sites, precision ${val(F.GATE, 'flare.precision')}; histogram edge at ${val(F.GATE, 'clock.histogram_edge_days')} days so whole days up to 42 count as within the placeholder. Median bias is computed in plain Python on the same site partitions (FLARE-ready, not run in FLARE). An earlier FLARE run on the four pathway intervals matched the central table in ${val(F.FLS, 'equivalence.none-p12.cells_ok')} of ${val(F.FLS, 'equivalence.none-p12.cells')} cells.</li>
      <li>FLARE ran in simulator mode on one laptop: no network between organisations, no site approval.</li></ul>`)}
    ${sec('A12', 'Compute and spend recorded in files', `<ul>
      <li>One Verda A100 80 GB: ${val(TF, 'machine_cost.hours', (v) => nf(v, 2))} h, USD ${val(TF, 'machine_cost.list_price_times_hours_usd', (v) => nf(v, 2))} at the list price (not the invoice), shared with the Evo 2 run. FLARE and MLX ran on this laptop at no cost.</li>
      <li>Nemotron on the Verda-hosted endpoint: ${val(NL, 'requests', (v) => nf(v))} reader requests; price not verified, recorded as unknown, not zero. TypeSafe Jev for the planner gate: USD ${val(JL, 'cost_usd', (v) => nf(v, 4))}.</li></ul>`)}</div>
    ${sec('A13', 'Limits', `<ul>
      <li>All patient-like data are SYNTHETIC: simulated people, and notes written by language models from six date forms; real notes use other phrasings. Labels were checked by models, not people. Nothing here has been tested on real clinical text.</li>
      <li>The 700-note test set had been read before; its results are post hoc. The frozen stress set is the number to trust.</li>
      <li>The scribe reads Finnish only; other languages go to manual entry. How many notes in a county are written in another language was not measured. Nemotron's model card does not name Finnish; planner plans are English drafts.</li>
      <li>Every time threshold is a placeholder. "Well-founded suspicion" needs a clinical definition and can be gamed.</li>
      <li>Second reader: every two-reader figure used Nemotron on the Verda-hosted endpoint, with SYNTHETIC notes only. In a pilot no patient data leaves the county: the second reader must run in a county-controlled environment (designed, not built) or a person does that step.</li>
      <li>Whether "recommendations" in the 2026 law covers the timing of pathway steps is unverified: confirm with STM and THL. Medical-device status to be confirmed with Fimea before a pilot (unverified). EU AI Act high-risk dates ${aiD('annex3')} and ${aiD('products')} are tracked.</li>
      <li>Evo 2 on BRCA1 is a research appendix outside the AstraZeneca pitch (${code('genomics/README.md')}).</li></ul>`)}
  </div>`, `${code(F.SN)} national, rule; ${code(F.GATE)} flare, clock; ${code(F.FLS)} equivalence; ${code(TF)} machine_cost; ${code(NL)}; ${code(JL)}; ${code(F.EV)} eu-ai-act-dates.`);

  return pages;
}
