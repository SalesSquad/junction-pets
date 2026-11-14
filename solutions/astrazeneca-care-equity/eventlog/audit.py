"""Audit produced artifacts without rerunning unchanged Monte Carlo experiments.

Run after run_all and after the unit tests have written
data/eventlog/tests-output.txt. Writes eventlog/RESULTS.md, the generated
blocks of DATA_COLLECTION.md (between <!-- STUDY:name:BEGIN/END --> markers) and
the execution receipt, all from the files on disk, and checks that
DATA_COLLECTION.md quotes the same numbers as data/eventlog/design-study-v1.json.
"""
import hashlib,json,re
from datetime import date
from pathlib import Path
import pyarrow.parquet as pq
from .parquet_io import read_dataset
from .schema import pathway_events,COUNTIES,PATHWAY_ORDER
from .validate import validate
from .log import log
from .run_all import write_json

CORE=['primary_care','diagnostic','treatment']
NAMES=dict(primary_care='primary care',diagnostic='diagnostic',treatment='treatment')
pct=lambda r:f"{round((r-1)*100)}%"
num=lambda x:'not reachable' if x is None else f'{x:,}'
cells_are=lambda k,n:f"{k} of {n} cells {'is' if k==1 else 'are'}"

def county_names(path='data/snapshot/public-v1.json'):
    return {r['id']:r['nameEn'].replace(' wellbeing services county','') for r in json.loads(Path(path).read_text())['regions']}

def document_rows(study):
    """Lines that DATA_COLLECTION.md section 2 must contain verbatim."""
    s=study['sample_sizes']; sd=s['sigma_by_interval']
    rows=['| county slower by | simulator step input (s = %.2f) | '%s['idealised_sigma']+' | '.join(f'{NAMES[k]} (s = {sd[k]:.3f})' for k in CORE)+f" | one step, cohort spread (s = {s['cohort_implied_sigma']:.3f}) |"]
    for r in s['rows']:
        rows.append(f"| {pct(r['slowdown'])} | {r['idealised']:,} | "+' | '.join(f'{r[k]:,}' for k in CORE)+f" | {r['cohort_spread']:,} |")
    return rows

def worst_detectable(c,period):
    """Smallest slowdown the county can detect in every interval (the widest interval decides)."""
    v=list(c[f'min_detectable_slowdown_{period}'].values())
    return None if any(x is None for x in v) else max(v)

def fam(study,layout,month,design='D3'):
    return next(x for x in study['familywise_null'] if x['design']==design and x['layout']==layout and x['month_share']==month)

def looks(study,layout,threshold):
    return next(x for x in study['repeated_looks_null'] if x['layout']==layout and x['threshold']==threshold)['any_false_flag_by_look']

def early_summary(study):
    """Median quarters from onset to the first flag (D3), looks counted in the family."""
    rows=[]
    for x in study['early_warning']:
        if x['design']=='D3':
            rows.append(dict(stage=x['stage'],slowdown=x['slowdown'],detected_by_quarter12=x['detected_by_quarter12'],
              median_quarters_to_detection=x['median_quarters_to_detection'],pre_onset_false_alarm_rate=x['pre_onset_false_alarm_rate']))
    return rows

def month_null(study):
    """Single-county null with half of the dates at month precision, in the order of small_county_null."""
    by={x['n']:x for x in study['small_county_null_month']}
    return [by[x['n']] for x in study['small_county_null']]

def ci_cell(row):
    lo,hi=row['ci95']
    return f"{row['familywise_false_positive_rate']:.3f} ({lo:.3f} to {hi:.3f})"

def small_null_reading(study):
    nominal=study['small_county_null'][0]['nominal_at_most']
    day=max(study['small_county_null'],key=lambda x:x['false_positive_rate_t'])
    tested=[x for x in study['small_county_null_month'] if x['false_positive_rate_among_tested'] is not None]
    untested=[x['n'] for x in study['small_county_null_month'] if x['counties_with_a_test_share']<.5]
    out=(f"With t quantiles the largest single-county rate at day precision is {day['false_positive_rate_t']:.5f} (n = {day['n']:,}; 95% interval {day['ci95_t'][0]:.5f} to {day['ci95_t'][1]:.5f}), "
         +('consistent with' if day['ci95_t'][0]<=nominal else 'above')+" the nominal bound. ")
    if tested:
        m=max(tested,key=lambda x:x['false_positive_rate_among_tested'])
        out+=(f"With half of the dates at month precision the largest rate among counties that are tested is {m['false_positive_rate_among_tested']:.5f} (n = {m['n']:,}; 95% interval "
              f"{m['ci95_among_tested'][0]:.5f} to {m['ci95_among_tested'][1]:.5f}), "+('consistent with' if m['ci95_among_tested'][0]<=nominal else 'above')+" the nominal bound. ")
    if untested:
        out+=f"Counties of {', '.join(f'{n:,}' for n in untested)} episodes are tested in fewer than half of the runs: month precision makes small counties silent rather than noisy."
    return out.strip()

def familywise_reading(study):
    cells=[x for x in study['familywise_null'] if x['design'] in ('D2','D3')]
    above=[x for x in cells if x['ci95'][0]>.05]
    worst=max(cells,key=lambda x:x['familywise_false_positive_rate'])
    where=lambda x:f"{x['design']}, {x['layout']}, {'half of the dates at month precision' if x['month_share'] else 'day precision'}"
    if not above:
        return (f"The largest of the {len(cells)} rates, {worst['familywise_false_positive_rate']:.3f} ({where(worst)}), has a 95% interval of {worst['ci95'][0]:.3f} to {worst['ci95'][1]:.3f}, "
                "which includes the 5% target: at this number of replications no cell is distinguishable from 5%.")
    return (f"{len(above)} of the {len(cells)} cells {'has' if len(above)==1 else 'have'} a 95% interval entirely above the 5% target: "
            +'; '.join(f"{x['familywise_false_positive_rate']:.3f} ({x['ci95'][0]:.3f} to {x['ci95'][1]:.3f}; {where(x)})" for x in above)
            +f". With {len(cells)} intervals at 95% one such result can arise by chance, so this is a warning that the family-wise rate may not be controlled there, not a proof; "
            "more replications were not run. Every D3 cell's interval includes or lies below 5%." if all(x['design']!='D3' for x in above) else
            f"{len(above)} of the {len(cells)} cells have a 95% interval entirely above the 5% target: "
            +'; '.join(f"{x['familywise_false_positive_rate']:.3f} ({x['ci95'][0]:.3f} to {x['ci95'][1]:.3f}; {where(x)})" for x in above)+". The family-wise rate is not controlled there.")

