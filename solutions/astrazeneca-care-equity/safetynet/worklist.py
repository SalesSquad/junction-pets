"""County worklist as of a replay date: counts first, then at most three unnamed SYNTHETIC rows.

The worklist sees only events dated on or before AS_OF; later events in the SYNTHETIC log are
treated as not yet happened. Thresholds are placeholders, never SAMA decisions:
- imaging follow-up: the due date the radiologist wrote, computed by code from the copied phrase;
- suspected-cancer referral: no DIAGNOSIS by day 42 after REFERRAL_SENT. 42 is a placeholder from
  the OECD/EU-reported six-week referral-to-treatment target; a 90-day count (SAMA's navigation
  card, src/recommend.mjs PUBLIC_WORKUP.stallAfterDays) is given as a sensitivity.
"""
from __future__ import annotations

import hashlib
import random
from collections import Counter
from datetime import date

from eventlog.schema import COUNTIES, ENTRY_ROUTES

from .extension import ASSUMPTIONS, CONTACT_LANGUAGES, SEED

AS_OF = date(2025, 12, 1)
REFERRAL_THRESHOLD_DAYS = 42
REFERRAL_SENSITIVITY_DAYS = 90
SUPPRESS_BELOW = 5
OWNER = dict(
    imaging_follow_up='Referring unit; a nurse calls',
    suspected_cancer_referral='Pathway coordinator (roadmap 1.2.3 care-coordinating worker); a nurse calls',
    recommendation_needs_person='Referring unit; a person reads the recommendation and sets the date',
)
MISSING = dict(
    imaging_follow_up='Follow-up imaging not recorded by the due date the radiologist wrote',
    suspected_cancer_referral=f'No DIAGNOSIS recorded by day {REFERRAL_THRESHOLD_DAYS} after the referral was sent',
    recommendation_needs_person='Due date not set: the written recommendation is a range, vague, conditional or has no time',
)


def referral_language(episode_id: str) -> tuple[str, bool]:
    """Deterministic SYNTHETIC contact language for an event-log episode (the log has none)."""
    rng = random.Random(int(hashlib.sha256(f'{SEED}:{episode_id}'.encode()).hexdigest()[:12], 16))
    shares = ASSUMPTIONS['contact_language_shares']
    lang = rng.choices(list(shares), weights=list(shares.values()))[0]
    return lang, lang == 'other'


def referral_state(loop: dict, as_of: date = AS_OF, threshold: int = REFERRAL_THRESHOLD_DAYS) -> dict | None:
    """None if the referral was sent after as_of. Otherwise its state as seen on as_of."""
    sent = loop['referral_sent']
    if sent > as_of:
        return None
    dx = loop['diagnosis'] if loop['diagnosis'] is not None and loop['diagnosis'] <= as_of else None
    age = (as_of - sent).days
    clock_passed = age >= threshold
    return dict(open=dx is None, overdue=dx is None and age > threshold,
                days_overdue=age - threshold if dx is None and age > threshold else None,
                clock_passed=clock_passed,
                closed_by_threshold=clock_passed and dx is not None and (dx - sent).days <= threshold)


def imaging_state(loop: dict, as_of: date = AS_OF) -> dict | None:
    """None if reported after as_of or the rule read 'no follow-up'. Uses the rule's due date, not gold."""
    report = loop['report_date']
    if report > as_of or loop['rule_outcome'] == 'NONE':
        return None
    done = loop['followup_done_date'] if loop['followup_done_date'] is not None and loop['followup_done_date'] <= as_of else None
    if loop['rule_outcome'] == 'PERSON':
        recent = (as_of - report).days < ASSUMPTIONS['person_window_days']
        return dict(kind='recommendation_needs_person', open=recent, overdue=False, awaiting_person=recent,
                    days_overdue=None, due_passed=False, done_by_due=False)
    due = loop['rule_due_date']
    due_passed = due <= as_of
    return dict(kind='imaging_follow_up', open=done is None, overdue=done is None and due < as_of,
                days_overdue=(as_of - due).days if done is None and due < as_of else None,
                awaiting_person=False, due_passed=due_passed,
                done_by_due=due_passed and done is not None and done <= due)


def _share(k, n):
    return round(k / n, 4) if n else None


