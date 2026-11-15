"""Render a new evaluation without inventing execution or test claims."""
import argparse
import json
from pathlib import Path
from split_policy import validate_manifest


def main():
    root = Path(__file__).resolve().parent
    default = root / 'artifacts' / 'target-year-disjoint-v1'
    parser = argparse.ArgumentParser()
    parser.add_argument('--metrics', type=Path, default=default / 'metrics.json')
    parser.add_argument('--out', type=Path, default=default / 'RUN_REPORT.md')
    args = parser.parse_args()
    report = json.loads(args.metrics.read_text())
    validate_manifest(report.get('split'))
    config = report.get('configuration', {})
    lines = ['# Recorded development evaluation', '',
             'Source: ' + str(args.metrics),
             'Panel SHA-256: ' + str(report.get('panelSha256', 'not recorded')),
             'Recorded configuration: ' + json.dumps({k: config.get(k) for k in ('device', 'seeds', 'epochs')}),
             'Executed epochs by seed: ' + json.dumps(report.get('executedEpochs')),
             '', 'No test-suite, API-fetch or clinical-performance claim is inferred from these metrics.', '']
    for group in ('county', 'municipality'):
        lines += ['## ' + group, '', '| Indicator | Horizon | Method | MAE | n |', '|---|---|---|---:|---:|']
        for key, item in report['metrics'].items():
            for horizon, methods in item.get(group, {}).items():
                for method, value in methods.items():
                    mae = value.get('mae')
                    lines.append('| ' + ' | '.join([key, horizon, method,
                        'unavailable' if mae is None else format(mae, '.4f'), str(value.get('n', 0))]) + ' |')
    lines += ['', '## Limits', '', *report.get('limits', [])]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Never replace an existing report: use a new --out for a new experiment.
    with args.out.open('x') as handle:
        handle.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