def extraction_block(study):
    """Section 4: the measured scribe error fed into the design study. Every number comes from the study file."""
    M=study['measured_text_extraction']; rows=M['rows']; profiles=M['profiles']
    sizes=sorted({x['n'] for x in rows}); nominal=next(x['nominal_at_most'] for x in rows if x['kind']=='null')
    P=lambda prof,n,k,f='stage_power':next(x[f] for x in rows if x['kind']=='planted' and x['profile']==prof and x['n']==n and x['stage']==k)
    N=lambda c,prof,n:next(x['county_false_positive_rate'] for x in rows if x['kind']=='null' and x['condition']==c and x['profile']==prof and x['n']==n)
    short=lambda p:p['system'].split(', ',1)[1] if ', ' in p['system'] else p['system']
    span=lambda vals:f"{min(vals):.3f}" if f"{min(vals):.3f}"==f"{max(vals):.3f}" else f"{min(vals):.3f} to {max(vals):.3f}"
    days=lambda v:f"{round(v,1)+0.:+.1f}"
    small=sizes[0]; big=sizes[-1]; main=profiles[0]
    meas_small=[P(p['profile'],small,k) for p in profiles for k in CORE]; conf_small=[P(None,small,k) for k in CORE]
    main_small=[P(main['profile'],small,k) for k in CORE]; main_big=[P(main['profile'],big,k) for k in CORE]
    bias=[P(p['profile'],n,k,'median_bias_days') for p in profiles for n in sizes for k in CORE]
    only=[N('measured_county_only',p['profile'],n) for p in profiles for n in sizes]
    not_enough=min(meas_small)<.8 or max(only)>.05
    lines=["**What the measured error does to the county indicator (design study, SYNTHETIC).** `eventlog/design_study.measured_extraction_study` replaces the assumed error rates of section 3 "
      "by the measured per-event error of the scribe. For every true event of a test note it takes the predicted event of the same type, if any, and the signed date error in days. "
      "Each simulated date then gets an error drawn independently from that list, and each event is lost with the measured share that was not found:",'',
      '| model and test notes | true events | found with the right type | exact date among those | wrong-date share | not found | largest error, days | extra predicted events | check |','| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
      *[f"| {p['system']} | {p['true_events']:,} | {p['events_with_type_found']:,} | {p['exact_dates']:,} | {p['wrong_date_share']:.3f} | {p['missing_share']:.3f} | {p['largest_absolute_error_days']} | "
        +('not counted' if p['extra_predicted_events'] is None else f"{p['extra_predicted_events']:,} (not modelled)")+f" | {p['check']} |" for p in profiles],'',
      f"A 30% slowdown planted in one interval of one county, {rows[0]['replications']:,} runs per cell. Located: share of runs in which the planted interval is the one flagged; bias: error of the county's median interval:",'',
      '| county episodes | dates | located: primary care / diagnostic / treatment | median bias, days | testable episodes, mean |','| --- | --- | --- | --- | --- |',
      *[f"| {n:,} | {'every event confirmed by a person' if p is None else short(p)} | "+' / '.join(f"{P(None if p is None else p['profile'],n,k):.3f}" for k in CORE)+' | '
        +' / '.join(days(P(None if p is None else p['profile'],n,k,'median_bias_days')) for k in CORE)+' | '
        +' / '.join(f"{P(None if p is None else p['profile'],n,k,'mean_complete_episodes'):.0f}" for k in CORE)+' |' for n in sizes for p in [None,*profiles]],'',
      f"No slowdown anywhere: share of runs in which the county is flagged (nominal at most {nominal:.5f}). Every event confirmed: "+', '.join(f"{N('confirmed',None,n):.3f} ({n:,} episodes)" for n in sizes)+'.','',
      '| model and test notes | county episodes | county and country extracted | only the county extracted, the rest from structured fields |','| --- | --- | --- | --- |',
      *[f"| {short(p)} | {n:,} | {N('measured_everywhere',p['profile'],n):.3f} | {N('measured_county_only',p['profile'],n):.3f} |" for p in profiles for n in sizes],'',
      f"Reading. With the selected version-2 adapter's error on Nemotron-written notes, a county of {small:,} episodes locates the planted interval in {span(main_small)} of runs instead of {span(conf_small)}, "
      f"and a county of {big:,} in {span(main_big)}. Across the three error profiles the median interval is off by {days(min(bias))} to {days(max(bias))} days at both county sizes; more episodes do not remove a bias. "
      f"A county whose dates come from text while the others come from structured fields is flagged in {span(only)} of runs when nothing is wrong. "
      +("So at the measured error, text extraction is not accurate enough to fill the county indicator without a person confirming every extracted date." if not_enough else
        "At the measured error the county indicator keeps most of its power; human confirmation is still required by the Gemma terms and by the lack of validation on real notes."),'',
      "Limits: "+' '.join(M['limits'])]
    return '\n'.join(lines)

