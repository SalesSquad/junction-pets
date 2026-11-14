"""Arrow contract. The spec leaves age-band limits and derived columns open;
we use 0-4 through 95-99, 100+, nullable durations and explicit censor flags.
Partition year is symptom-onset year (not the calendar year of each event).

EVENT_TYPES is the single pathway order shared by the simulator, the validator
and DATA_COLLECTION.md section 1: each event is on or after the one before it
(whole days, ties allowed). SPECIALIST_VISIT is the first visit to the treating
specialist, the milestone that sits just before TREATMENT_START.
"""
import pyarrow as pa
EVENT_TYPES = ['SYMPTOM_ONSET_REPORTED','FIRST_CONTACT','PHYSICIAN_ASSESSMENT','REFERRAL_SENT','REFERRAL_RECEIVED','DIAGNOSIS','MDT_DECISION','SPECIALIST_VISIT','TREATMENT_START']
PATHWAY_ORDER = ' <= '.join(EVENT_TYPES)
INDEX = {k:i for i,k in enumerate(EVENT_TYPES)}
DATE_PRECISIONS = ['DAY','MONTH']
COUNTIES = [f'HVA{i:02}' for i in range(1,22)] + ['HVA90','HVA91']
ENTRY_ROUTES = ['PUBLIC_PRIMARY','OCCUPATIONAL','PRIVATE','EMERGENCY','SCREENING']
CANCER_SITES = ['lung','colorectal','breast','prostate','haematological','other']
AGE_BANDS = [f'{i}-{i+4}' for i in range(0,100,5)] + ['100+']
SOURCES = ['STRUCTURED_FIELD','TEXT_EXTRACTED','PATIENT_REPORTED']
ENUMS = dict(event_type=EVENT_TYPES,date_precision=DATE_PRECISIONS,county=COUNTIES,entry_route=ENTRY_ROUTES,cancer_site=CANCER_SITES,age_band=AGE_BANDS,source=SOURCES)
D = pa.dictionary(pa.int8(),pa.string())
pathway_events = pa.schema([(k,D if k in ENUMS else t) for k,t in [
 ('episode_id',pa.string()),('event_type',D),('event_date',pa.date32()),('date_precision',D),('county',D),('entry_route',D),('cancer_site',D),('age_band',D),('source',D),('extraction_confidence',pa.float32()),('verified_by_human',pa.bool_()),('synthetic',pa.bool_())]])
# Intervals are named by their endpoint events, never by a bare position.
INTERVAL_EVENTS = dict(primary_care=('FIRST_CONTACT','REFERRAL_SENT'),diagnostic=('REFERRAL_SENT','DIAGNOSIS'),
                       treatment=('DIAGNOSIS','TREATMENT_START'),total=('FIRST_CONTACT','TREATMENT_START'))
INTERVALS = list(INTERVAL_EVENTS)
ENDPOINTS = [(INDEX[a],INDEX[b]) for a,b in INTERVAL_EVENTS.values()]
D2_ENDPOINTS = (INDEX['REFERRAL_RECEIVED'],INDEX['TREATMENT_START'])
# day_precision_<k>: both dates of the interval are known to the day (null when the interval is not observed).
pathway_intervals = pa.schema([('episode_id',pa.string()),('county',D),('entry_route',D)] + [(f'days_{k}',pa.int32()) for k in INTERVALS] + [(f'censored_{k}',pa.bool_()) for k in INTERVALS] + [(f'day_precision_{k}',pa.bool_()) for k in INTERVALS] + [('synthetic',pa.bool_())])

def events_table(rows):
    return pa.Table.from_pylist(rows,schema=pathway_events)
