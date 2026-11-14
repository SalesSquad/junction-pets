"""Summarize actual sponsor test receipts without uploading source or fixtures."""
import json
import pathlib
import sys
import xml.etree.ElementTree as ET

directory, source_sha = pathlib.Path(sys.argv[1]), sys.argv[2]
expected = {
    'MessagePack.SourceGenerator.Tests',
    'MessagePack.SourceGenerator.ExecutionTests',
    'MessagePack.SourceGenerator.MapModeExecutionTests',
    'MessagePack.Tests',
}
reports = []
for path in sorted(directory.glob('*.trx')):
    root = ET.parse(path).getroot()
    counters = next((node for node in root.iter() if node.tag.split('}')[-1] == 'Counters'), None)
    if counters is None:
        raise SystemExit('TRX lacks actual test counters')
    keys = ['total', 'executed', 'passed', 'failed', 'notExecuted', 'error', 'timeout', 'aborted', 'disconnected', 'inProgress', 'pending']
    values = {key: int(counters.get(key, '0')) for key in keys}
    summary = next((node for node in root.iter() if node.tag.split('}')[-1] == 'ResultSummary'), None)
    outcome = summary.get('outcome') if summary is not None else None
    reports.append({'suite': path.stem, 'outcome': outcome, **values})
missing = sorted(expected - {r['suite'] for r in reports})
abnormal = ['failed', 'error', 'timeout', 'aborted', 'disconnected', 'inProgress', 'pending']
ok = not missing and len(reports) == 4 and all(
    r['total'] > 0 and r['passed'] > 0 and r['executed'] == r['passed'] + r['failed']
    and r['outcome'] in {'Passed', 'Completed'} and all(r[key] == 0 for key in abnormal)
    for r in reports
)
result = {'scope': 'official-sponsor-own-suite-net8-regression', 'source_sha': source_sha, 'reports': reports, 'missing': missing, 'status': 'passed' if ok else 'failed'}
print(json.dumps(result, sort_keys=True))
if not ok:
    raise SystemExit(1)