def document_blocks(study):
    """Generated parts of DATA_COLLECTION.md sections 2, 3 and 4. Every number comes from the study file."""
    s=study['sample_sizes']; cal=study['interval_log_sd']; I=cal['intervals']; co=cal['cohort_check']
    c=study['sample_size_check_summary']; K=c['known_sd']; W=c['detector']
    g={(x['missingness'],x['month_share']):x for x in study['power_gap_by_condition']}
    where=lambda cell:f"{NAMES[cell['interval']]}, {pct(cell['slowdown'])} slowdown, n = {cell['n']}"
    wider=[NAMES[k] for k in CORE if I[k]['sd_log_duration']>s['idealised_sigma']]
    narrower=[NAMES[k] for k in CORE if I[k]['sd_log_duration']<=s['idealised_sigma']]
    blocks={}
    fa=co['fast']
    blocks['SIZES']='\n'.join([
      f"**Which `s`, and where each value comes from.** Computed from the cohort: in the Finnish DLBCL cohort (Kuitunen 2026, doi:{co['doi']}) the mean and median from symptom onset to treatment are "
      f"{co['published_mean_days']} and {co['published_median_days']} days on the public route and {fa['published_mean_days']} and {fa['published_median_days']} days on the private or occupational route. "
      f"A single log-normal with that mean and median has `s = sqrt(2 ln(mean/median))`: {co['published_implied_log_sd']:.3f} and {fa['published_implied_log_sd']:.3f}. "
      "Computed from the simulator: the per-interval values of the next paragraph, which the per-interval columns use. "
      f"Neither: the simulator's own step value `s = {s['idealised_sigma']}` is an input chosen near the cohort figures; "
      +("neither route reproduces it, so it is a modelling choice, not a derived number." if not co['step_sigma_reproduced_by_cohort'] else "one route reproduces it to two decimals.")
      +" The `s = %.2f` column is kept only to show what that input alone would give."%s['idealised_sigma'],'',
      f"`s = {s['idealised_sigma']}` describes one log-normal step in one population. None of the three intervals is that: each mixes the entry routes, primary care is a sum of two steps, "
      "and treatment is part of one step plus all of another. Mixing routes widens the log-duration, summing steps narrows it. "
      f"So `s` is measured for each interval in {cal['episodes']:,} simulated episodes (section 3; whole-day dates; a zero-day interval is logged as 0.5 day before taking logs, "
      f"which touches {I['primary_care']['zero_day_share']*100:.3f}%, {I['diagnostic']['zero_day_share']*100:.3f}% and {I['treatment']['zero_day_share']*100:.3f}% of the primary-care, diagnostic and treatment intervals; positive intervals are unchanged). "
      "Result: "+', '.join(f"{NAMES[k]} {I[k]['sd_log_duration']:.3f}" for k in CORE)+f". Wider than the single-step value: {', '.join(wider) or 'none'}; narrower: {', '.join(narrower) or 'none'}.",'',
      'Complete episodes per county and period (both dates of the interval known to the day), for one look, against a reference so large that its own error can be ignored:','',
      document_rows(study)[0],'| --- | --- | --- | --- | --- | --- |',*document_rows(study)[1:],'',
      f"The per-interval columns are SYNTHETIC: they follow from the simulator's assumptions ({cal['fast_route_share_assumed']*100:.0f}% of episodes on the fast route, the published step means, "
      f"log-SD {s['idealised_sigma']} per step, the diagnosis placed at 0.6 of the referral-to-specialist step, the multidisciplinary decision placed uniformly after it) and must be re-measured once real event data exist.",'',
      f"**The simulator is less spread than the cohort.** It reproduces the published mean but not the published median. On the public route, {co['episodes']:,} simulated episodes give a mean of "
      f"{co['simulated_mean_days']:.1f} days and a median of {co['simulated_median_days']:.1f} days from symptom onset to treatment (log-SD {co['simulated_log_sd']:.3f}), "
      f"against {co['published_mean_days']} and {co['published_median_days']} in the cohort (log-SD {co['published_implied_log_sd']:.2f}); on the private or occupational route {fa['episodes']:,} simulated episodes give "
      f"{fa['simulated_mean_days']:.1f} and {fa['simulated_median_days']:.1f} days (log-SD {fa['simulated_log_sd']:.3f}) against {fa['published_mean_days']} and {fa['published_median_days']}. Five independent steps add up to a total that is less skewed than the real one. "
      "Real intervals may therefore be more spread than the simulated ones, and every `n` grows with `s^2`. The last column of the table shows the size of that effect for one step.",'',
      f"**Against the rest of the country, not an infinite reference.** The detector compares a county with the other episodes of the same period, so `n(N - n)/N` takes the place of `n`, with `N` the national count of the period. "
      f"With {s['national_cases_assumed']:,} new cases a year (an assumption for sizing, not an observed incidence):",'',
      '| county slower by | period | primary care | diagnostic | treatment |','| --- | --- | --- | --- | --- |',
      *[f"| {pct(r['slowdown'])} | {'one year' if period=='year' else 'one quarter'} (N = {s['national_cases_assumed']//(1 if period=='year' else 4):,}) | "
        +' | '.join(num(r['rest_of_country'][period][k]) for k in CORE)+' |' for period in ['year','quarter'] for r in s['rows']],'',
      '"Not reachable" means no county size gives the power, because the rest of the country is then too small a comparator.'])
    ro=lambda period,kind:[x for x in study['rest_of_country_check'] if x['period']==period and x['county_n_kind']==kind]
    rng=lambda rows:f"{min(x['empirical_power'] for x in rows):.3f} to {max(x['empirical_power'] for x in rows):.3f}"
    worst=max(g.values(),key=lambda x:x['largest_gap']); wc=worst['largest_gap_cell']
    untest=sum(1 for x in study['design_grid'] if x['design']=='D3' and x['expected_testable_episodes']<study['minimum_testable_episodes'])
    d3=sum(1 for x in study['design_grid'] if x['design']=='D3')
    sn=study['small_county_null']; layouts=list(dict.fromkeys(x['layout'] for x in study['familywise_null']))
    blocks['CHECKS']='\n'.join([
      f"**How well the formula holds.** Simulated at exactly the per-interval `n` of the first table, {c['replications']:,} counties per cell, {c['cells']} cells, target power {c['target_power']:.2f}:",'',
      f"- With the measured `s` treated as known, as the formula assumes, power is {K['min_power']:.4f} to {K['max_power']:.4f}. The largest gap to the formula is {K['largest_gap']:.4f} ({where(K['largest_gap_cell'])}); "
      f"{cells_are(K['cells_beyond_3_monte_carlo_se'],c['cells'])} more than three Monte Carlo standard errors away.",
      f"- The detector as actually run estimates the variance inside the county and uses Student t critical values. Its power is {W['min_power']:.4f} to {W['max_power']:.4f}. "
      f"The largest gap is {W['largest_gap']:.4f} ({where(W['largest_gap_cell'])}), and {cells_are(W['cells_beyond_3_monte_carlo_se'],c['cells'])} more than three Monte Carlo standard errors away. "
      "The formula uses a normal quantile, so it is a little optimistic for small `n`.",
      f"- With the rest of the country as comparator, fully simulated ({study['rest_of_country_check'][0]['replications']:,} countries per cell): at the `n` of the first table the power is {rng(ro('quarter','infinite_reference_n'))} "
      f"for a 20% slowdown against one quarter and {rng(ro('year','infinite_reference_n'))} for a 10% slowdown against one year; at the `n` of the second table it is {rng(ro('quarter','rest_of_country_n'))} and {rng(ro('year','rest_of_country_n'))}.",
      f"- Across the wider design grid (n from 100 to 2,000, {study['replications']:,} simulated counties per cell) the largest gap with day-precision dates is {g[(0.,0.)]['largest_gap']:.4f} with no missing dates and "
      f"{g[(.2,0.)]['largest_gap']:.4f} with 20% of dates missing; of the cells with formula power between 0.02 and 0.98, {g[(0.,0.)]['cells_beyond_3_monte_carlo_se']} of {g[(0.,0.)]['cells_with_analytic_power_between_0_02_and_0_98']} and "
      f"{g[(.2,0.)]['cells_beyond_3_monte_carlo_se']} of {g[(.2,0.)]['cells_with_analytic_power_between_0_02_and_0_98']} are more than three Monte Carlo standard errors away.",'',
      "**Month-precision dates cost episodes.** A date known only to the month is an interval, not a point. The earlier version of the detector put it at mid-month and tested anyway; its power then fell far below the formula"
      +(f" (largest gap {second_revision()[1]['largest_absolute_power_gap']:.4f} in that version's run, `runs/eventlog.jsonl`)" if second_revision()[1] else '')+". "
      "The detector now tests an interval only when both of its dates are known to the day. With a share `q` of dates known to the month only, `(1 - q)^2` of the intervals remain: divide `n` by `(1 - q)^2`. "
      f"With half of the dates at month precision a quarter of the intervals remain, so four times as many episodes are needed. With that correction in the formula the largest gap in the month-precision cells is "
      f"{g[(0.,.5)]['largest_gap']:.4f} with no missing dates and {g[(.2,.5)]['largest_gap']:.4f} with 20% missing "
      f"(largest over all conditions: {worst['largest_gap']:.4f}; {NAMES[wc['stage']]}, n = {wc['n']}, {pct(wc['slowdown'])} slowdown, {wc['planted_test_power']:.3f} of simulations against {wc['analytic_power']:.3f} from the formula). "
      f"A county needs at least {study['minimum_testable_episodes']} testable episodes in an interval to be tested at all; {untest} of the {d3} core-four cells of the grid expect fewer and are not tested. "
      "An interval-censored analysis could use month-precision dates; this study does not do one. That remains the strongest argument for recording `date_precision = DAY`.",'',
      f"**False alarms when nothing is wrong.** One county against a large reference, {sn[0]['replications']:,} simulated counties per size and precision, any of its three tests rejecting (nominal at most {sn[0]['nominal_at_most']:.5f}). "
      "With half of the dates at month precision only the day-precision pairs are tested, so small counties are often not tested at all:",'',
      '| county n | day precision, t quantiles (as run) | day precision, normal quantile (first implementation) | half month precision, all counties | half month precision, among counties with a test (share with a test) |','| --- | --- | --- | --- | --- |',
      *[f"| {x['n']:,} | {x['false_positive_rate_t']:.5f} | {x['false_positive_rate_normal_quantile']:.5f} | {m['false_positive_rate_t']:.5f} | "
        +('no county tested (0.000)' if m['false_positive_rate_among_tested'] is None else f"{m['false_positive_rate_among_tested']:.5f} ({m['counties_with_a_test_share']:.3f})")+' |'
        for x,m in zip(sn,month_null(study))],'',
      small_null_reading(study),'',
      f"All 23 counties tested at once against the rest of the country, share of {study['replications']:,} simulated countries with at least one false flag (target 0.05; 95% interval in brackets), "
      "for the core four (D3, 69 tests) and for two timestamps (D2, 23 tests), with day-precision dates and with half of the dates at month precision:",'',
      '| county layout | D3, day precision | D3, half month precision | D2, day precision | D2, half month precision |','| --- | --- | --- | --- | --- |',
      *[f"| {lay} | {ci_cell(fam(study,lay,0.))} | {ci_cell(fam(study,lay,.5))} | {ci_cell(fam(study,lay,0.,'D2'))} | {ci_cell(fam(study,lay,.5,'D2'))} |" for lay in layouts],'',
      familywise_reading(study)])
    L0=study['repeated_looks_null'][0]['layout']; L1=study['repeated_looks_null'][2]['layout']; n_looks=s['planned_looks']
    r20=next(r for r in s['rows'] if r['slowdown']==1.2)
    blocks['LOOKS']='\n'.join([
      f"**Repeated looks and strata are part of the family.** `a = 0.05/69` covers one look at one stratum: 23 counties x 3 intervals, once. It does not cover a quarterly report repeated over time, and it does not cover separate analyses by cancer site. "
      f"Simulated with no slowdown anywhere, quarterly looks on a rolling four-quarter window ({study['replications']:,} countries):",'',
      f'| county layout | threshold | false flag somewhere at the first look | within 4 looks | within 8 looks | within {n_looks} looks |','| --- | --- | --- | --- | --- | --- |',
      *[f"| {lay} | {'one look, a = 0.05/69' if thr=='single_look' else f'{n_looks} looks counted, a = 0.05/(69 x {n_looks})'} | "
        +' | '.join(f"{looks(study,lay,thr)[i]['rate']:.3f}" for i in [0,3,7,n_looks-1])+' |' for lay in [L0,L1] for thr in ['single_look','looks_in_family']],'',
      f"Counting the planned looks in the family (Bonferroni over looks, an upper bound because rolling windows overlap) keeps the false-alarm probability over the horizon near 5%. It costs sample size: for a 20% slowdown the per-interval `n` rises from "
      +', '.join(f"{r20[k]:,}" for k in CORE)+' to '+', '.join(f"{r20['with_planned_looks'][k]:,}" for k in CORE)
      +f" (primary care, diagnostic, treatment) with {n_looks} looks. The early-warning experiment of section 3 uses that threshold. A sequential boundary calibrated by simulation would cost less; it is not implemented. "
      "Each cancer-site stratum analysed separately multiplies the family again."])
    names=county_names(); cd=study['county_detectability']
    cell=lambda c,period:(lambda v:'not reachable' if v is None else f"{(v-1)*100:.0f}%")(worst_detectable(c,period))
    reach=lambda period,r:sum(1 for c in cd if worst_detectable(c,period) is not None and worst_detectable(c,period)<=r)
    blocks['COUNTIES']='\n'.join([
      f"**Consequence, county by county.** The table takes {s['national_cases_assumed']:,} new cases a year (an assumption, not an observed incidence), shares them by {study['county_population_year']} population, "
      "and gives the smallest slowdown each county could detect in every interval with power 0.8 at one look (`a = 0.05/69`, rest of the country as comparator, every date known to the day, no missing dates). SYNTHETIC planning figures.",'',
      '| county | assumed cases a year | smallest slowdown detectable in one quarter | in one year |','| --- | --- | --- | --- |',
      *[f"| {names.get(c['county'],c['county'])} | {c['assumed_annual_cases']:,} | {cell(c,'quarter')} | {cell(c,'year')} |" for c in sorted(cd,key=lambda c:-c['assumed_annual_cases'])],'',
      f"So under these assumptions {reach('quarter',1.2)} of {len(cd)} counties could detect a 20% slowdown within one quarter, {reach('year',1.2)} within one year, and {reach('year',1.1)} could detect 10% within one year. "
      f"The smallest county has about {min(c['assumed_cases_per_quarter'] for c in cd):.0f} cases a quarter. Quarterly all-cancer reporting is informative for slowdowns of roughly "
      f"{cell(max(cd,key=lambda c:c['assumed_annual_cases']),'quarter')} or more in the largest county and {cell(min(cd,key=lambda c:c['assumed_annual_cases']),'quarter')} or more in the smallest; "
      "a rolling twelve months brings those to "
      f"{cell(max(cd,key=lambda c:c['assumed_annual_cases']),'year')} and {cell(min(cd,key=lambda c:c['assumed_annual_cases']),'year')}. Missing or month-precision dates, repeated looks and site strata all push these figures up. "
      "Real case counts by county are not in this repository, so these rows describe the assumption, not the counties."])
    blocks['EXTRACTION']=extraction_block(study)
    return blocks

