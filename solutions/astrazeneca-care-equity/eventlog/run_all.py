"""Run from project root: eventlog/.venv/bin/python -m eventlog.run_all."""
import argparse,json,time,platform
from datetime import date
from pathlib import Path
import numpy as np
import pyarrow as pa
from .log import log

def write_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--replications',type=int,default=1000);p.add_argument('--seed',type=int,default=20261114);a=p.parse_args()
    command='python -m eventlog.run_all'; started=time.monotonic()
    log('run_start',command,inputs=['DATA_COLLECTION.md','data/snapshot/public-v1.json'],metrics=dict(seed=a.seed,replications=a.replications,python=platform.python_version(),numpy=np.__version__,pyarrow=pa.__version__))
    try:
        from .simulate import simulate,populations
        from .parquet_io import write_dataset,read_dataset
        from .validate import validate
        from .intervals import derive
        from .aggregate import aggregate
        from .detect import detect
        from .design_study import run
        out=Path('data/eventlog');out.mkdir(exist_ok=True,parents=True)
        cut=date(2026,12,31)
        table,roster=simulate(national_cases=20000,seed=a.seed,data_cut=cut)
        write_dataset(table,out/'sample',roster)
        reloaded=read_dataset(out/'sample')
        report=validate(reloaded,roster,cut)
        write_json(out/'validation-report.json',dict(schemaVersion='1.1',seed=a.seed,data_cut=cut.isoformat(),synthetic=True,**report.to_dict()))
        # One pathway order (schema.EVENT_TYPES) is shared by simulator and validator.
        # The validator still only reports; it never moves a date.
        interval=derive(reloaded,roster,cut)
        import pyarrow.parquet as pq
        pq.write_table(interval,out/'sample-intervals.parquet',compression='zstd')
        write_json(out/'sample-roster.json',roster)
        write_json(out/'county-intervals.json',dict(schemaVersion='1.1',seed=a.seed,synthetic=True,population_year=populations()[0],national_cases_assumption=37000,sample_cases=20000,data_cut=cut.isoformat(),thresholds_are_assumptions=True,
            log_duration='log(days); a zero-day interval is logged as 0.5 day',statistics=aggregate(interval),detection=detect(interval)))
        log('sample_and_aggregate',command,outputs=[str(out/'sample'),str(out/'validation-report.json'),str(out/'county-intervals.json')],metrics=dict(episodes=len(roster),events=table.num_rows,valid=report.valid,chronology_violations=report.reversed_pairs,duplicates=report.duplicates,impossible_dates=report.impossible_dates))
        study=run(a.replications,a.seed)
        study['sample_validation']=dict(episodes=len(roster),events=table.num_rows,chronology_violations=report.reversed_pairs,
            episodes_with_violation=report.episodes_with_reversed_pair,duplicates=report.duplicates,impossible_dates=report.impossible_dates,valid=report.valid)
        study['findings'].insert(1,f"The synthetic Parquet sample of {len(roster)} episodes and {table.num_rows} events validates with {report.reversed_pairs} chronology violations, {report.duplicates} duplicates and {report.impossible_dates} impossible dates.")
        write_json(out/'design-study-v1.json',study)
        log('study_complete',command,outputs=[str(out/'design-study-v1.json')],metrics=dict(grid_cells=len(study['design_grid']),
            sd_log_duration=study['sample_sizes']['sigma_by_interval'],sample_sizes=study['sample_sizes']['rows'],
            largest_sample_size_check_gap=study['largest_sample_size_check_gap'],
            largest_power_gap_day_precision_complete=study['largest_power_gap_day_precision_complete'],
            largest_power_gap=study['largest_absolute_power_gap'],elapsed_seconds=time.monotonic()-started))
        from .audit import write_results
        write_results(out)
        log('results_markdown',command,inputs=[str(out/'design-study-v1.json'),str(out/'validation-report.json')],outputs=['eventlog/RESULTS.md'])
        print(json.dumps(dict(episodes=len(roster),events=table.num_rows,valid=report.valid,chronology_violations=report.reversed_pairs,findings=study['findings']),indent=1),flush=True)
    except Exception as e:
        log('run_failed',command,metrics={'error':str(e)},status='failed');raise

if __name__=='__main__': main()
