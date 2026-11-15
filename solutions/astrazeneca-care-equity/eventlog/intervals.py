"""Complete observed spans; censor flags are distinct from missing endpoints.
No invalid negative or duplicate-endpoint span is silently repaired.
Censored spans are lower bounds only if the start is observed and the endpoint
is known (from the synthetic roster) to lie after the administrative cutoff.
"""
from collections import defaultdict
from datetime import date
import pyarrow as pa
from .schema import EVENT_TYPES, INTERVALS, ENDPOINTS, pathway_intervals

def derive(table, roster, data_cut=None):
    events=defaultdict(lambda:defaultdict(list))
    precision=defaultdict(dict)
    for r in table.to_pylist():
        events[r['episode_id']][r['event_type']].append(r['event_date'])
        precision[r['episode_id']][r['event_type']]=r['date_precision']
    rows=[]
    for ep in roster:
        row={k:ep[k] for k in ['episode_id','county','entry_route','synthetic']}
        found=events[ep['episode_id']]
        for name,(a,b) in zip(INTERVALS,ENDPOINTS):
            starts,ends=found[EVENT_TYPES[a]],found[EVENT_TYPES[b]]
            censored=EVENT_TYPES[b] in ep.get('administratively_censored',[])
            days=None; exact=None
            if len(starts)==1 and len(ends)==1:
                days=(ends[0]-starts[0]).days
                kinds=precision[ep['episode_id']]
                exact=kinds[EVENT_TYPES[a]]=='DAY' and kinds[EVENT_TYPES[b]]=='DAY'
            elif len(starts)==1 and not ends and censored and data_cut:
                days=(data_cut-starts[0]).days
            row['days_'+name]=days
            row['censored_'+name]=censored
            row['day_precision_'+name]=exact
        rows.append(row)
    return pa.Table.from_pylist(rows,schema=pathway_intervals)