def render_document(doc,study):
    for name,text in document_blocks(study).items():
        pattern=re.compile(rf'<!-- STUDY:{name}:BEGIN -->.*?<!-- STUDY:{name}:END -->',re.S)
        if not pattern.search(doc): raise ValueError(f'DATA_COLLECTION.md has no STUDY:{name} block')
        doc=pattern.sub(lambda _:f'<!-- STUDY:{name}:BEGIN -->\n{text}\n<!-- STUDY:{name}:END -->',doc)
    return doc

def document_numbers(study):
    """Numbers quoted in the hand-written prose of DATA_COLLECTION.md section 3."""
    return [f"{study['sample_validation']['episodes']:,} episodes, {study['sample_validation']['events']:,} events",
      f"{study['interval_log_sd']['episodes']:,} calibration episodes",f"{study['binomial_n']} episodes"]

def first_implementation():
    """Numbers of the superseded first implementation, read from its own audit
    line in the append-only run log (the files themselves were overwritten)."""
    for line in Path('runs/eventlog.jsonl').read_text().splitlines():
        r=json.loads(line)
        if r['step']=='final_artifact_audit' and 'chronology_violations' in r['metrics']: return r['ts'],r['metrics']
    return None,None

def second_revision():
    """Last audit line of the second revision (normal quantile, month midpoints tested, one-look family)."""
    found=(None,None)
    for line in Path('runs/eventlog.jsonl').read_text().splitlines():
        r=json.loads(line)
        if r['step']=='final_artifact_audit' and 'largest_gap_at_per_interval_n_detector' in r['metrics'] and 'max_familywise_fpr_any_layout' not in r['metrics']: found=(r['ts'],r['metrics'])
    return found

