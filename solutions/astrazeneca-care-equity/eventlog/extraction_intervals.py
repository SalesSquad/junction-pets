"""The current scribe's measured interval errors, as is and with the product's code date resolver,
fed into the county detector. SYNTHETIC notes, simulated counties; nothing here is a Finnish observation.

Profiles (measured). For every pair of DAY-precision gold events in one held-out test note of the
C-270m-all-v2data adapter (500 Nemotron-written and 200 Haiku-written notes), the pair is found when
both endpoints were predicted with the right type and DAY precision; its error is the predicted span
minus the true span. Errors that share an anchor inside a note therefore stay correlated. The matching
of predicted to gold events is the diagnosis code's (runs/diagnose/diagnose.py: analyse, intervals).
Arm 'off' uses the stored predictions as they are; arm 'A' first applies the product's frozen relative
date resolver (scribe/v3/resolve.py, repair) to them. The recomputed pairs must equal the stored lists
in runs/diagnose/ that runs/diagnose/simulate.py used, or the study stops.

Extra predicted events (measured per writer and type, effect modelled). An extra is a predicted event
left over after every gold event of its note was matched. Each note carries extras_T / notes extras of
type T; an episode whose nine events are spread over notes like the test notes spans 9 x notes / gold
events notes, so its slot T receives at least one extra with probability 1 - exp(-9 extras_T / gold
events). eventlog.intervals.derive computes an interval only from exactly one start and one end event,
so a slot with an extra makes both core intervals that use it underivable. Not modelled: an extra that
stands in for a true event missing from the record (it would carry a wrong date).

Simulation: as in runs/diagnose/simulate.py, each core interval of a simulated episode gets an error
drawn from the profile's found pairs and is lost with the profile's lost share; negative spans are
excluded by the detector, never repaired. The detector, the reference pool and the simulator are the
repository's own (eventlog/).
"""
import hashlib, importlib.util, json
from collections import Counter
from math import exp, sqrt
from pathlib import Path
import numpy as np
from .detect import log_days, moments, test_moments
from .schema import ENDPOINTS, EVENT_TYPES, INTERVALS
from .simulate import plant
from .aggregate import wilson

ROOT = Path(__file__).resolve().parents[1]
CORE = INTERVALS[:3]
RUN = 'C-270m-all-v2data'
PREDICTIONS = 'data/scribe/v3/student/C-270m-all-v2data/eval-test.json'
LABELS = ['data/scribe/v3/dataset/test_nemotron.parquet', 'data/scribe/v3/dataset/test_haiku.parquet']
DIAGNOSE = 'runs/diagnose/diagnose.py'
RESOLVER = 'scribe/v3/resolve.py'
LEXICON = 'scribe/v3/lexicon.py'
FREEZE = 'data/scribe/v4/resolver/freeze.json'
REPRODUCE = 'data/scribe/v4/resolver/reproduce-v1.json'
STORED = {'off': 'runs/diagnose/intervals-C-270m-all-v2data.json', 'A': 'runs/diagnose/intervals-C-270m-all-v2data-resolved.json'}
IMPACT = 'runs/diagnose/interval-impact-v1.json'
IMPACT_NAMES = {'off': 'C-270m-all-v2data as is', 'A': 'C-270m-all-v2data + code resolver'}
ARMS = {'off': 'as is', 'A': 'with the code date resolver (arm A)'}
WRITERS = ('all', 'nemotron', 'haiku')


