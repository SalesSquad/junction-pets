"""Export only horizons with source-bound, disjoint evaluation evidence."""
import copy
import hashlib
from datetime import datetime, timezone
from common import *
from train_forecaster import fit, predict
from split_policy import horizon_evidence


def panel_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def county_methods(metrics):
    return {name: {h: rows[name] for h, rows in metrics['county'].items() if name in rows}
            for name in METHODS}


def export(a):
    torch.set_num_threads(2)
    p, x, years, targets, cats = load(a.panel)
    record = json.loads((Path(a.artifacts) / 'metrics.json').read_text())
    validate_manifest(record.get('split'))
    if record.get('panelSha256') != panel_digest(a.panel):
        raise ValueError('Panel changed since evaluation')
    metrics = record['metrics']
    evidence = {key: horizon_evidence(item['chosen'], item.get('validation', {}),
                county_methods(item), record.get('trainingSupport', {}).get(key, {}))
                for key, item in metrics.items()}
    for key, item in evidence.items():
        item['export'] = dict(status='WITHHELD', horizons={
            h: dict(exported=0, withheld=0, reasons=[])
            for h in ('h1', 'h2')})
    eligible = {key for key, item in evidence.items()
                if any(h['status'] == 'ELIGIBLE' for h in item['horizons'].values())}
    forecasts, outputmetrics = {}, {}
    selected = any(metrics[key]['chosen'] == 'transformer' for key in eligible)
    bundle = None
    if eligible:
        cal = torch.load(Path(a.artifacts) / 'calibration.pt', weights_only=False)
        w, y, m = windows(x, years, targets, years[:-1], window=a.window)
        ridge = fit_ridge(w, y, targets)
        if selected:
            old = torch.load(Path(a.artifacts) / 'backtest.pt', weights_only=False)
            validate_manifest(old.get('split'))
            if old.get('panelSha256') != panel_digest(a.panel):
                raise ValueError('Panel changed since training')
            epochs = max(1, int(np.median([len(h) for h in old['histories']])))
            bundle = fit(w, y, m, w, y, m, cats, targets, a, epochs)
            torch.save(bundle, Path(a.artifacts) / 'refit.pt')
    for j, k in enumerate(targets):
        key = p['indicators'][k]['key']
        method = metrics[key]['chosen']
        outputmetrics[key] = dict(chosen=method, **metrics[key]['county'])
        if key not in eligible:
            for h, result in evidence[key]['horizons'].items():
                evidence[key]['export']['horizons'][h]['reasons'] = result['reasons']
            continue  # A null winner is abstention, never a persistence fallback.
        forecasts[key] = {}
        for u, unit in enumerate(p['units']):
            if cats[u] != 1:
                continue
            valid = np.where(np.isfinite(x[u, :, k]))[0]
            if not len(valid):
                continue
            index = valid[-1]
            origin = int(years[index])
            fw, _, fm = windows(x, years, targets, [origin], window=a.window)
            n = next((i for i, value in enumerate(fm) if value[0] == u), None)
            if n is None:
                continue
            if method == 'transformer':
                q = predict(bundle, fw[n:n+1], fm[n:n+1], cats, targets, a.device)[0, j]
            else:
                q = baseline(fw[n:n+1], targets, method, ridge)[0, j, :, None] + cal['offsets'][method][j]
            q[:, 0] -= cal['widths'][method][j]
            q[:, 4] += cal['widths'][method][j]
            item = dict(lastYear=origin, lastValue=float(x[u, index, k]), pWorse={}, pBelowThreshold=None)
            for h in range(2):
                label = 'h' + str(h+1)
                disposition = evidence[key]['export']['horizons'][label]
                if evidence[key]['horizons'][label]['status'] != 'ELIGIBLE':
                    disposition['withheld'] += 1
                    disposition['reasons'] = evidence[key]['horizons'][label]['reasons']
                    continue
                if not valid_quantiles(q[h].tolist()):
                    disposition['withheld'] += 1
                    if 'INVALID_OR_COLLAPSED_QUANTILES' not in disposition['reasons']:
                        disposition['reasons'].append('INVALID_OR_COLLAPSED_QUANTILES')
                    continue
                item[label] = dict(year=origin+h+1, **dict(zip(['q05', 'q25', 'q50', 'q75', 'q95'], map(float, q[h]))))
                disposition['exported'] += 1
                evidence[key]['export']['status'] = 'EXPORTED'
            # Quantile interpolation is not a calibrated risk probability.
            if 'h1' in item or 'h2' in item:
                forecasts[key][unit['id']] = item
        if not forecasts[key]:
            del forecasts[key]
    save(a.out, dict(
        schemaVersion='care-equity-forecast-v1', generatedAt=datetime.now(timezone.utc).isoformat(),
        trainedOn=dict(device=a.device, seeds=a.seeds, epochs=a.epochs, transformerRefitted=selected),
        skippedIndicators=p.get('skippedIndicators', []), metrics=outputmetrics, forecasts=forecasts,
        evaluation=dict(split=record['split'], panelSha256=record['panelSha256'], indicators=evidence,
                        units=record.get('evaluationUnits', 'county test; pooled validation'),
                        limits=['No horizon is exported without positive validation and test support.',
                                'A new development evaluation is not an untouched prospective holdout.',
                                'Predictive intervals are empirical; calibrated risk probabilities are not supplied.'])))