def results_markdown(summary,study):
    cal=study['interval_log_sd']; I=cal['intervals']; c=study['sample_size_check_summary']; co=cal['cohort_check']; s=study['sample_sizes']
    blocks=document_blocks(study)
    lines=['# Executed results','',
      'Everything here is SYNTHETIC: simulated episodes under stated assumptions, not Finnish patients. Not for clinical use.',
      'Generated by `eventlog/audit.py` from `data/eventlog/design-study-v1.json` and the Parquet sample on disk; no number is typed by hand.','',
      *[f'- {k}: {v}' for k,v in summary.items()],'',
      '## Pathway order','',f'`{PATHWAY_ORDER}`','',
      f"Chronology violations in the validated Parquet sample: {summary['chronology_violations']}. In the {cal['episodes']:,}-episode calibration sample rounded to whole days: {cal['whole_day_chronology_violations']}. Ties are allowed.",'',
      '## Standard deviation of log-duration per interval','',
      f"{cal['episodes']:,} simulated episodes. {cal['definition']}",'',
      '| interval | SD of log-duration | standard error | skewness | zero-day share | mean days | SD fast route | SD public route |','| --- | --- | --- | --- | --- | --- | --- | --- |',
      *[f"| {NAMES[k]} | {I[k]['sd_log_duration']:.4f} | {I[k]['sd_standard_error']:.5f} | {I[k]['skewness_log_duration']:+.3f} | {I[k]['zero_day_share']:.6f} | {I[k]['mean_days']:.2f} | {I[k]['by_route']['fast']['sd_log_duration']:.4f} | {I[k]['by_route']['public']['sd_log_duration']:.4f} |" for k in CORE],'',
      f"Idealised value (one log-normal step): {s['idealised_sigma']}.",'',
      '## Cohort check','',
      f"Public route, {co['interval']}, {co['episodes']:,} simulated episodes: mean {co['simulated_mean_days']:.1f} days, median {co['simulated_median_days']:.1f} days, log-SD {co['simulated_log_sd']:.4f}. "
      f"Published (doi:{co['doi']}): mean {co['published_mean_days']}, median {co['published_median_days']}, implied log-SD {co['published_implied_log_sd']:.4f}. {co['reading']}",'',
      f"Private or occupational route, {co['fast']['episodes']:,} simulated episodes: mean {co['fast']['simulated_mean_days']:.1f} days, median {co['fast']['simulated_median_days']:.1f} days, log-SD {co['fast']['simulated_log_sd']:.4f}. "
      f"Published: mean {co['fast']['published_mean_days']}, median {co['fast']['published_median_days']}, implied log-SD {co['fast']['published_implied_log_sd']:.4f}.",'',
      'Where each `s` comes from:','',*[f"- {k.replace('_',' ')}: {v}" for k,v in co['sigma_sources'].items()],'',
      '## Required complete episodes per county and period','',s['formula'],'',
      *document_rows(study)[:1],'| --- | --- | --- | --- | --- | --- |',*document_rows(study)[1:],'',
      f"Rest of the country as comparator: {s['rest_of_country_formula']}.",'',
      '| county slower by | period | primary care | diagnostic | treatment |','| --- | --- | --- | --- | --- |',
      *[f"| {pct(r['slowdown'])} | {period} (N = {s['national_cases_assumed']//(1 if period=='year' else 4):,}) | "+' | '.join(num(r['rest_of_country'][period][k]) for k in CORE)+' |' for period in ['year','quarter'] for r in s['rows']],'',
      f"With {s['planned_looks']} planned looks counted in the family (a = 0.05/(69 x {s['planned_looks']}), infinite reference):",'',
      '| county slower by | primary care | diagnostic | treatment |','| --- | --- | --- | --- |',
      *[f"| {pct(r['slowdown'])} | "+' | '.join(f"{r['with_planned_looks'][k]:,}" for k in CORE)+' |' for r in s['rows']],'',
      '## Analytic versus simulated power at exactly the per-interval n','',
      f"{c['replications']:,} replications per cell. `known SD` is the formula's own setting (z-test with the measured SD); `detector` is the Welch test as run (variance estimated in the county, t quantiles). Monte Carlo SE = {c['monte_carlo_se']}.",'',
      '| interval | slowdown | n | analytic | known SD | absolute gap | gap / MC SE | detector | signed gap | gap / MC SE |','| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |',
      *[f"| {NAMES[x['interval']]} | {pct(x['slowdown'])} | {x['n']:,} | {x['analytic_power']:.4f} | {x['known_sd_power']:.4f} | {x['known_sd_gap']:.4f} | {x['known_sd_gap_in_monte_carlo_se']:.2f} | {x['empirical_power']:.4f} | {x['signed_gap']:+.4f} | {x['gap_in_monte_carlo_se']:.2f} |" for x in study['sample_size_check']],'',
      '## Power with the rest of the country as comparator','',
      f"{study['rest_of_country_check'][0]['replications']:,} fully simulated countries per cell; the first n episodes are the county with the planted slowdown, the other N - n are the comparator.",'',
      '| period (N) | interval | slowdown | county n | which n | analytic, two-sample | analytic, infinite reference | simulated (95% interval) |','| --- | --- | --- | --- | --- | --- | --- | --- |',
      *[f"| {x['period']} ({x['national_episodes']:,}) | {NAMES[x['interval']]} | {pct(x['slowdown'])} | {x['n']:,} | {'first table' if x['county_n_kind']=='infinite_reference_n' else 'rest-of-country formula'} | {x['analytic_power_two_sample']:.4f} | {x['analytic_power_infinite_reference']:.4f} | {x['empirical_power']:.4f} ({x['empirical_power_ci95'][0]:.3f} to {x['empirical_power_ci95'][1]:.3f}) |" for x in study['rest_of_country_check']],'',
      '## Analytic versus simulated power in the design grid (D3 cells)','',
      f"{study['replications']} replications per cell; planted interval's own test against the per-interval analytic power. Testable n = n (1 - m)^2 (1 - q)^2 for a share m of missing dates and a share q of month-precision dates.",'',
      '| missingness | month-precision share | cells | largest gap | where | mean gap | cells beyond 3 MC SE (of those with analytic power 0.02 to 0.98) | largest gap, first implementation definition |','| --- | --- | --- | --- | --- | --- | --- | --- |',
      *[f"| {g['missingness']} | {g['month_share']} | {g['cells']} | {g['largest_gap']:.4f} | {NAMES[g['largest_gap_cell']['stage']]}, n = {g['largest_gap_cell']['n']}, {pct(g['largest_gap_cell']['slowdown'])}: simulated {g['largest_gap_cell']['planted_test_power']:.4f}, analytic {g['largest_gap_cell']['analytic_power']:.4f} | {g['mean_gap']:.4f} | {g['cells_beyond_3_monte_carlo_se']} of {g['cells_with_analytic_power_between_0_02_and_0_98']} | {g['largest_idealised_gap']:.4f} |" for g in study['power_gap_by_condition']],'',
      '## False alarms when nothing is wrong','',*blocks['CHECKS'].split('\n')[blocks['CHECKS'].split('\n').index(next(l for l in blocks['CHECKS'].split('\n') if l.startswith('**False alarms'))):],'',
      '## Repeated looks','',*blocks['LOOKS'].split('\n'),'',
      '## Early warning (D3, looks counted in the family)','',
      f"A slowdown starts in quarter 5 of 12 in one county of 250 episodes a quarter; each quarter the last four quarters are tested at a = 0.05/(69 x {s['planned_looks']}).",'',
      '| interval | slowdown | detected by quarter 12 | median quarters from onset to first flag | pre-onset false alarm (4 looks) |','| --- | --- | --- | --- | --- |',
      *[f"| {NAMES[x['stage']]} | {pct(x['slowdown'])} | {x['detected_by_quarter12']:.3f} | {'not reached in half of the runs' if x['median_quarters_to_detection'] is None else f'{x['median_quarters_to_detection']:.0f}'} | {x['pre_onset_false_alarm_rate']:.4f} |" for x in early_summary(study)],'',
      '## County by county','',*blocks['COUNTIES'].split('\n'),'',
      '## Measured extraction error fed back','',*blocks['EXTRACTION'].split('\n'),'',
      '## Findings','',*[f'- {x}' for x in study['findings']]]
    ts,old=first_implementation(); ts2,second=second_revision()
    if old:
        lines+=['','## What changed from earlier implementations','',
          f"First-implementation numbers are read from its audit line in `runs/eventlog.jsonl` ({ts}); second-revision numbers from its last audit line ({ts2}).",'',
          '| quantity | first implementation | second revision | now |','| --- | --- | --- | --- |',
          f"| chronology violations in the 20,000-episode sample | {old['chronology_violations']} | {second['chronology_violations'] if second else 'n/a'} | {summary['chronology_violations']} |",
          f"| largest analytic-versus-simulated power gap, first definition (any of the three tests rejects, s = {s['idealised_sigma']}) | {old['largest_absolute_power_gap']:.4f} | n/a | {study['largest_idealised_power_gap']:.4f} |",
          f"| largest gap at exactly the per-interval n, detector as run | not measured | {second['largest_gap_at_per_interval_n_detector']:.4f} (normal quantile) | {c['detector']['largest_gap']:.4f} (t quantile) |" if second else '',
          f"| largest gap in the grid, all observation conditions | not measured | {second['largest_absolute_power_gap']:.4f} (month midpoints tested) | {study['largest_absolute_power_gap']:.4f} (month-precision pairs not tested, counted out of n) |" if second else '',
          f"| family-wise false-positive rate, one look | not measured | {second['max_familywise_fpr']:.3f} (23 x 250, day precision only) | {summary['max_familywise_fpr_any_layout']:.3f} (largest over three layouts and two precisions) |" if second else '',
          f"| false flag somewhere within {s['planned_looks']} quarterly looks | not measured | not measured | {summary['false_flag_within_planned_looks_single_look_threshold']:.3f} with the one-look threshold, {summary['false_flag_within_planned_looks_looks_in_family']:.3f} with the looks counted |"]
    return '\n'.join(l for l in lines if l is not None)+'\n'

