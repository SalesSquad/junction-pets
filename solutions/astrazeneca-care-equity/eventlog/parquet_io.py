from pathlib import Path
import pyarrow as pa
import pyarrow.dataset as ds
from .schema import pathway_events

def write_dataset(table, path, roster):
    years = {x['episode_id']:x['year'] for x in roster}
    t = table.append_column('year',pa.array([years[x] for x in table['episode_id'].to_pylist()],pa.int16()))
    partition = ds.partitioning(pa.schema([('year',pa.int16()),('county',pa.string())]),flavor='hive')
    fmt = ds.ParquetFileFormat()
    ds.write_dataset(t,str(path),format=fmt,file_options=fmt.make_write_options(compression='zstd'),partitioning=partition,existing_data_behavior='delete_matching')

def read_dataset(path):
    # Cast Hive string partition keys back to the declared dictionary schema.
    t = ds.dataset(str(path),format='parquet',partitioning='hive').to_table()
    return t.select(pathway_events.names).cast(pathway_events)