def _sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def note_pairs(arm, diagnose=None, resolver=None, gold=None):
    """Within-note interval pairs and extra predicted events of every test note under one resolver arm."""
    D = diagnose or _module('eventlog_diagnose', DIAGNOSE)
    R = resolver or _module('eventlog_resolver', RESOLVER)
    gold = gold or D.load_gold()
    run = json.loads((ROOT / PREDICTIONS).read_text())
    pairs, extras, gold_events, notes = [], Counter(), Counter(), Counter()
    for split in ('test_nemotron', 'test_haiku'):
        for rec in run['splits'][split]['records']:
            row = gold[rec['id']]
            pred = rec['prediction'] if arm == 'off' else R.repair(rec['prediction'], row['note_text'], row['note_date'], arm)
            note = D.analyse(row, dict(rec, prediction=pred))
            w = note['writer']; notes[w] += 1; gold_events[w] += note['n_gold']
            for x in note['extras']: extras[(w, x['type'])] += 1
            iv = D.intervals(note)
            if iv is None:          # a parse failure loses every pair of the note, as in diagnose.py
                ng = note['day_gold_events']
                iv = [dict(found=False, parse_failure=True) for _ in range(ng * (ng - 1) // 2)]
            for q in iv: q['writer'] = w
            pairs.extend(iv)
    return pairs, extras, gold_events, notes


def _profile(pairs, extras, gold_events, notes, writer):
    sel = [r for r in pairs if writer == 'all' or r['writer'] == writer]
    found = [r for r in sel if r.get('found')]
    err = np.array([r['err'] for r in found], float)
    ws = WRITERS[1:] if writer == 'all' else (writer,)
    g = sum(gold_events[w] for w in ws); n = sum(notes[w] for w in ws)
    by_type = {t: sum(extras[(w, t)] for w in ws) for t in EVENT_TYPES}
    return dict(writer=writer, notes=n, gold_events=g, pairs=len(sel), found=len(found), keep=len(found) / len(sel),
                exact_interval=float(np.mean(err == 0)), mean_err=float(err.mean()), sd_err=float(err.std(ddof=1)),
                mad_err=float(np.median(np.abs(err))), p90_abs=float(np.quantile(np.abs(err), .9)),
                extra_events=sum(by_type.values()), extra_events_by_type={t: k for t, k in by_type.items() if k},
                extra_slot_probability=[1 - exp(-9 * by_type[t] / g) for t in EVENT_TYPES]), err


def measured_interval_profiles():
    """Profiles for arms off and A (and A', the product default, checked equal to A on these notes), every
    source hashed, every recomputation checked against the stored lists of runs/diagnose/."""
    D = _module('eventlog_diagnose', DIAGNOSE); R = _module('eventlog_resolver', RESOLVER); gold = D.load_gold()
    freeze = json.loads((ROOT / FREEZE).read_text())
    frozen = {p: freeze['files'][p] == _sha(p) for p in (RESOLVER, LEXICON)}
    if not all(frozen.values()): raise ValueError(f'resolver differs from its freeze record {FREEZE}: {frozen}')
    strip = lambda rows: [{k: v for k, v in r.items() if k != 'note'} for r in rows]
    profiles, errors, checks = {}, {}, {}
    computed = {}
    for arm in ('off', 'A', "A'"):
        computed[arm] = note_pairs(arm, D, R, gold)
    for arm in ('off', 'A'):
        stored = json.loads((ROOT / STORED[arm]).read_text())
        if strip(computed[arm][0]) != strip(stored):
            raise ValueError(f'arm {arm}: recomputed interval pairs differ from {STORED[arm]}')
        checks[arm] = f'recomputed {len(stored):,} within-note pairs equal {STORED[arm]}'
        for w in WRITERS:
            p, e = _profile(*computed[arm], w)
            profiles[f'{arm}|{w}'] = dict(arm=arm, arm_label=ARMS[arm], **p); errors[f'{arm}|{w}'] = e
    same = strip(computed["A'"][0]) == strip(computed['A'][0]) and computed["A'"][1] == computed['A'][1]
    impact = json.loads((ROOT / IMPACT).read_text())['profiles']
    for arm in ('off', 'A'):
        for w in WRITERS:
            ref = impact[f'{IMPACT_NAMES[arm]} | {w}']; p = profiles[f'{arm}|{w}']
            ok = (ref['pairs'], ref['found'], ref['keep'], ref['exact_interval']) == (p['pairs'], p['found'], round(p['keep'], 4), round(p['exact_interval'], 4))
            if not ok: raise ValueError(f'profile {arm}|{w} differs from {IMPACT}')
    sources = {x: _sha(x) for x in [PREDICTIONS, *LABELS, DIAGNOSE, RESOLVER, LEXICON, FREEZE, STORED['off'], STORED['A'], IMPACT]}
    return dict(profiles=profiles, sources=sources, checks=dict(
        recomputed_equals_stored=checks, resolver_frozen=frozen, frozen_at_utc=freeze['frozen_at_utc'], rule=freeze['rule'],
        product_default_arm_Aprime_equals_A_on_these_notes=same,
        profiles_equal_interval_impact_v1=True)), errors


def core_logs(rng, t, prof=None, err=None, extras=False):
    """Log-durations of the three core intervals: (logs, observed spans, true spans); nan when lost."""
    a = np.rint(t)
    spans = np.stack([a[..., b] - a[..., s] for s, b in ENDPOINTS[:3]], axis=-1)
    if prof is None:
        return log_days(spans), spans, spans
    obs = spans + err[rng.integers(0, len(err), spans.shape)]
    lost = rng.random(spans.shape) >= prof['keep']
    if extras:
        hit = rng.random(a.shape) < np.asarray(prof['extra_slot_probability'])
        lost |= np.stack([hit[..., s] | hit[..., b] for s, b in ENDPOINTS[:3]], axis=-1)
    obs = np.where(lost, np.nan, obs)
    return log_days(obs), obs, spans


def _planted(rng, truth, ratio, prof, err, ref, extras, stages=(0, 1, 2)):
    out = {}
    for stage in stages:
        logs, obs, spans = core_logs(rng, plant(truth, stage, ratio), prof, err, extras)
        mean, var, cnt = moments(logs)
        flag, _, located = test_moments(mean, var, cnt, *ref)
        s = spans[..., stage]; o = obs[..., stage]
        med_true = np.median(s, axis=1)
        with np.errstate(invalid='ignore'):
            med_obs = np.nanmedian(np.where(o >= 0, o, np.nan), axis=1)
        k = int((located == stage).sum())
        out[CORE[stage]] = dict(located=k / len(located), located_ci95=wilson(k, len(located)),
            planted_test_power=float(flag[..., stage].mean()), any_flag=float(flag.any(axis=-1).mean()),
            median_bias_days=float(np.nanmean(med_obs - med_true)), true_median_days=float(med_true.mean()),
            testable_mean=float(cnt[..., stage].mean()), negative_span_share=float(np.mean(o < 0)),
            log_sd_noisy=float(np.nanstd(logs[..., stage])))
    return out


def _null(rng, truth, prof, err, ref, extras):
    logs, _, _ = core_logs(rng, truth, prof, err, extras)
    mean, var, cnt = moments(logs)
    flag, _, _ = test_moments(mean, var, cnt, *ref)
    hit = flag.any(axis=-1)
    return dict(county_false_positive_rate=float(hit.mean()), county_false_positive_rate_ci95=wilson(int(hit.sum()), len(hit)),
                mean_testable=[float(x) for x in cnt.mean(axis=0)])


def interval_extraction_study(rng, reps, pathways, table_n, reference_size=100_000, sizes=(500, 2000), ratio=1.3, null_n=500):
    """pathways: design_study.pathways; table_n: per-interval n for a 20% slowdown at one look (section 2)."""
    measured, errors = measured_interval_profiles()
    P = measured['profiles']
    ref_truth = pathways(rng, (reference_size,))
    refs = {}
    def ref(key, extras=False):
        """Reference moments: key None = structured fields (no extraction error), else a profile key."""
        if (key, extras) not in refs:
            logs = core_logs(rng, ref_truth, None if key is None else P[key], None if key is None else errors[key], extras and key is not None)[0]
            refs[(key, extras)] = moments(logs, axis=0)
        return refs[(key, extras)]
    variants = [(None, False)] + [(arm, x) for arm in ('off', 'A') for x in (False, True)]
    label = lambda arm, x: 'every event confirmed by a person' if arm is None else ARMS[arm] + (', extra events modelled' if x else '')
    rows = []
    for n in sizes:
        truth = pathways(rng, (reps, n))
        for arm, x in variants:
            key = None if arm is None else f'{arm}|all'
            rows.append(dict(kind='planted', condition='confirmed' if arm is None else 'measured_everywhere', arm=arm, writer='all', extras_modelled=x,
                label=label(arm, x), n=n, slowdown=ratio, replications=reps,
                intervals=_planted(rng, truth, ratio, None if key is None else P[key], None if key is None else errors[key], ref(key, x), x)))
    for arm, x in variants:
        key = None if arm is None else f'{arm}|all'; cell = {}
        for stage, k in enumerate(CORE):
            truth = pathways(rng, (reps, table_n[k]))
            cell.update(_planted(rng, truth, 1.2, None if key is None else P[key], None if key is None else errors[key], ref(key, x), x, stages=(stage,)))
        rows.append(dict(kind='planted_table_n', condition='confirmed' if arm is None else 'measured_everywhere', arm=arm, writer='all', extras_modelled=x,
            label=label(arm, x), n={k: table_n[k] for k in CORE}, slowdown=1.2, replications=reps, intervals=cell))
    truth = pathways(rng, (reps, null_n))
    rows.append(dict(kind='null', condition='confirmed', arm=None, writer=None, extras_modelled=False, n=null_n, replications=reps,
                     **_null(rng, truth, None, None, ref(None), False)))
    for arm in ('off', 'A'):
        for x in (False, True):
            key = f'{arm}|all'
            rows.append(dict(kind='null', condition='measured_everywhere', arm=arm, writer='all', extras_modelled=x, n=null_n, replications=reps,
                             **_null(rng, truth, P[key], errors[key], ref(key, x), x)))
            for w in WRITERS:
                key = f'{arm}|{w}'
                rows.append(dict(kind='null', condition='county_extracted_country_structured', arm=arm, writer=w, extras_modelled=x, n=null_n, replications=reps,
                                 **_null(rng, truth, P[key], errors[key], ref(None), x)))
            rows.append(dict(kind='null', condition='county_haiku_like_country_nemotron_like', arm=arm, writer='haiku vs nemotron', extras_modelled=x, n=null_n, replications=reps,
                             **_null(rng, truth, P[f'{arm}|haiku'], errors[f'{arm}|haiku'], ref(f'{arm}|nemotron', x), x)))
    rep = json.loads((ROOT / REPRODUCE).read_text())
    if rep['primary']['run'] != RUN or rep['primary']['arm'] != 'A' or rep['freeze']['files'] != json.loads((ROOT / FREEZE).read_text())['files']:
        raise ValueError(f'{REPRODUCE} is not the arm-A result of {RUN} under the current freeze')
    pick = lambda r: dict(k=r['k'], n=r['n'], value=r['value'], wilson95=r['wilson95'])
    exact = dict(source=REPRODUCE, run=RUN, arm='A', reproduced_exactly=rep['primary']['reproduced_exactly'], notes_made_worse_all_runs=rep['notes_made_worse_arm_A_all_runs'],
                 validation=dict(role=rep['primary']['validation']['role'], as_is=pick(rep['primary']['validation']['before']), resolver=pick(rep['primary']['validation'])),
                 test=dict(role=rep['primary']['test']['role'], as_is=pick(rep['primary']['test']['before']), resolver=pick(rep['primary']['test']),
                           resolver_by_writer={w: pick(v) for w, v in rep['primary']['test']['by_writer'].items()}))
    measured['sources'][REPRODUCE] = _sha(REPRODUCE)
    out = dict(run=RUN, note_exact_match=exact, profiles=list(P.values()), sources=measured['sources'], checks=measured['checks'], reference_episodes=reference_size, rows=rows,
        error_model=('Each core interval of a simulated episode gets an error drawn from the measured within-note interval errors of the profile '
                     '(predicted span minus true span over pairs of DAY-precision gold events of one note whose two endpoints were found) and is lost with the measured lost share. '
                     'Negative spans are excluded, never repaired.'),
        extra_events_model=('Measured per writer and event type; an episode slot receives an extra with probability 1 - exp(-9 x extras of the type / gold events). '
                            'An extra makes both core intervals that use the slot underivable, because eventlog.intervals.derive needs exactly one start and one end event. '
                            'An extra that stands in for a true event missing from the record is not modelled.'),
        limits=['The error profiles come from 700 SYNTHETIC test notes written and labelled by language models, not from clinical text; the test notes had been read before (post hoc).',
                'The resolver was designed on the generator\'s own six date forms; notes with other relative phrasings are not represented.',
                'Interval errors are drawn from all within-note pairs, not per interval type; extra events that stand in for a missing true event are not modelled.',
                'The confirmed condition assumes that a person removes every error; that was not measured.'])
    out['agreement_with_interval_impact_v1'] = agreement(out)
    return out


def agreement(study):
    """Compare the comparable cells (no extra events) with runs/diagnose/interval-impact-v1.json: rates by
    binomial SE of the difference (p clipped to half a replication), median bias by absolute days."""
    old = json.loads((ROOT / IMPACT).read_text())
    cond = lambda arm, w='all': 'confirmed (no error)' if arm is None else f'{IMPACT_NAMES[arm]} | {w}'
    find = lambda kind, c, n=None: next(x for x in old['cells'] if x['kind'] == kind and x['condition'] == c and (n is None or x.get('n') == n))
    pairs = []
    for r in study['rows']:
        if r['extras_modelled']: continue
        if r['kind'] == 'planted':
            o = find('planted 30%', cond(r['arm']), r['n'])
            for k in CORE: pairs.append((f"planted 30%, n={r['n']}, {r['arm']}, {k}", r['intervals'][k]['located'], o[k]['located'], r['replications'], old['reps'], r['intervals'][k]['median_bias_days'], o[k]['median_bias_days']))
        elif r['kind'] == 'planted_table_n':
            o = find('planted 20% at the table n (473/513/347)', cond(r['arm']))
            for k in CORE: pairs.append((f"planted 20% at the table n, {r['arm']}, {k}", r['intervals'][k]['located'], o[k]['located'], r['replications'], old['reps'], r['intervals'][k]['median_bias_days'], o[k]['median_bias_days']))
        elif r['kind'] == 'null':
            c = {'confirmed': ('null, same error in county and country', cond(None)),
                 'measured_everywhere': ('null, same error in county and country', cond(r['arm'])),
                 'county_extracted_country_structured': ('null, county extracted, country structured', cond(r['arm'], r['writer'])),
                 'county_haiku_like_country_nemotron_like': ('null, county errors from Haiku-written notes, country from Nemotron-written', None if r['arm'] is None else IMPACT_NAMES[r['arm']])}[r['condition']]
            if r['condition'] == 'county_extracted_country_structured' and r['writer'] != 'all': continue
            o = find(c[0], c[1], 500)
            pairs.append((f"null, {r['condition']}, {r['arm']}", r['county_false_positive_rate'], o['primary_care']['false_flag_any'], r['replications'], old['reps'], None, None))
    rows = []
    for name, new, prev, r1, r2, b1, b2 in pairs:
        clip = lambda p, r: min(max(p, .5 / r), 1 - .5 / r)
        se = sqrt(clip(new, r1) * (1 - clip(new, r1)) / r1 + clip(prev, r2) * (1 - clip(prev, r2)) / r2)
        rows.append(dict(cell=name, this_study=new, interval_impact_v1=prev, difference=new - prev, difference_in_se=abs(new - prev) / se,
                         median_bias_days=None if b1 is None else [b1, b2]))
    return dict(source=IMPACT, compared_rates=len(rows), beyond_3_se=sum(x['difference_in_se'] > 3 for x in rows),
                largest_rate_difference=max(abs(x['difference']) for x in rows),
                largest_median_bias_difference_days=max(abs(x['median_bias_days'][0] - x['median_bias_days'][1]) for x in rows if x['median_bias_days']),
                note='Different random streams; the reference pool of 100,000 episodes is drawn once per study, so its error is shared by all cells of one study and is not in the binomial SE.',
                rows=rows)


def null_rate(section, condition, arm, writer, extras=False):
    return next(x['county_false_positive_rate'] for x in section['rows'] if x['kind'] == 'null' and x['condition'] == condition
                and x['arm'] == arm and x['writer'] == writer and x['extras_modelled'] == extras)


def fake_inequality(section):
    """The insight, with every number read from the study section."""
    county = lambda arm, x=False: null_rate(section, 'county_extracted_country_structured', arm, 'all', x)
    style = lambda arm, x=False: null_rate(section, 'county_haiku_like_country_nemotron_like', arm, 'haiku vs nemotron', x)
    null = next(x for x in section['rows'] if x['kind'] == 'null')
    numbers = dict(county_text_country_structured=dict(as_is=county('off'), resolver=county('A'), as_is_with_extras=county('off', True), resolver_with_extras=county('A', True)),
                   county_haiku_like_country_nemotron_like=dict(as_is=style('off'), resolver=style('A'), as_is_with_extras=style('off', True), resolver_with_extras=style('A', True)),
                   confirmed=null_rate(section, 'confirmed', None, None), nominal_at_most=3 * .05 / 69, county_episodes=null['n'], replications=null['replications'],
                   extra_events_modelled=True, extra_events_standing_in_for_missing_true_events_modelled=False)
    headline = 'Extraction errors manufacture fake county inequality (simulation on SYNTHETIC error profiles).'
    text = (f"With no real difference anywhere, one county of {null['n']:,} episodes whose dates are read from notes by the current scribe ({RUN}) while the rest of the country "
            f"comes from structured fields is flagged in {county('off'):.3f} of {null['replications']:,} runs as is and in {county('A'):.3f} with the code date resolver "
            f"(every event confirmed: {numbers['confirmed']:.3f}; nominal at most {numbers['nominal_at_most']:.5f}). "
            f"If both are read from notes, but the county's notes are written like the Haiku-written test notes and the country's like the Nemotron-written ones, "
            f"the county is flagged in {style('off'):.3f} of runs as is and {style('A'):.3f} with the resolver. "
            f"Extra predicted events are modelled at the measured rate per writer and event type (an extra makes the interval underivable, as eventlog.intervals.derive does): "
            f"then {county('off', True):.3f} and {county('A', True):.3f} for the first comparison, {style('off', True):.3f} and {style('A', True):.3f} for the second. "
            "An extra that stands in for a true event missing from the record is not modelled.")
    return dict(headline=headline, text=text, numbers=numbers)
