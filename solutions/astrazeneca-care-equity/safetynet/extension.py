"""Event-log extension for the safety net. SYNTHETIC only. Does not edit eventlog/schema.py.

Two loop kinds are joined per county:

1. Suspected-cancer referrals, read from the SYNTHETIC event log (data/eventlog/sample): the
   referral clock starts at REFERRAL_SENT and the loop closes at DIAGNOSIS. Read-only.
2. Imaging follow-up loops: an extension table with its own SYNTHETIC cohort of people whose
   radiology report recommends follow-up imaging. Its county sizes and entry-route mix are taken
   from the event log's episodes in the same county (the join); each loop carries a report line
   rendered by safetynet.reports and the frozen rule's reading of it. Whether and when the
   follow-up scan happened is a stated simulation assumption (ASSUMPTIONS), identical in every
   county, so county differences in it are sampling noise by construction.

Extension event types (IMAGING_REPORTED, FOLLOWUP_IMAGING_DONE) live only in this module's table;
eventlog.schema.EVENT_TYPES is imported read-only and never changed.
"""
from __future__ import annotations

import hashlib
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

from eventlog.schema import AGE_BANDS, COUNTIES, ENTRY_ROUTES, EVENT_TYPES

from . import rule
from .reports import render

EXT_EVENT_TYPES = ['IMAGING_REPORTED', 'FOLLOWUP_IMAGING_DONE']
assert not set(EXT_EVENT_TYPES) & set(EVENT_TYPES)
CONTACT_LANGUAGES = ['fi', 'sv', 'se', 'other']
ADULT_BANDS = [b for b in AGE_BANDS if b[0].isdigit() and 40 <= int(b.split('-')[0].rstrip('+')) <= 80]

SEED = 20261115
ASSUMPTIONS = dict(
    imaging_loops_per_event_log_episode=0.25,
    report_window_days=365,
    p_followup_on_time=0.70,
    p_followup_late=0.20,
    p_followup_not_done=0.10,
    on_time_done_up_to_days_before_due=14,
    late_delay_mean_days=45,
    imaging_age_bands=ADULT_BANDS,
    contact_language_shares=dict(fi=0.85, sv=0.05, se=0.002, other=0.098),
    interpreter_flag='set when contact language is other',
    person_window_days=14,
)
ASSUMPTION_NOTES = [
    'Every value in ASSUMPTIONS is a simulation choice made for this demo, not an estimate about Finland.',
    'Imaging follow-up completion (70% on time, 20% late, 10% not done) is the same in every county and route, so the share done by the due date reproduces 0.70 up to sampling noise; it is not a finding.',
    'The imaging cohort reuses the 60-line test family mix (30 dated, 20 for a person, 10 no follow-up per 60); that mix is a design choice, not an observed report mix.',
    'Contact language is drawn from one fixed share for every county; it is not Statistics Finland data.',
    'Age bands of imaging loops are drawn uniformly from 40-44 to 80-84; event-log age bands come from its simulator, which draws them uniformly from 0-4 to 100+.',
]

imaging_loops_schema = pa.schema([
    ('loop_id', pa.string()), ('county', pa.string()), ('entry_route', pa.string()), ('age_band', pa.string()),
    ('contact_language', pa.string()), ('interpreter', pa.bool_()), ('report_line_id', pa.string()),
    ('report_date', pa.date32()), ('report_text', pa.string()), ('rule_outcome', pa.string()),
    ('rule_reason', pa.string()), ('rule_due_date', pa.date32()), ('recommendation_copied', pa.string()),
    ('gold_outcome', pa.string()), ('gold_due_date', pa.date32()), ('followup_done_date', pa.date32()),
    ('synthetic', pa.bool_()),
])


