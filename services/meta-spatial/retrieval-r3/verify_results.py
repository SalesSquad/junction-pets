#!/usr/bin/env python3
"""Verify committed evidence and recompute metrics from compact score events.

An integrity pass preserves a failed product gate; it never grants deployment.
Large public feature/score caches may remain in the owner-controlled execution
archive. Their digests are recorded, while per-query events are committed here.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

from evaluation import exact_upper, validate_fresh, paired_family_bootstrap
from visual_adapter import load_selected, load_ablation
from train_visual import PROTOCOL, canonical, sha_bytes


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def equal(actual, expected, label):
    if isinstance(expected, float):
        if not math.isclose(actual, expected, abs_tol=1e-12, rel_tol=1e-12):
            raise ValueError('metric_mismatch:'+label)
    elif actual != expected:
        raise ValueError('value_mismatch:'+label)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, default=Path(__file__).with_name('results'))
    a = parser.parse_args()
    root = a.results.resolve()
    manifest = json.loads((root/'artifacts.json').read_text())
    for item in manifest['artifacts']:
        p = root/item['path']
        if p.is_symlink() or not p.resolve().is_relative_to(root) or p.stat().st_size != item['bytes'] or sha(p) != item['sha256']:
            raise ValueError('artifact_integrity_mismatch:'+item['path'])
    source = json.loads((root/'execution-source.json').read_text())
    verified_sources = 0
    for name, expected in source['source_files'].items():
        # Documentation evolves after the run. Executed code/protocol do not.
        if name.endswith('.py') or name in ('protocol.json','requirements.txt'):
            if sha(Path(__file__).with_name(name)) != expected:
                raise ValueError('executed_source_changed:'+name)
            verified_sources += 1
    data_bytes = gzip.decompress((root/'dataset.json.gz').read_bytes())
    data = json.loads(data_bytes)
    prior_bytes = gzip.decompress((Path(__file__).parent.parent/'retrieval-r2/results/dataset.json.gz').read_bytes())
    prior = json.loads(prior_bytes)
    validate_fresh(data, prior)
    training = json.loads((root/'training/report.json').read_text())
    selection = json.loads((root/'training/selection.json').read_text())
    report = json.loads((root/'evaluation/report.json').read_text())
    freeze = json.loads((root/'evaluation/evaluation-freeze.json').read_text())
    policies = json.loads((root/'evaluation/frozen-policies.json').read_text())
    equal(sha_bytes(canonical(PROTOCOL)), selection['protocol_sha256'], 'training_protocol')
    equal(sha(root/'training/selection.json'), report['selection_sha256'], 'selection_digest')
    equal(hashlib.sha256(data_bytes).hexdigest(), report['dataset_sha256'], 'fresh_dataset_digest')
    equal(hashlib.sha256(prior_bytes).hexdigest(), selection['dataset_sha256'], 'prior_dataset_digest')
    equal(source['source_commit'], report['source_commit'], 'executed_commit')
    equal(report['source_commit'], freeze['source_commit'], 'evaluation_freeze_commit')
    equal(report['selection_sha256'], policies['selection_sha256'], 'policy_selection_digest')
    equal(report['policies'], policies['policies'], 'frozen_policies')
    equal(selection['confirmation_candidate'], selection['primary'], 'primary_confirmation')
    equal(report['selection'], selection['primary'], 'evaluated_primary')
    equal(sha(Path(__file__).with_name('protocol.json')), report['protocol_sha256'], 'evaluation_protocol')
    load_selected(selection, root/'training')
    load_ablation(selection, root/'training')
    if len(training['candidates']) != 6:
        raise ValueError('six_fixed_training_candidates_required')
    for candidate in training['candidates']:
        if len(candidate['history']) != 12 or not candidate['gradient_observed'] or not candidate['parameter_update_observed']:
            raise ValueError('training_update_or_epoch_evidence_missing')
        for epoch in candidate['history']:
            if epoch['minimum_anchor_count'] != 1 or epoch['maximum_anchor_count'] != 1 or epoch['anchors_seen'] != 3313:
                raise ValueError('anchor_coverage_evidence_mismatch')
        if sha(root/'training'/candidate['final_checkpoint']) != candidate['final_checkpoint_sha256']:
            raise ValueError('final_checkpoint_mismatch')
    event_info = json.loads((root/'evaluation/score-events.json').read_text())
    equal(event_info['source_scores_sha256'], report['scores_sha256'], 'source_scores_digest')
    equal(sha(root/'evaluation/score-events.npz'), event_info['events_sha256'], 'events_digest')
    comparisons = 0
    test_predictions = {}
    with np.load(root/'evaluation/score-events.npz', allow_pickle=False) as events:
        for split in ('cal','test'):
            records = [r for r in data['records'] if r['split']==split]
            f = np.asarray([r['family_id'] for r in records])
            for method, result in report['partitions'][split].items():
                prefix = split+'__'+method+'__'
                ranks, predicted = events[prefix+'rank'], events[prefix+'predicted']
                confidence, absent = events[prefix+'confidence'], events[prefix+'absent_confidence']
                n = len(records)
                if any(v.shape != (n,) for v in (ranks,predicted,confidence,absent)):
                    raise ValueError('event_shape_mismatch')
                if np.any(ranks<1) or np.any(ranks>n) or np.any(predicted<0) or np.any(predicted>=n) or not np.isfinite(confidence).all() or not np.isfinite(absent).all():
                    raise ValueError('event_value_invalid')
                if not np.array_equal(ranks==1, predicted==np.arange(n)):
                    raise ValueError('rank_prediction_inconsistent')
                retrieval = result['retrieval']
                for k in (1,5,10): equal(float(np.mean(ranks<=k)),retrieval['recall_at_'+str(k)],prefix+'recall'+str(k))
                equal(float(np.mean(1/ranks)),retrieval['mrr'],prefix+'mrr')
                equal(float(np.mean(f[predicted]==f)),retrieval['family_recall_at_1'],prefix+'family_recall')
                threshold = report['policies'][method]['threshold']
                accepted = np.zeros(n,dtype=bool) if threshold is None else confidence>=threshold
                absent_accepted = np.zeros(n,dtype=bool) if threshold is None else absent>=threshold
                wrong = accepted & (predicted!=np.arange(n))
                errors = sum(bool(np.any((wrong|absent_accepted)[f==family])) for family in set(f))
                policy = result['policy']
                equal(float(accepted.mean()),policy['coverage'],prefix+'coverage')
                equal(int(accepted.sum()),policy['accepted'],prefix+'accepted')
                equal(int(wrong.sum()),policy['wrong_present_accepted'],prefix+'present_errors')
                equal(errors,policy['combined_families_with_any_error'],prefix+'combined_errors')
                equal(exact_upper(errors,len(set(f))),policy['combined_family_error_upper95'],prefix+'bound')
                comparisons += 1
                if split == 'test':
                    test_predictions[method] = predicted.copy()
    test_families = [r['family_id'] for r in data['records'] if r['split']=='test']
    # Bootstrap depends only on paired correctness events, not score magnitudes.
    one_hot = np.eye(len(test_families), dtype=np.uint8)
    paired = paired_family_bootstrap(one_hot[test_predictions['primary_visual']],
                                    one_hot[test_predictions['frozen_image_image']], test_families)
    equal(paired, report['paired_primary_vs_frozen'], 'paired_family_bootstrap')
    primary = report['partitions']['test']['primary_visual']
    policy = primary['policy']
    checks = {'recall_at_least_fixed_hybrid':primary['retrieval']['recall_at_1']>=report['partitions']['test']['frozen_hybrid_text_weight_0.25']['retrieval']['recall_at_1'],
              'coverage_at_least_20_percent':policy['coverage']>=.20,
              'zero_wrong_present_accepted':policy['wrong_present_accepted']==0,
              'combined_family_upper95_at_most_1_percent':policy['combined_family_error_upper95']<=.01}
    equal(checks,report['product_gate']['checks'],'gate_checks')
    equal('PASS' if all(checks.values()) else 'FAIL',report['product_gate']['status'],'gate_status')
    if report['production_activation'] is not False or report['physical_identity_verified'] is not False:
        raise ValueError('unsupported_activation_or_identity_claim')
    print(json.dumps({'status':'PASS','artifacts_verified':len(manifest['artifacts']),
                      'executed_sources_verified':verified_sources,'partition_methods_recomputed':comparisons,
                      'source_commit':report['source_commit'],'research_gate':report['product_gate']['status'],
                      'research_failure_preserved':report['product_gate']['status']=='FAIL',
                      'production_activation':False,'signed_or_hosted_qualification':False}))


if __name__ == '__main__':
    main()
