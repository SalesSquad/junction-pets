#!/usr/bin/env python3
"""Manual-only V12 pilot. Real original TRAIN physics; science RED exits nonzero.

No dispatch API. No fitting, followup, DEV, TEST or OOD. All 144 original traces
and all 512 public starts survive scientific STOP as losslessly packed evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SOURCE_SHA = '64c9a32bf983c26099ece11f1c3a0f6da5bc4f1d'
V11_SHA = 'ab6df4054ef6ed350b479469590a48046a0c0a68'
WINDOW_END = '2026-11-15T17:00:00+00:00'
PRODUCT = Path('solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco')
SCHEMA = 'junction.rokoko.v12-pilot.craci.train.v1'
ARMS = ('frozen_v5', 'v12_phase_dwell_supported_actions',
        'v12_right_side_action4_exploration_train_only')


def require(ok, reason):
    if not ok:
        raise AssertionError(reason)


def load(path, name):
    require(path.is_file() and not path.is_symlink(), 'V12_SOURCE_FILE_REQUIRED')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, obj):
    with path.open('x', encoding='utf8') as f:
        json.dump(obj, f, sort_keys=True, separators=(',', ':'), allow_nan=False)
        f.write('\n')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def admission(env, now=None):
    now = now or datetime.now(timezone.utc)
    require(env.get('CRACI_CREDIT_WINDOW_OPEN') == 'true' and
            env.get('CRACI_WINDOW_END') == '2026-11-15T17:00:00Z' and
            (datetime.fromisoformat(WINDOW_END) - now).total_seconds() >= 3600,
            'V12_LIVE_MIN_60_MINUTES_CREDIT_REQUIRED')
    require(env.get('CRACI_SOURCE_SHA') == SOURCE_SHA and
            env.get('CRACI_WORKLOAD') == 'rokoko-mujoco-v12-pilot' and
            env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch' and
            env.get('GITHUB_RUN_ATTEMPT') == '1', 'V12_MANUAL_EXACT_SOURCE_FIRST_ATTEMPT_ONLY')


def source_contract(source):
    protocol = load(source / PRODUCT / 'v12_learning/protocol.py', 'v12_frozen_protocol')
    policy = load(source / PRODUCT / 'v12_learning/policy.py', 'v12_frozen_policy')
    frozen = source / PRODUCT / 'v12_learning/frozen-real-train-v10-v11-final'
    plan = protocol.verified_plan(frozen / 'next-train-plan.json')
    model = policy.load_frozen_model(frozen / 'model.json')
    require(tuple(protocol.PILOT_ARMS) == ARMS and
            [int(a) for a, m in model['models'].items() if m['supported']] == [1, 2, 3, 5],
            'V12_ACTION_SUPPORT_OR_ARM_DRIFT')
    return protocol, policy, plan, frozen


def matrix_readout(protocol, plan, scans, cohort, trials):
    science = protocol.paired_physical_goal_readout(
        trials, cohort, 'pilot', all_512_initial_public_worlds=scans, plan=plan)
    # Stronger host gate: retain and reject unsafe in ANY arm, including V5.
    unsafe = [[r['seed'], r['strategy']] for r in trials if r['unsafe']]
    science['anyArmUnsafeTrialKeys'] = unsafe
    science['hostScienceRed'] = bool(science['hardStopNoFurtherPhysics'] or unsafe)
    return science


def verify_terminal(row, trace):
    require(trace and len(trace) == row['option_steps'] == row['full_transition_count'] and
            trace[-1]['done'] is True and all(not t['done'] for t in trace[:-1]),
            'V12_INCOMPLETE_OR_POST_TERMINAL_OPTIONS')
    for t in trace:
        require(type(t['action']) is int and 0 <= t['action'] < 7 and
                len(t['mask']) == 7 and t['mask'][t['action']] == 1,
                'V12_ILLEGAL_ORIGINAL_ACTION')
    physical = (row['dwell_ticks_final'] >= 250 and row['contacts'] > 0 and
                row['final_error'] < .02 and not row['unsafe'])
    require(row['success'] == physical and
            trace[-1]['success_info'] == physical and
            trace[-1]['dwell_ticks_current'] == row['dwell_ticks_final'],
            'V12_ORIGINAL_CONTACT_20MM_250_ACTUAL_TICKS_REQUIRED')


def verify_raw(output, protocol, plan):
    # The final outer manifest adds proofs without changing the original
    # producer manifest. Audit either the pre-replay or final retained tree.
    manifest_path = output / 'manifest.json'
    if (output / 'original-manifest.json').exists():
        outer = json.loads(manifest_path.read_text())
        require(outer['executed_head'] == SOURCE_SHA and
                set(outer['file_sha256']) == {p.name for p in output.iterdir()} - {'manifest.json'} and
                all(sha(output / n) == digest for n, digest in outer['file_sha256'].items()),
                'V12_OUTER_ORIGINAL_HASH_MISMATCH')
        manifest_path = output / 'original-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    require(manifest['schema'] == SCHEMA + '.manifest' and
            manifest['executed_head'] == SOURCE_SHA and
            set(manifest['file_sha256']) ==
            {'training.json', 'full_transitions.jsonl.gz', 'paired-readout.json'} and
            all(sha(output / name) == digest for name, digest in manifest['file_sha256'].items()),
            'V12_ORIGINAL_HASH_OR_SOURCE_MISMATCH')
    training = json.loads((output / 'training.json').read_text())
    require(training['executed_head'] == SOURCE_SHA and training['stage'] == 'pilot' and
            training['training_only'] is True and training['model_promotion_authorized'] is False,
            'V12_TRAIN_ONLY_SOURCE_BINDING_REQUIRED')
    expected = matrix_readout(protocol, plan, training['all_512_public_initial_scans'],
                              training['cohort'], training['trials'])
    require(expected == json.loads((output / 'paired-readout.json').read_text()),
            'V12_SCIENCE_READOUT_NOT_RAW')
    rows = {(r['seed'], r['strategy']): r for r in training['trials']}
    seen = set()
    with gzip.open(output / 'full_transitions.jsonl.gz', 'rt') as f:
        for line in f:
            doc = json.loads(line)
            key = (doc['seed'], doc['strategy'])
            require(key in rows and key not in seen, 'V12_DUPLICATE_OR_EXTRA_RAW_TRACE')
            seen.add(key)
            trace = doc['transitions']
            for t in trace:
                protocol.public_abi(t['observation'], t['mask'])
                protocol.public_abi(t['next_observation'], t['mask'])
            canonical = json.dumps(trace, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
            require(hashlib.sha256(canonical).hexdigest() == rows[key]['full_transition_sha256'],
                    'V12_FULL_TRACE_SHA_MISMATCH')
            verify_terminal(rows[key], trace)
    require(seen == set(rows) and len(seen) == 144, 'V12_MISSING_RAW_TRIAL')
    return training, expected


def publish(output, collector, harness):
    """Reuse V11 binary chunk writer + independent exact reassembly verifier.

    Only V12 source proof differs. No V11 schema/800-trial claim is fabricated.
    Incomplete execution can also be retained, but can never qualify science.
    """
    pack = load(harness / 'scripts/craci/rokoko-mujoco-v11-retain-evidence.py',
                'v12_reused_v11_binary_packer')
    names = tuple(sorted(p.name for p in output.iterdir()))
    require(all(p.is_file() and not p.is_symlink() for p in output.iterdir()),
            'V12_UNSAFE_PRIVATE_EVIDENCE')
    # Everything is an original binary source, including proof/plan files, so
    # JSON collector caps cannot truncate large public scans or sparse traces.
    # The existing reassembly verifier expects the readout in the proof set.
    pack.SOURCE_FILES = tuple(n for n in names if n not in ('manifest.json', 'paired-readout.json'))
    pack.PROOF_FILES = ('manifest.json', 'paired-readout.json')
    pack.MANIFEST_SCHEMA = SCHEMA + '.manifest'
    pack.SCHEMA = SCHEMA + '.retention'
    pack.CHUNK_BYTES = 6 * 1024 * 1024 - 2048  # ZIP overhead still <=6 MiB
    def proof(private):
        m = json.loads((private / 'manifest.json').read_text())
        require(m['schema'] == pack.MANIFEST_SCHEMA and m['executed_head'] == SOURCE_SHA and
                set(m['file_sha256']) == set(pack.SOURCE_FILES) | {'paired-readout.json'} and
                all(sha(private / n) == h for n, h in m['file_sha256'].items()),
                'V12_RETENTION_ORIGINAL_SHA_MISMATCH')
        return m
    pack.source_proof = proof
    return pack.publish_private_source(output, collector)


def runtime(source, harness, temp):
    # Use V11 reviewed immutable checkpoint staging and historical source checks.
    v11 = load(harness / 'scripts/craci/rokoko-mujoco-v11-prospective-qualification.py',
               'v12_reused_v11_qualifier')
    inputs = v11.verify_frozen_input_files(source, temp / 'v12-private-checkpoints')
    sys.path.insert(0, str(source / PRODUCT / 'v11_learning'))
    original = load(source / PRODUCT / 'v11_learning/prospective_train.py',
                    'v12_original_v11_import_safe_runner')
    raw = (source / PRODUCT / 'v10_prospective/run.py').read_bytes()
    require(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() ==
            original.ORIGINAL_V10_BLOB, 'V12_ORIGINAL_V10_RUNNER_BLOB_DRIFT')
    old = load(source / PRODUCT / 'v10_prospective/run.py', 'v12_original_v10_runner')
    old.verify_historical_source(source)
    require(subprocess.run(['git', '-C', str(source), 'merge-base', '--is-ancestor',
                            V11_SHA, 'HEAD'], capture_output=True).returncode == 0,
            'V12_ORIGINAL_V11_LINEAGE_REQUIRED')
    v7, Env = old.v8.import_v7_and_physics()
    require(Path(sys.modules['policy'].__file__).resolve() ==
            source / PRODUCT / 'v5_learning/policy.py' and
            Path(sys.modules['physics'].__file__).resolve() == source / PRODUCT / 'physics.py',
            'V12_ORIGINAL_POLICY_OR_PHYSICS_IMPORT_COLLISION')
    frozen_v8, _, _ = old.v8.verify_frozen_model(inputs['weights.json'],
        inputs['training-receipt.json'], old.v8.FROZEN_WEIGHTS_SHA256)
    baseline = old.policy_factory('frozen_v5', inputs['candidate-weights.json'],
                                  frozen_v8, frozen_v7=v7)
    return old.v8, v7, Env, v7.v6.v5.v4.v3.v2.v1._world_signature, baseline


def main():
    admission(os.environ)
    import mujoco
    import numpy
    require(mujoco.__version__ == '3.3.7' and numpy.__version__ == '2.3.4',
            'V12_EXACT_ORIGINAL_SIMULATOR_VERSIONS_REQUIRED')
    source = Path(os.environ['CRACI_SOURCE_ROOT']).resolve(strict=True)
    harness = Path(os.environ['CRACI_HARNESS_ROOT']).resolve(strict=True)
    temp = Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    for root, head in ((source, SOURCE_SHA), (harness, os.environ['CRACI_HARNESS_SHA'])):
        require(len(head) == 40 and git(root, 'rev-parse', 'HEAD') == head and
                git(root, 'status', '--porcelain=v1') == '', 'V12_CLEAN_PINNED_CHECKOUT_REQUIRED')
    protocol, policy, plan, frozen = source_contract(source)
    runner, v7, Env, signature, baseline = runtime(source, harness, temp)
    factories = {ARMS[0]: baseline,
                 ARMS[1]: policy.policy_factory(baseline, frozen / 'model.json'),
                 ARMS[2]: policy.right4_train_only_factory(baseline, frozen / 'model.json')}
    output = temp / 'v12-pilot-private-originals'
    require(not output.exists(), 'V12_FRESH_PRIVATE_OUTPUT_REQUIRED')
    output.mkdir(mode=0o700)
    deadline = time.monotonic() + 1200  # execution + all-trial replay, below 30min job cap
    training = dict(schema=SCHEMA + '.training', executed_head=SOURCE_SHA,
                    harness_sha=os.environ['CRACI_HARNESS_SHA'], stage='pilot', training_only=True,
                    actual_physics_engine='mujoco-3.3.7', numpy_version='2.3.4', strategies=list(ARMS),
                    model_promotion_authorized=False, dev_cal_test_ood_opened=False,
                    all_512_public_initial_scans=[], cohort=[], trials=[])
    science = {'hostScienceRed': True, 'scienceDecision': 'STOP_INCOMPLETE'}
    proof = dict(schema=SCHEMA, experiment_complete=False, science_gate='RED',
                 exact_source_sha=SOURCE_SHA, harness_sha=os.environ['CRACI_HARNESS_SHA'],
                 actual_provider_cost='unknown', model_promotion_authorized=False,
                 dev_cal_test_ood_opened=False, plan_sha256=protocol.PLAN_SHA256,
                 model_sha256=protocol.MODEL_SHA256,
                 original_source_files_sha256={str(p): sha(source / PRODUCT / p) for p in map(Path,
                     ('physics.py', 'moving_scene.xml', 'v5_learning/policy.py',
                      'v11_learning/prospective_train.py', 'v12_learning/protocol.py', 'v12_learning/policy.py'))},
                 tuple=dict(source=SOURCE_SHA,
                 seed_range=[518000, 518511], stage='pilot'))
    error = None
    try:
        env = Env(max_options=60)
        for seed in range(518000, 518512):
            require(time.monotonic() < deadline, 'V12_BOUNDED_SCAN_DEADLINE')
            obs = env.reset(seed=seed, ood=False)
            training['all_512_public_initial_scans'].append(dict(seed=seed,
                world_hash=str(signature(env)), observation=obs.tolist(), mask=env.mask(obs).astype(int).tolist()))
        cohort = protocol.derive_cohort(training['all_512_public_initial_scans'], plan, 'pilot')
        training['cohort'] = cohort
        with gzip.open(output / 'full_transitions.jsonl.gz', 'xt') as sink:
            for world in cohort:
                for arm in ARMS:
                    row, trace = runner.run_real_episode(env, world['seed'], arm,
                        factories[arm], signature, deadline, v7)
                    require(row['world_hash'] == world['world_hash'], 'V12_PAIRED_WORLD_DRIFT')
                    training['trials'].append(row)
                    sink.write(json.dumps(dict(seed=world['seed'], strategy=arm, transitions=trace),
                                          sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')
                    verify_terminal(row, trace)
        science = matrix_readout(protocol, plan, training['all_512_public_initial_scans'], cohort, training['trials'])
        write(output / 'training.json', training)
        write(output / 'paired-readout.json', science)
        write(output / 'manifest.json', dict(schema=SCHEMA + '.manifest', executed_head=SOURCE_SHA,
              file_sha256={n: sha(output / n) for n in ('training.json', 'paired-readout.json', 'full_transitions.jsonl.gz')}))
        checked, _ = verify_raw(output, protocol, plan)
        # Independent pass re-executes every initial world and EVERY trial,
        # including every near/clear positive, negative and RIGHT4 probe.
        replay_env = Env(max_options=60)
        for scan in checked['all_512_public_initial_scans']:
            require(time.monotonic() < deadline, 'V12_BOUNDED_REPLAY_DEADLINE')
            obs = replay_env.reset(seed=scan['seed'], ood=False)
            require(obs.tolist() == scan['observation'] and str(signature(replay_env)) == scan['world_hash'] and
                    replay_env.mask(obs).astype(int).tolist() == scan['mask'], 'V12_INITIAL_WORLD_REPLAY_DRIFT')
        rows = {(r['seed'], r['strategy']): r for r in checked['trials']}
        with gzip.open(output / 'full_transitions.jsonl.gz', 'rt') as stream:
            for line in stream:
                doc = json.loads(line)
                row, trace = runner.run_real_episode(replay_env, doc['seed'], doc['strategy'],
                    factories[doc['strategy']], signature, deadline, v7)
                require(row == rows[doc['seed'], doc['strategy']] and trace == doc['transitions'],
                        'V12_ALL_TRIAL_ORIGINAL_ACTION_GOAL_REPLAY_DIVERGED')
                verify_terminal(row, trace)
        proof.update(experiment_complete=True, all_512_worlds_replayed=True,
                     all_144_trials_replayed=True, independent_near_clear_positive_replay=True,
                     science_gate='RED' if science['hostScienceRed'] else 'TRAIN_ONLY_REVIEW')
    except Exception as exc:
        error = type(exc).__name__ + ': ' + str(exc)
        proof['failure'] = error
    finally:
        # Preserve original files unchanged; add an envelope binding ALL bytes,
        # including failed/incomplete runs, before V11 lossless packaging.
        if not (output / 'training.json').exists(): write(output / 'training.json', training)
        if not (output / 'paired-readout.json').exists(): write(output / 'paired-readout.json', science)
        if not (output / 'full_transitions.jsonl.gz').exists():
            with gzip.open(output / 'full_transitions.jsonl.gz', 'xt'): pass
        for name in ('model.json', 'next-train-plan.json'):
            with (output / name).open('xb') as f: f.write((frozen / name).read_bytes())
        write(output / 'qualification.json', proof)
        if (output / 'manifest.json').exists():
            (output / 'manifest.json').rename(output / 'original-manifest.json')
        write(output / 'manifest.json', dict(schema=SCHEMA + '.manifest', executed_head=SOURCE_SHA,
              harness_sha=os.environ['CRACI_HARNESS_SHA'],
              file_sha256={p.name: sha(p) for p in output.iterdir()}))
        publish(output, Path(os.environ['CRACI_RECEIPT_DIR']) / 'artifacts/rokoko-mujoco-v12-pilot', harness)
    print(json.dumps(proof, sort_keys=True))
    return 1 if error or science['hostScienceRed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