def dataset_sha256(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob('*.parquet')):
        h.update(str(p.relative_to(root)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def read_event_log(root: Path, types=('SYMPTOM_ONSET_REPORTED', 'REFERRAL_SENT', 'DIAGNOSIS')) -> dict:
    """Episodes keyed by episode_id with county, route, age band, site and the requested event dates."""
    d = ds.dataset(str(root), format='parquet', partitioning='hive')
    cols = ['episode_id', 'event_type', 'event_date', 'entry_route', 'cancer_site', 'age_band', 'county', 'synthetic']
    t = d.to_table(columns=cols)
    t = t.filter(pc.is_in(pc.cast(t['event_type'], pa.string()), value_set=pa.array(list(types))))
    episodes = {}
    for r in t.to_pylist():
        if not r['synthetic']:
            raise ValueError('safety net demo reads SYNTHETIC rows only')
        e = episodes.setdefault(r['episode_id'], dict(episode_id=r['episode_id'], county=str(r['county']),
                                                      entry_route=r['entry_route'], age_band=r['age_band'],
                                                      cancer_site=r['cancer_site'], events={}))
        e['events'][r['event_type']] = r['event_date']
    return episodes


def referral_loops(episodes: dict) -> list[dict]:
    """One loop per episode with a REFERRAL_SENT event: the clock starts when the referral is sent."""
    out = []
    for e in episodes.values():
        sent = e['events'].get('REFERRAL_SENT')
        if sent is None:
            continue
        out.append(dict(loop_kind='suspected_cancer_referral', loop_id=e['episode_id'], county=e['county'],
                        entry_route=e['entry_route'], age_band=e['age_band'], cancer_site=e['cancer_site'],
                        referral_sent=sent, diagnosis=e['events'].get('DIAGNOSIS'), synthetic=True))
    return out


def _language(rng: random.Random) -> str:
    shares = ASSUMPTIONS['contact_language_shares']
    return rng.choices(list(shares), weights=list(shares.values()))[0]


def imaging_cohort(episodes: dict, as_of: date, seed: int = SEED) -> list[dict]:
    """SYNTHETIC imaging follow-up loops, sized and route-mixed per county from the event log."""
    rng = random.Random(seed)
    per_county, routes = Counter(), defaultdict(Counter)
    for e in episodes.values():
        per_county[e['county']] += 1
        routes[e['county']][e['entry_route']] += 1
    sizes = {c: round(ASSUMPTIONS['imaging_loops_per_event_log_episode'] * per_county[c]) for c in COUNTIES if per_county[c]}
    need, lines, i = sum(sizes.values()), [], 0
    start = as_of - timedelta(days=ASSUMPTIONS['report_window_days'])
    while len(lines) < need:
        lines += render(seed=seed + 1000 + i, start=start, days=ASSUMPTIONS['report_window_days'],
                        prefix=f'SYN-SN{i:03d}-RAD')
        i += 1
    rng.shuffle(lines)
    loops, k = [], 0
    for county in COUNTIES:
        if county not in sizes:
            continue
        mix = routes[county]
        for j in range(sizes[county]):
            line = lines[k]
            k += 1
            report = date.fromisoformat(line['report_date'])
            r = rule.read(line['text'], report)
            gold_due = date.fromisoformat(line['gold_due_date']) if line['gold_due_date'] else None
            done = None
            if gold_due is not None:
                u = rng.random()
                if u < ASSUMPTIONS['p_followup_on_time']:
                    done = max(report + timedelta(days=1), gold_due - timedelta(days=rng.randint(0, ASSUMPTIONS['on_time_done_up_to_days_before_due'])))
                elif u < ASSUMPTIONS['p_followup_on_time'] + ASSUMPTIONS['p_followup_late']:
                    done = gold_due + timedelta(days=max(1, round(rng.expovariate(1 / ASSUMPTIONS['late_delay_mean_days']))))
            language = _language(rng)
            route = rng.choices(list(mix), weights=list(mix.values()))[0]
            loops.append(dict(
                loop_id=f'SYNTHETIC-SN-{seed}-{county}-{j:04d}', county=county, entry_route=route,
                age_band=rng.choice(ADULT_BANDS), contact_language=language, interpreter=language == 'other',
                report_line_id=line['line_id'], report_date=report, report_text=line['text'],
                rule_outcome=r['outcome'], rule_reason=r['reason'],
                rule_due_date=date.fromisoformat(r['due_date']) if r['due_date'] else None,
                recommendation_copied=r['recommendation_text'], gold_outcome=line['gold_outcome'],
                gold_due_date=gold_due, followup_done_date=done, synthetic=True))
    for x in loops:
        assert x['county'] in COUNTIES and x['entry_route'] in ENTRY_ROUTES and x['age_band'] in AGE_BANDS
    return loops


def imaging_table(loops: list[dict]) -> pa.Table:
    return pa.Table.from_pylist(loops, schema=imaging_loops_schema)
