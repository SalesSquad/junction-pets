#!/usr/bin/env python3
"""Paired 60-second policies scored against every original 10-second M3 slot."""
import argparse
import gzip
import json
import math
from pathlib import Path
import subprocess
import numpy as np
import torch
from common import FEATURES, dump, load_data, model, probabilities, sha

STRATEGIES = ['A_timer_only', 'B_always_camera_no_AI', 'C_fixed_10min_no_AI',
              'D_selective_model', 'E_hold_fixed_10min_no_AI']


def camera_call(row, variant):
    """The ONLY policy access to M3's noisy occupancy proxy, only on a query.

    Repeated frames share the room/fault process: no independence assumption.
    Hidden truth is never consulted here.
    """
    s = row['sample']
    fresh = row['cheap'][5] <= 30 and s['connected']
    occupied = s['occupancy']
    if variant == 'correlated_false_empty' and 10 * 3600 <= row['second'] < 16 * 3600:
        occupied = 0  # One sustained correlated error, not independent frames.
    trusted = variant != 'untrusted_camera'
    return dict(empty=occupied == 0, valid=bool(fresh and trusted), second=row['second'] - row['cheap'][5])


def shield(baseline, cheap, camera, second, allow_empty):
    """Return hypothetical schedule or fan-OFF proposal; lights ALWAYS schedule.

    HOLD is represented by schedule accounting, never an OFF command. This is
    NOT M1 evaluate: 60 seconds exceeds its watchdog; no debounce claim is made.
    """
    action = dict(baseline)
    _, _, temp, rh, connected, age = cheap
    if not connected or age > 30 or temp >= 26 or rh >= 68:
        return action
    if camera is not None and camera['valid'] and camera['empty'] and second - camera['second'] <= 30 and allow_empty:
        action['fan'] = False
    return action


