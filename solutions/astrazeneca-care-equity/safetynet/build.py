"""Build data/safetynet/*: rule evaluation, imaging extension table and the county panel JSON.

Run from the solution root:  scribe/.venv/bin/python -m safetynet.build
Standard library plus pyarrow. No model, no network. Everything patient-like is SYNTHETIC.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from . import extension, measure, rule, worklist

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'data' / 'safetynet'
LOG = ROOT / 'runs' / 'ship-safetynet.jsonl'
SAMPLE = ROOT / 'data' / 'eventlog' / 'sample'
SNAPSHOT = ROOT / 'data' / 'snapshot' / 'public-v1.json'
PILOT = 'HVA06'

THRESHOLDS = [
    dict(clock='Suspected-cancer referral to DIAGNOSIS (worklist trigger)', days=worklist.REFERRAL_THRESHOLD_DAYS,
         label='PLACEHOLDER', source='Placeholder taken from the OECD/EU-reported six-week referral-to-treatment target (OECD/EU Country Cancer Profile Finland 2025, p. 19; evidence row oecd-2025-six-week-target). The law (STM hoitotakuu) allows up to six months for treatment and names no cancer-specific limit. Not a SAMA decision: cancer-specific access times are to be set under roadmap measure 3.1.2 (p. 57); quality targets and indicators under 3.1.4 (p. 58).'),
    dict(clock='Same, sensitivity', days=worklist.REFERRAL_SENSITIVITY_DAYS, label='PLACEHOLDER',
         source="SAMA's navigation action flags a stalled work-up at 90 days, also a placeholder. Shown only as a count, so the two placeholders do not compete."),
    dict(clock='Imaging follow-up', days=None, label='COPIED',
         source='The due date the radiologist wrote, copied by the rule and computed by calendar arithmetic. Never decided by SAMA. Ranges and vague wording go to a person.'),
]
KPIS = [
    dict(name='Share of imaging follow-ups done by the due date', target='DESIGN TARGET, set by the county at pilot start; not set or measured by SAMA'),
    dict(name='Share of worklist items resolved within 14 days of appearing', target='DESIGN TARGET, set by the county; not measured'),
    dict(name=f'Share of suspected-cancer referrals with a diagnosis recorded by day {worklist.REFERRAL_THRESHOLD_DAYS} (placeholder)', target='DESIGN TARGET; not measured'),
    dict(name='Stage at diagnosis among people found through the worklist', target='DESIGN TARGET; not measured'),
    dict(name='Every KPI reported by entry route, education and contact language, so the safety net cannot reproduce the gap', target='DESIGN REQUIREMENT'),
]
TEXT = dict(
    title='Close loops, don’t count them',
    synthetic='SYNTHETIC: every row, count and report line in this panel is simulated. No real patient, report or county record.',
    clock='The referral clock starts when the referral is sent (event REFERRAL_SENT), not when it is received.',
    as_of='Replay date: the worklist sees only SYNTHETIC events dated on or before this date.',
    governance='The county owns the list and the care. Nurses call. No patient data leaves the county or goes to any sponsor. Any company role is a documented, non-promotional collaboration owned by the county.',
    legal="Since 1 June 2026 a county may identify patients whose care does not follow recommendations (“joiden hoito ei vastaa suosituksia”); processing their data and contacting them must respect data protection and self-determination (STM, 21 May 2026). Scope for pathway timing to be confirmed with STM/THL.",
    legal_url='https://valtioneuvosto.fi/-/1271139/lakimuutokset-parantavat-hyvinvointialueiden-mahdollisuuksia-ennakoivaan-terveydenhuoltoon',
    regulatory="A workflow aid: it copies the radiologist's written recommendation, computes a date, and a nurse decides. Device qualification under the MDR to be confirmed with Fimea before the pilot (UNVERIFIED). AI Act high-risk dates 2 Dec 2027 and 2 Aug 2028 tracked.",
    pilot='Pilot: Satakunta, every overdue suspected-cancer referral, lung follow-up first. Chosen on process grounds: Finnish-language services, not under the state assessment procedure, already the default on SAMA’s pilot card (data/roadmap/mapping-v1.json). Not chosen as “highest lung mortality”. Whether Satakunta is in the national lung screening pilot is UNVERIFIED; if it is in a randomised arm, the evaluation design must change.',
    scope='Finnish report lines only; lines in other languages go to manual entry.',
    rule='A code rule reads the follow-up recommendation (no model). It copies the written phrase and computes the due date; ranges, approximate, vague or conditional wording go to a person. A nurse confirms every item.',
    neutrality='Vendor- and product-neutral. No drug or biomarker content.',
    aland='The 1 June 2026 amendment and national measures are not claimed for Åland (separate health legislation; UNVERIFIED).',
    roadmap='Operational form of SAMA’s navigation action (roadmap 1.2.3, named care-coordinating worker) with digital pathways (3.5.3).',
)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def log(step: str, **kw) -> None:
    row = dict(at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), step=step, **kw)
    with LOG.open('a') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


def _iso(v):
    return v.isoformat() if hasattr(v, 'isoformat') else v


def build(as_of=worklist.AS_OF) -> dict:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    names = {r['id']: r['nameEn'].replace(' wellbeing services county', '') for r in json.loads(SNAPSHOT.read_text())['regions']}

    ev = measure.evaluate()
    (OUT / 'rule-eval-v1.json').write_text(json.dumps(dict(
        schemaVersion='1.0', synthetic=True, rule_version=ev['rule_version'], rule_sha256=sha256_file(ROOT / 'safetynet/rule.py'),
        reports_sha256=sha256_file(ROOT / 'safetynet/reports.py'),
        caveat='The 60 lines were rendered by code templates written by the same step that wrote the rule, after the rule was frozen. A score here measures the rule against its own template family; it says nothing about real radiology reports.',
        metrics=ev['metrics'], lines=ev['lines'], rows=ev['rows']), ensure_ascii=False, indent=1) + '\n')

    episodes = extension.read_event_log(SAMPLE)
    referrals = extension.referral_loops(episodes)
    imaging = extension.imaging_cohort(episodes, as_of)
    pq.write_table(extension.imaging_table(imaging), OUT / 'imaging-loops.parquet', compression='zstd')
    g = lambda o: [x for x in imaging if x['gold_outcome'] == o]
    cohort_rule = dict(
        loops=len(imaging),
        rule_outcomes={o: sum(x['rule_outcome'] == o for x in imaging) for o in rule.OUTCOMES},
        gold_outcomes={o: len(g(o)) for o in rule.OUTCOMES},
        rule_matches_gold=sum(x['rule_outcome'] == x['gold_outcome'] and x['rule_due_date'] == x['gold_due_date'] for x in imaging),
        exact_due_date=sum(x['rule_outcome'] == 'DUE_DATE' and x['rule_due_date'] == x['gold_due_date'] for x in g('DUE_DATE')),
        errors=dict(
            wrong_due_date=sum(x['rule_outcome'] == 'DUE_DATE' and x['rule_due_date'] != x['gold_due_date'] for x in g('DUE_DATE')),
            invented_date_for_person_line=sum(x['rule_outcome'] == 'DUE_DATE' for x in g('PERSON')),
            invented_date_for_none_line=sum(x['rule_outcome'] == 'DUE_DATE' for x in g('NONE')),
            missed_recommendation=sum(x['rule_outcome'] == 'NONE' for x in g('DUE_DATE') + g('PERSON')),
            due_line_sent_to_person=sum(x['rule_outcome'] == 'PERSON' for x in g('DUE_DATE'))),
        due_line_sent_to_person_reasons=dict(sorted(Counter(x['rule_reason'] for x in g('DUE_DATE') if x['rule_outcome'] == 'PERSON').items())),
        note='Second check, after the 60-line evaluation: the cohort lines are rendered from the same templates with new seeds and dates, so new combinations of finding and recommendation sentences occur. Same caveat: not real reports.')

    panels = []
    for c in sorted({e['county'] for e in episodes.values()}):
        p = worklist.county_panel(c, referrals, imaging, as_of)
        p['name'] = names.get(c, c)
        if c == 'HVA91':
            p['note'] = TEXT['aland']
        panels.append(p)
    out = dict(
        schemaVersion='1.0', schemaDoc='data/safetynet/SCHEMA.md', dataClass='SYNTHETIC', synthetic=True,
        generatedAt=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        asOf=as_of.isoformat(), pilotRegionId=PILOT, text=TEXT, thresholds=THRESHOLDS, kpis=KPIS,
        suppression=dict(below=worklist.SUPPRESS_BELOW, rule='Counts 1-4 are displayed as "<5"; raw SYNTHETIC counts stay in this file. National totals are summed from county rows.'),
        rule=dict(version=rule.RULE_VERSION, sha256=sha256_file(ROOT / 'safetynet/rule.py'), evaluation='data/safetynet/rule-eval-v1.json',
                  metrics={k: ev['metrics'][k] for k in ('lines', 'gold_counts', 'exact_due_date', 'sent_to_person_when_gold_person', 'none_correct', 'all_correct', 'errors')},
                  caveat='Measured on 60 SYNTHETIC lines from code templates written by the same step after the rule was frozen; not a result on real reports.'),
        cohort=dict(imaging_loops=cohort_rule, referral_loops=len(referrals), event_log_episodes=len(episodes),
                    assumptions=extension.ASSUMPTIONS, assumption_notes=extension.ASSUMPTION_NOTES),
        national=worklist.national(panels),
        counties=panels,
        provenance=dict(
            event_log=str(SAMPLE.relative_to(ROOT)), event_log_sha256=extension.dataset_sha256(SAMPLE),
            snapshot=str(SNAPSHOT.relative_to(ROOT)), snapshot_sha256=sha256_file(SNAPSHOT),
            code={p: sha256_file(ROOT / p) for p in ('safetynet/rule.py', 'safetynet/reports.py', 'safetynet/measure.py',
                                                      'safetynet/extension.py', 'safetynet/worklist.py', 'safetynet/build.py')},
            python=platform.python_version(), pyarrow=pa.__version__, command='scribe/.venv/bin/python -m safetynet.build'),
    )
    (OUT / 'safetynet-v1.json').write_text(json.dumps(out, ensure_ascii=False, indent=1, default=_iso) + '\n')
    pilot = next(p for p in panels if p['regionId'] == PILOT)
    log('3-build', status='done', outputs=['data/safetynet/safetynet-v1.json', 'data/safetynet/rule-eval-v1.json', 'data/safetynet/imaging-loops.parquet'],
        metrics=dict(rule=out['rule']['metrics']['all_correct'], exact_due_date=out['rule']['metrics']['exact_due_date'],
                     sent_to_person=out['rule']['metrics']['sent_to_person_when_gold_person'],
                     cohort=cohort_rule, referral_loops=len(referrals), pilot_counts=pilot['counts'],
                     national_open=out['national']['open_loops'], national_overdue=out['national']['overdue'],
                     elapsed_s=round(time.time() - t0, 2)),
        synthetic=True)
    return out


if __name__ == '__main__':
    o = build()
    p = next(x for x in o['counties'] if x['regionId'] == PILOT)
    json.dump(dict(rule=o['rule']['metrics']['all_correct'], pilot=p['counts'], examples=p['examples'], national=o['national']),
              sys.stdout, ensure_ascii=False, indent=1, default=_iso)
    print()
