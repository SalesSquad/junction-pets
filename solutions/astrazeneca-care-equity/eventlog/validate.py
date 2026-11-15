"""Schema, enumeration, duplicate, date and chronology checks.

Chronology uses the one pathway order in schema.EVENT_TYPES: within an episode
every observed event must be on or after every observed earlier event type.
Dates are whole days and ties are allowed. Because the order is total, checking
neighbouring observed events is sufficient. Nothing is repaired.

That order is the simulator's convention, not a rule every real pathway obeys
(a specialist visit before the diagnosis is confirmed, an emergency diagnosis
before any referral, a screening case with no symptom onset, treatment before a
recorded multidisciplinary decision). Two modes:
  order='strict'  simulator output: a reversed pair can only be a simulator bug,
                  so it makes the file invalid;
  order='flag'    real records: every reversed pair is counted by pair type and
                  its episode is listed in flagged_for_review; the file stays
                  valid unless something else is wrong (schema, enumerations,
                  duplicates, impossible dates).
"""
import calendar
from dataclasses import dataclass, asdict, field
from datetime import date
from collections import defaultdict, Counter
from .schema import pathway_events, ENUMS, EVENT_TYPES, PATHWAY_ORDER

@dataclass
class ValidationReport:
    valid: bool
    rows: int
    episodes: int
    schema_errors: list[str]
    enum_errors: list[str]
    reversed_pairs: int
    duplicates: int
    impossible_dates: int
    missing_share: dict[str,float | None]
    pathway_order: str = PATHWAY_ORDER
    reversed_by_pair: dict[str,int] | None = None
    episodes_with_reversed_pair: int = 0
    order_mode: str = 'strict'
    flagged_for_review: list[str] = field(default_factory=list)
    def to_dict(self): return asdict(self)

ORDER_MODES = ('strict','flag')

def bounds(row):
    # MONTH observations represent ranges; only disjoint reversed ranges are errors.
    d=row['event_date']
    if d is None: return None
    if row['date_precision']=='DAY': return d,d
    return d.replace(day=1),d.replace(day=calendar.monthrange(d.year,d.month)[1])

def validate(table, roster=None, data_cut=None, order='strict'):
    if order not in ORDER_MODES: raise ValueError(f'order must be one of {ORDER_MODES}')
    schema_errors=[] if table.schema.equals(pathway_events) else ['Schema differs from pathway_events']
    enum_errors=[]
    for k,allowed in ENUMS.items():
        if k in table.column_names:
            bad=set(table[k].to_pylist())-set(allowed)
            if bad: enum_errors.append(f'{k}: {sorted(map(str,bad))}')
    if schema_errors:
        # Invalid physical types/columns cannot safely enter date/order checks.
        schema_errors.append('Date/order/duplicate checks unavailable until schema conforms')
        n=len(roster) if roster is not None else (len(set(table['episode_id'].to_pylist())) if 'episode_id' in table.column_names else 0)
        return ValidationReport(False,table.num_rows,n,schema_errors,enum_errors,0,0,0,{k:None for k in EVENT_TYPES},order_mode=order)
    groups=defaultdict(list); counts=Counter(); duplicates=0; impossible=0
    for row in table.to_pylist():
        groups[row['episode_id']].append(row)
        d=row['event_date']
        if d is None or not date(1900,1,1)<=d<=date(2200,12,31) or (data_cut and d>data_cut): impossible+=1
    reversed_pairs=0; by_pair=Counter(); bad_episodes=0; flagged=[]
    for episode,rows in groups.items():
        seen=Counter(x['event_type'] for x in rows)
        duplicates+=sum(max(0,n-1) for n in seen.values())
        counts.update(set(seen)&set(EVENT_TYPES))
        ordered=sorted([x for x in rows if x['event_type'] in EVENT_TYPES],key=lambda x:EVENT_TYPES.index(x['event_type']))
        before=reversed_pairs
        for a,b in zip(ordered,ordered[1:]):
            ba,bb=bounds(a),bounds(b)
            if ba and bb and ba[0]>bb[1]:
                reversed_pairs+=1; by_pair[f"{a['event_type']} > {b['event_type']}"]+=1
        if reversed_pairs>before: bad_episodes+=1; flagged.append(episode)
    n=len(roster) if roster is not None else len(groups)
    order_blocks=order=='strict' and reversed_pairs>0
    return ValidationReport(not(schema_errors or enum_errors or order_blocks or duplicates or impossible),table.num_rows,n,schema_errors,enum_errors,reversed_pairs,duplicates,impossible,{k:1-counts[k]/n if n else 0. for k in EVENT_TYPES},PATHWAY_ORDER,dict(sorted(by_pair.items())),bad_episodes,order,sorted(flagged))