def artifacts(out=Path('data/eventlog')):
    """Re-read and re-validate what is on disk; nothing is taken from memory."""
    study=json.loads((out/'design-study-v1.json').read_text())
    roster=json.loads((out/'sample-roster.json').read_text());table=read_dataset(out/'sample')
    report=validate(table,roster,date(2026,12,31)).to_dict()
    files=list((out/'sample').rglob('*.parquet'))
    c=study['sample_size_check_summary']; L0=study['repeated_looks_null'][0]['layout']
    summary=dict(episodes=len(roster),events=table.num_rows,county_partitions=len(files),
        chronology_violations=report['reversed_pairs'],sample_valid=report['valid'],
        grid_cells=len(study['design_grid']),replications=study['replications'],
        early_warning_rows=len(study['early_warning']),extraction_rows=len(study['text_extraction']),
        sd_log_duration=study['sample_sizes']['sigma_by_interval'],
        sample_size_check_replications=c['replications'],
        largest_gap_at_per_interval_n_known_sd=c['known_sd']['largest_gap'],
        largest_gap_at_per_interval_n_detector=c['detector']['largest_gap'],
        largest_power_gap_day_precision_complete=study['largest_power_gap_day_precision_complete'],
        largest_absolute_power_gap=study['largest_absolute_power_gap'],
        max_familywise_fpr_any_layout=max(x['familywise_false_positive_rate'] for x in study['familywise_null']),
        false_flag_within_planned_looks_single_look_threshold=looks(study,L0,'single_look')[-1]['rate'],
        false_flag_within_planned_looks_looks_in_family=looks(study,L0,'looks_in_family')[-1]['rate'],
        max_single_county_null_month_precision_among_tested=max((x['false_positive_rate_among_tested'] for x in study['small_county_null_month'] if x['false_positive_rate_among_tested'] is not None),default=None),
        measured_extraction_wrong_date_share={p['profile']:p['wrong_date_share'] for p in study['measured_text_extraction']['profiles']},
        measured_extraction_min_localisation_smallest_county=min(x['stage_power'] for x in study['measured_text_extraction']['rows'] if x['kind']=='planted' and x['condition']=='measured_everywhere' and x['n']==min(r['n'] for r in study['measured_text_extraction']['rows'])),
        measured_extraction_localisation_confirmed_smallest_county=min(x['stage_power'] for x in study['measured_text_extraction']['rows'] if x['kind']=='planted' and x['condition']=='confirmed' and x['n']==min(r['n'] for r in study['measured_text_extraction']['rows'])),
        measured_extraction_county_only_null_rate=max(x['county_false_positive_rate'] for x in study['measured_text_extraction']['rows'] if x['kind']=='null' and x['condition']=='measured_county_only'))
    return study,roster,table,report,files,summary