def export_sweep(a):
    """Refit each eligible selected configuration; preserve null selections."""
    root = Path(a.artifacts)
    sweep = json.loads((root / 'sweep.json').read_text())
    validate_manifest(sweep.get('split'))
    for config in sweep['configs'].values():
        if panel_digest(config['configuration']['panel']) != config['panelSha256']:
            raise ValueError('Panel changed since sweep')
    if panel_digest(sweep['configuration']['panel']) != sweep['basePanelSha256']:
        raise ValueError('Base panel changed since sweep')
    groups = {}
    for key, chosen in sweep['chosen'].items():
        group = chosen if chosen and chosen.startswith('config-') else 'baselines'
        groups.setdefault(group, []).append(key)
    combined = dict(schemaVersion='care-equity-forecast-v1',
                    generatedAt=datetime.now(timezone.utc).isoformat(),
                    skippedIndicators=[], metrics={}, forecasts={},
                    evaluation=dict(split=sweep['split'], panelSha256=sweep['basePanelSha256'],
                                    indicators={}, units='all panel categories pooled',
                                    limits=sweep['limits']))
    choices = {}
    refitted = False
    for group, keys in groups.items():
        c = copy.copy(a)
        if group != 'baselines':
            for name, value in sweep['configs'][group]['configuration'].items():
                setattr(c, name, value)
        else:
            c.panel = sweep['configuration']['panel']
            c.window = 8
        c.device = a.device
        c.artifacts = str(root / 'export' / group)
        c.out = str(Path(c.artifacts) / 'forecast.json')
        Path(c.artifacts).mkdir(parents=True, exist_ok=True)
        p, x, years, targets, cats = load(c.panel)
        metrics = {}
        offsets = {name: np.zeros((len(targets), 2, 5)) for name in METHODS[1:]}
        widths = {name: np.zeros((len(targets), 2)) for name in METHODS}
        support = (sweep['configs'][group]['trainingSupport'] if group != 'baselines'
                   else sweep['trainingSupport'])
        for j, k in enumerate(targets):
            key = p['indicators'][k]['key']
            record = json.loads((root / ('selected-' + key + '.json')).read_text())
            selected = sweep['chosen'][key] if key in keys else None
            method = 'transformer' if selected and selected.startswith('config-') else selected
            test = record['test']['methods']
            scores = {('transformer' if name.startswith('config-') else name): hs for name, hs in test.items()}
            validation = {name: hs for name, hs in record['validation'].items() if name in METHODS[1:]}
            if selected and selected.startswith('config-'):
                validation['transformer'] = record['validation'][selected]
            metrics[key] = dict(chosen=method, validation=validation,
                county={h: {name: hs[h] for name, hs in scores.items()} for h in ('h1', 'h2')})
            for name, off in record['offsets'].items():
                offsets[name][j] = off
            for name, width in record['widths'].items():
                widths['transformer' if name.startswith('config-') else name][j] = width
        save(Path(c.artifacts) / 'metrics.json', dict(metrics=metrics, split=sweep['split'],
            panelSha256=panel_digest(c.panel), trainingSupport=support,
            evaluationUnits='all panel categories pooled'))
        torch.save(dict(offsets=offsets, widths=widths), Path(c.artifacts) / 'calibration.pt')
        if group != 'baselines':
            old_path = Path(sweep['configs'][group]['configuration']['artifacts']) / 'backtest.pt'
            bundle = torch.load(old_path, weights_only=False, map_location='cpu')
            torch.save(bundle, Path(c.artifacts) / 'backtest.pt')
        export(c)
        output = json.loads(Path(c.out).read_text())
        combined['skippedIndicators'] = output['skippedIndicators']
        refitted = refitted or output['trainedOn']['transformerRefitted']
        for key in keys:
            if key in output['forecasts']:
                combined['forecasts'][key] = output['forecasts'][key]
            chosen = sweep['chosen'][key]
            configuration = (sweep['configs'][chosen] if chosen and chosen.startswith('config-')
                else dict(method=chosen, panel=sweep['configuration']['panel'],
                          panelSha256=sweep['basePanelSha256'], window=8))
            choices[key] = configuration
            combined['metrics'][key] = dict(**output['metrics'][key], chosenConfig=configuration,
                validation=sweep['validation'][key], test=sweep['test'][key],
                evaluationUnits='all panel categories pooled')
            combined['evaluation']['indicators'][key] = dict(**output['evaluation']['indicators'][key],
                panelSha256=panel_digest(c.panel))
            combined['evaluation']['indicators'][key]['selectedCandidate'] = chosen
    combined['trainedOn'] = dict(device=a.device, selection=sweep['selection'], chosenConfigs=choices,
        seeds=sweep['configuration']['seeds'], epochs=sweep['configuration']['epochs'],
        transformerRefitted=refitted)
    save(a.out, combined)


def configure(p):
    p.add_argument('--grid', help=argparse.SUPPRESS)
    p.add_argument('--extended-panel', help=argparse.SUPPRESS)
    p.add_argument('--sweep', action='store_true', help='Refit/export validation-selected sweep winners')


if __name__ == '__main__':
    a = args(configure)
    if a.sweep:
        export_sweep(a)
    else:
        export(a)