def evaluate_day(packet, net, meta, costs):
    rows = packet['rows']; variant = packet['variant']; day = packet['day']
    decisions = rows[::6]
    x = np.array([r['cheap'] for r in decisions], dtype=np.float32)
    mean = np.array(meta['normalization']['mean'], dtype=np.float32)
    std = np.array(meta['normalization']['std'], dtype=np.float32)
    p = probabilities(net, (x - mean) / std)
    lo, hi = np.array(meta['support']['min']), np.array(meta['support']['max'])
    outside = ((x < lo - 1e-5) | (x > hi + 1e-5)).any(axis=1)
    # Explicit distribution changes are unverified even when marginal ranges fit.
    # Offline rejection only: this day-level value NEVER enters a policy decision.
    unsupported_day = bool(outside.any() or variant != 'nominal' or day['scenario'] == 'fault')
    results = []
    for strategy in STRATEGIES:
        last = None; consecutive_empty = 0; queries = 0; inference_count = 0
        load_wh = baseline_wh = 0.; extra = unmet = baseline_unmet = 0
        drift_latched = False
        for i, row in enumerate(decisions):
            second = row['second']; baseline = row['baseline']; cheap = row['cheap']
            drift_latched = bool(drift_latched or outside[i])
            valid = bool(cheap[4] and cheap[5] <= 30)
            can_reduce = bool(baseline['fan'] and valid and cheap[2] < 26 and cheap[3] < 68)
            query = False; allow_empty = True
            if strategy == 'B_always_camera_no_AI':
                query = True
            elif strategy in ['C_fixed_10min_no_AI', 'E_hold_fixed_10min_no_AI']:
                query = second % 600 == 0
            elif strategy == 'D_selective_model':
                inference_count += 1
                stale = last is None or second - last['second'] > 30 or not last['valid']
                low = p[i] <= meta['low_probability_threshold']
                # One-minute upper-bound load value, not learned causal utility.
                # Uncertainty queries buy information only; uncertain means ON.
                uncertainty = 0.2 <= p[i] <= 0.8
                value_wh = (1 - float(p[i])) * 40 / 60
                query = bool(can_reduce and stale and not drift_latched and (low or uncertainty) and
                             value_wh > costs['query_wh'])
                allow_empty = bool(low and not drift_latched)
            if query:
                queries += 1; last = camera_call(row, variant)
                consecutive_empty = consecutive_empty + 1 if last['valid'] and last['empty'] else 0
            if strategy == 'E_hold_fixed_10min_no_AI':
                allow_empty = consecutive_empty >= 2  # corroboration is NOT independent evidence.
            # Learned proposals/queries occur only each minute. The deterministic
            # shield rechecks cheap sensors and camera expiry every original 10s;
            # an OFF permission cannot survive a newly stale/hot/disconnected slot.
            for fine in rows[i * 6:(i + 1) * 6]:
                b = fine['baseline']; truth = fine['truth']  # scoring ONLY
                action = b if strategy == 'A_timer_only' else shield(b, fine['cheap'], last, fine['second'], allow_empty)
                needed = truth['occupancy'] > 0 and (truth['temperature'] >= 27 or truth['humidity'] >= 70)
                baseline_wh += (40 * b['fan'] + 20 * b['light']) * 10 / 3600
                load_wh += (40 * action['fan'] + 20 * action['light']) * 10 / 3600
                extra += 10 * int(needed and b['fan'] and not action['fan'])
                unmet += 10 * int(needed and not action['fan'])
                baseline_unmet += 10 * int(needed and not b['fan'])
        board_wh = 0 if strategy == 'A_timer_only' else costs['board_w'] * 24
        camera_wh = queries * costs['query_wh'] + (24 * costs['always_camera_w'] if strategy == 'B_always_camera_no_AI' else 0)
        inference_wh = inference_count * costs['cheap_inference_wh']
        gross = baseline_wh - load_wh; net = gross - board_wh - camera_wh - inference_wh
        reasons = []
        if net <= 0: reasons.append('NON_POSITIVE_NET')
        if extra: reasons.append('EXTRA_MISSED_REQUIRED_FAN_SERVICE')
        if unsupported_day: reasons.append('OUTSIDE_VERIFIED_SYNTHETIC_SUPPORT')
        results.append(dict(day_id=day['day_id'], scenario=day['scenario'], seed=day['seed'], variant=variant,
                            strategy=strategy, baseline_load_wh=baseline_wh, policy_load_wh=load_wh,
                            gross_wh=gross, board_assumed_wh=board_wh, camera_assumed_wh=camera_wh,
                            cheap_inference_assumed_wh=inference_wh, net_wh=net, queries_per_day=queries,
                            cheap_inferences=inference_count, extra_missed_fan_seconds=extra,
                            missed_fan_seconds=unmet, baseline_missed_fan_seconds=baseline_unmet,
                            outside_support=unsupported_day, outside_range_decisions=int(outside.sum()),
                            candidate=strategy != 'A_timer_only' and not reasons, rejection_reasons=reasons))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True); parser.add_argument('--model', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--packets-gzip', help='Source-bound M3 offline stream for an executor without Node')
    parser.add_argument('--packets-sha256', help='Exact SHA-256 of the complete compressed stream')
    parser.add_argument('--board-w', type=float, default=4)
    parser.add_argument('--always-camera-w', type=float, default=1)
    parser.add_argument('--query-wh', type=float, default=0.01)
    parser.add_argument('--cheap-inference-wh', type=float, default=0.000001)
    a = parser.parse_args()
    costs = dict(board_w=a.board_w, always_camera_w=a.always_camera_w, query_wh=a.query_wh,
                 cheap_inference_wh=a.cheap_inference_wh)
    for k, v in costs.items():
        if not math.isfinite(v) or v < 0 or v > 30:
            raise ValueError('Cost must be finite 0..30: ' + k)
    if a.always_camera_w < 1 or a.board_w < 4 or a.query_wh <= 0:
        raise ValueError('Require camera >=1W, board >=4W, positive per-query Wh')
    manifest, _ = load_data(a.data)
    directory = Path(a.model); meta = json.loads((directory / 'metadata.json').read_text())
    if (meta['source_commit'] != manifest['source_commit'] or meta['sources'] != manifest['sources'] or
        meta['features'] != FEATURES or meta['dataset_manifest_sha256'] != sha(Path(a.data) / 'manifest.json') or
        meta['dataset_hashes'] != manifest['files'] or meta['weights_sha256'] != sha(directory / 'weights.pt')):
        raise ValueError('Source/dataset/model mismatch')
    net = model(); net.load_state_dict(torch.load(directory / 'weights.pt', map_location='cpu', weights_only=True)); net.eval()
    torch.set_num_threads(2)
    if bool(a.packets_gzip) != bool(a.packets_sha256):
        raise ValueError('Offline packets require both --packets-gzip and --packets-sha256')
    if a.packets_gzip:
        if len(a.packets_sha256) != 64 or sha(a.packets_gzip) != a.packets_sha256:
            raise ValueError('Offline packet SHA-256 mismatch or malformed digest')
        proc = None
        stream = gzip.open(a.packets_gzip, 'rt', encoding='utf-8')
    else:
        command = ['node', str(Path(__file__).with_name('export.mjs')),
                   '--evaluation=' + str(Path(a.data) / 'manifest.json')]
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
        stream = proc.stdout
    expected_packets = {
        (day['day_id'], variant): day
        for day in manifest['days'] if day['partition'] == 'test'
        for variant in ['nominal', 'drift', 'correlated_false_empty', 'untrusted_camera']
    }
    seen = set()
    days = []
    try:
        for line in stream:
            packet = json.loads(line)
            if not isinstance(packet, dict) or set(packet) != {'day', 'variant', 'rows'}:
                raise ValueError('Unexpected packet envelope')
            key = (packet['day'].get('day_id'), packet['variant'])
            if key not in expected_packets or key in seen or packet['day'] != expected_packets[key]:
                raise ValueError('Duplicate, unknown or altered M3 evaluation day')
            rows = packet['rows']
            if not isinstance(rows, list) or len(rows) != 8640 or any(
                row.get('second') != i * 10 for i, row in enumerate(rows)):
                raise ValueError('Missing, repeated or unordered 10-second M3 slots')
            seen.add(key)
            days.extend(evaluate_day(packet, net, meta, costs))
        if seen != set(expected_packets):
            raise ValueError(f'Missing M3 evaluation packets: {len(seen)} of {len(expected_packets)}')
        if proc is not None and proc.wait() != 0:
            raise RuntimeError('M3 regeneration/source check failed')
    finally:
        stream.close()
        if proc is not None and proc.poll() is None:
            proc.terminate(); proc.wait()
    expected = manifest['days_per_scenario'] * 4 * 4 * len(STRATEGIES)
    if len(days) != expected:
        raise ValueError('Missing paired days/stress variants')
    summaries = {}
    for strategy in STRATEGIES:
        subset = [d for d in days if d['strategy'] == strategy]
        summaries[strategy] = dict(mean_net_wh=float(np.mean([d['net_wh'] for d in subset])),
                                   worst_day_net_wh=min(d['net_wh'] for d in subset),
                                   mean_queries_per_day=float(np.mean([d['queries_per_day'] for d in subset])),
                                   worst_extra_missed_fan_seconds=max(d['extra_missed_fan_seconds'] for d in subset),
                                   candidate=all(d['candidate'] for d in subset))
    candidate = summaries['D_selective_model']['candidate']
    # Added value must also beat fixed polling and hold+poll on mean net and queries,
    # without worse service on ANY paired day. Never cherry-pick a scenario.
    for competitor in ['C_fixed_10min_no_AI', 'E_hold_fixed_10min_no_AI']:
        d = summaries['D_selective_model']; c = summaries[competitor]
        candidate = candidate and d['mean_net_wh'] > c['mean_net_wh'] and d['mean_queries_per_day'] < c['mean_queries_per_day']
        paired = {(r['day_id'], r['variant']): r for r in days if r['strategy'] == competitor}
        candidate = candidate and all(r['extra_missed_fan_seconds'] <= paired[(r['day_id'], r['variant'])]['extra_missed_fan_seconds']
                                      for r in days if r['strategy'] == 'D_selective_model')
    report = dict(schema='green-edge.active.policy.v1', evidence='SYNTHETIC/OFFBOARD', physical_execution=False,
                  source_commit=manifest['source_commit'], sources=manifest['sources'],
                  dataset_manifest_sha256=sha(Path(a.data) / 'manifest.json'), weights_sha256=meta['weights_sha256'],
                  evaluator_sha256=sha(__file__), costs_assumed=costs, summary=summaries, days=days,
                  candidate=candidate, verdict='SYNTHETIC_CANDIDATE_ONLY' if candidate else 'NO_GO',
                  semantics='MLP/query decisions at 60s, deterministic expiry/sensor shield at original 10s; M1 watchdog/debounce NOT executed; HOLD accounts schedule; no causal HVAC effect',
                  limits=['No hardware or calibrated energy', 'Range support is not a drift detector or safety certificate',
                          'Fault and stress distributions are unverified and veto qualification',
                          'Correlated frames are not independent; repeated false-empty may evade shields',
                          'VOI is an authored one-minute load upper bound, not measured or learned utility'])
    dump(a.out, report)
    print(json.dumps(dict(verdict=report['verdict'], summary=summaries), indent=2))


if __name__ == '__main__':
    main()