def write_results(out=Path('data/eventlog')):
    study,_,_,_,_,summary=artifacts(out)
    Path('eventlog/RESULTS.md').write_text(results_markdown(summary,study))
    doc=Path('DATA_COLLECTION.md'); doc.write_text(render_document(doc.read_text(),study))
    return summary

def main():
    out=Path('data/eventlog'); study,roster,table,report,files,summary=artifacts(out)
    previous=json.loads((out/'validation-report.json').read_text())
    assert all(previous[k]==v for k,v in report.items())
    assert report['reversed_pairs']==0 and report['valid'], 'sample must validate with zero chronology violations'
    assert study['sample_validation']['chronology_violations']==0 and study['interval_log_sd']['whole_day_chronology_violations']==0
    assert study['pathway_order']==PATHWAY_ORDER==report['pathway_order']
    assert len(roster)==20000 and len({r['episode_id'] for r in roster})==20000
    assert set(table['county'].to_pylist())==set(COUNTIES)
    assert all(table['synthetic'].to_pylist())
    assert table.schema.equals(pathway_events)
    assert all(pq.ParquetFile(f).metadata.row_group(0).column(0).compression=='ZSTD' for f in files)
    assert study['replications']>=400 and len(study['design_grid'])==960
    assert all(r['stage_power'] is None for r in study['design_grid'] if r['design'] in ['D1','D2'])
    # One look, every layout and precision: the family-wise rate must stay near the 5% target.
    assert all(r['familywise_false_positive_rate']<.08 for r in study['familywise_null']), 'family-wise null rate above 0.08'
    # Repeated looks: the corrected threshold must hold the horizon near 5%; the one-look threshold is reported, not required.
    assert all(x['any_false_flag_by_look'][-1]['rate']<.08 for x in study['repeated_looks_null'] if x['threshold']=='looks_in_family')
    assert len(study['early_warning'])==48 and len(study['text_extraction'])==144 and len(study['sample_size_check'])==12
    assert len(study['small_county_null_month'])==len(study['small_county_null'])==5
    assert {x['condition'] for x in study['measured_text_extraction']['rows']}=={'confirmed','measured_everywhere','measured_county_only'}
    for prof in study['measured_text_extraction']['profiles']:
        for src,sha in prof['sources'].items():
            assert hashlib.sha256(Path(src).read_bytes()).hexdigest()==sha, f'{src} changed since the study ran: rerun eventlog.run_all'
    assert len(study['county_detectability'])==23 and len(study['rest_of_country_check'])==12
    doc=Path('DATA_COLLECTION.md').read_text()
    assert doc==render_document(doc,study), 'DATA_COLLECTION.md generated blocks are stale: run eventlog.audit.write_results()'
    missing=[x for x in document_rows(study)+document_numbers(study) if x not in doc]
    assert not missing, f'DATA_COLLECTION.md does not quote the study: {missing}'
    assert PATHWAY_ORDER in ' '.join(doc.replace('`','').split())
    tests=(out/'tests-output.txt').read_text()
    ran=re.search(r'^Ran (\d+) tests? in',tests,re.M)
    assert ran and re.search(r'^OK$',tests,re.M) and not re.search(r'^(FAILED|ERROR)',tests,re.M), 'unit tests must have passed'
    summary['unit_tests_passed']=int(ran.group(1))
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('eventlog').glob('*.py'))+[Path('eventlog/tests/test_eventlog.py')]}
    hashes['DATA_COLLECTION.md']=hashlib.sha256(doc.encode()).hexdigest()
    hashes['data/snapshot/public-v1.json']=hashlib.sha256(Path('data/snapshot/public-v1.json').read_bytes()).hexdigest()
    hashes['data/eventlog/design-study-v1.json']=hashlib.sha256((out/'design-study-v1.json').read_bytes()).hexdigest()
    write_json(out/'execution-receipt.json',dict(synthetic=True,summary=summary,source_sha256=hashes,
      tests_output=tests,
      limits=['All data are simulated under stated assumptions; nothing is a Finnish observation and nothing is for clinical use.',
        'The sample-size formula is a normal approximation with the measured per-interval log-SD; the detector estimates the variance in each county and uses t quantiles, and the measured departure at the tabulated n is reported, not removed.',
        'Month-precision dates are not used by the test; the formula counts them out of n. No interval-censored analysis is done.',
        'Repeated looks are handled by a Bonferroni bound over the planned looks, not by a calibrated sequential boundary. Cancer-site strata are not in the family.',
        'The simulator matches the published step means but not the published median of the whole pathway; real intervals may be more spread.',
        'The per-interval SDs depend on the assumed route shares and step distributions, and county sizes on an assumed national case count; real data will give other values.',
        'The measured extraction experiment uses the scribe adapters\' per-event errors on synthetic, model-labelled notes, drawn independently per date; it is not a measurement on clinical text.',
        'No git operations.']))
    Path('eventlog/RESULTS.md').write_text(results_markdown(summary,study))
    log('final_artifact_audit','eventlog/.venv/bin/python -m eventlog.audit',
        inputs=[str(out/'sample'),str(out/'design-study-v1.json'),str(out/'tests-output.txt'),'DATA_COLLECTION.md'],
        outputs=[str(out/'execution-receipt.json'),'eventlog/RESULTS.md'],metrics=summary)
    print(json.dumps(summary))

if __name__=='__main__': main()