def county_panel(county: str, referrals: list[dict], imaging: list[dict], as_of: date = AS_OF) -> dict:
    ref = [(x, referral_state(x, as_of)) for x in referrals if x['county'] == county]
    ref = [(x, s) for x, s in ref if s]
    sens = [referral_state(x, as_of, REFERRAL_SENSITIVITY_DAYS) for x, _ in ref]
    img = [(x, imaging_state(x, as_of)) for x in imaging if x['county'] == county]
    img = [(x, s) for x, s in img if s]
    dated = [(x, s) for x, s in img if s['kind'] == 'imaging_follow_up']
    person = [(x, s) for x, s in img if s['kind'] == 'recommendation_needs_person']
    counts = dict(
        imaging=dict(
            open=sum(s['open'] for _, s in dated), overdue=sum(s['overdue'] for _, s in dated),
            due_passed=sum(s['due_passed'] for _, s in dated), done_by_due=sum(s['done_by_due'] for _, s in dated),
            awaiting_person=sum(s['awaiting_person'] for _, s in person),
            reports_with_recommendation=len(img)),
        referral=dict(
            open=sum(s['open'] for _, s in ref), overdue=sum(s['overdue'] for _, s in ref),
            overdue_at_sensitivity_days=sum(s['overdue'] for s in sens),
            clock_passed=sum(s['clock_passed'] for _, s in ref),
            diagnosed_by_threshold=sum(s['closed_by_threshold'] for _, s in ref)),
    )
    counts['imaging']['share_done_by_due'] = _share(counts['imaging']['done_by_due'], counts['imaging']['due_passed'])
    counts['referral']['share_diagnosed_by_threshold'] = _share(counts['referral']['diagnosed_by_threshold'], counts['referral']['clock_passed'])
    counts['open_loops'] = counts['imaging']['open'] + counts['imaging']['awaiting_person'] + counts['referral']['open']
    counts['overdue'] = counts['imaging']['overdue'] + counts['referral']['overdue']

    rows = []
    for x, s in dated:
        if s['open']:
            rows.append(dict(kind='imaging_follow_up', x=x, s=s, lang=(x['contact_language'], x['interpreter'])))
    for x, s in person:
        if s['open']:
            rows.append(dict(kind='recommendation_needs_person', x=x, s=s, lang=(x['contact_language'], x['interpreter'])))
    for x, s in ref:
        if s['open']:
            rows.append(dict(kind='suspected_cancer_referral', x=x, s=s, lang=referral_language(x['loop_id'])))
    by_route = {r: dict(route=r, open=0, overdue=0) for r in ENTRY_ROUTES}
    by_language = {g: dict(language=g, open=0, overdue=0, interpreter=0) for g in CONTACT_LANGUAGES}
    for r in rows:
        by_route[r['x']['entry_route']]['open'] += 1
        by_route[r['x']['entry_route']]['overdue'] += bool(r['s']['overdue'])
        g = by_language[r['lang'][0]]
        g['open'] += 1
        g['overdue'] += bool(r['s']['overdue'])
        g['interpreter'] += r['lang'][1]
    return dict(regionId=county, counts=counts,
                by_route=[v for v in by_route.values() if v['open']],
                by_language=[v for v in by_language.values() if v['open']],
                examples=examples(rows), synthetic=True)


def _adult(band: str) -> bool:
    return band[0].isdigit() and int(band.split('-')[0].rstrip('+')) >= 40


def examples(rows: list[dict]) -> list[dict]:
    """At most three unnamed SYNTHETIC rows: the most overdue imaging loop, the most overdue referral
    (age band 40+ only, to keep the illustration plausible) and the newest item that needs a person."""
    picks = []
    img = sorted((r for r in rows if r['kind'] == 'imaging_follow_up' and r['s']['overdue']),
                 key=lambda r: (-r['s']['days_overdue'], r['x']['loop_id']))
    ref = sorted((r for r in rows if r['kind'] == 'suspected_cancer_referral' and r['s']['overdue'] and _adult(r['x']['age_band'])),
                 key=lambda r: (-r['s']['days_overdue'], r['x']['loop_id']))
    per = sorted((r for r in rows if r['kind'] == 'recommendation_needs_person'),
                 key=lambda r: (r['x']['report_date'], r['x']['loop_id']), reverse=True)
    for group in (img, ref, per):
        if group:
            picks.append(group[0])
    out = []
    for r in picks[:3]:
        x, s = r['x'], r['s']
        kind = r['kind']
        out.append(dict(
            episode_code=x['loop_id'], loop_kind=kind, age_band=x['age_band'], route=x['entry_route'],
            contact_language=r['lang'][0], interpreter=r['lang'][1],
            days_overdue=s['days_overdue'], missing_step=MISSING[kind], owner_role=OWNER[kind],
            status='needs editing' if kind == 'recommendation_needs_person' else 'nurse confirms',
            recommendation_copied=x.get('recommendation_copied'),
            due_date=(x['rule_due_date'].isoformat() if x.get('rule_due_date') else None) if kind != 'suspected_cancer_referral'
            else None,
            referral_sent=x['referral_sent'].isoformat() if kind == 'suspected_cancer_referral' else None,
            report_date=x['report_date'].isoformat() if kind != 'suspected_cancer_referral' else None,
            synthetic=True))
    return out


def national(panels: list[dict]) -> dict:
    """Totals summed from the unsuppressed county rows (never from a suppressed table)."""
    t = dict(open_loops=0, overdue=0, imaging=Counter(), referral=Counter())
    for p in panels:
        c = p['counts']
        t['open_loops'] += c['open_loops']
        t['overdue'] += c['overdue']
        for k in ('imaging', 'referral'):
            t[k].update({a: b for a, b in c[k].items() if isinstance(b, int)})
    t['imaging'], t['referral'] = dict(t['imaging']), dict(t['referral'])
    t['imaging']['share_done_by_due'] = _share(t['imaging']['done_by_due'], t['imaging']['due_passed'])
    t['referral']['share_diagnosed_by_threshold'] = _share(t['referral']['diagnosed_by_threshold'], t['referral']['clock_passed'])
    return t
