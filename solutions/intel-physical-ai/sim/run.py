#!/usr/bin/env python3
"""CPU SO101 rigid-body replay. No hardware, learned policy, perception or sorting."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import time

from bridge import (Bridge, FRAMES, FAULT_FRAME, ROOT, SCENARIOS, sha,
                    validate_model, verify_episode)
from motion import desired_pose


def write_json(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')


def source_state():
    files = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py', '.json', '.txt', '.md')]
    return {'git_head': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
            'files_sha256': {p.name: sha(p) for p in sorted(files)}}


def simulate(model, mode, seed, directory, capture):
    import mujoco
    import numpy as np
    directory.mkdir()
    (directory / 'frames').mkdir()
    data = mujoco.MjData(model)
    rng = np.random.default_rng(seed)
    adr = int(model.jnt_qposadr[6])
    data.qpos[adr:adr+7] = [0.31 + rng.uniform(-.015, .015), rng.uniform(-.03, .03), .042, 1, 0, 0, 0]
    bounds = np.asarray(model.actuator_ctrlrange[:6])
    data.ctrl[:] = desired_pose(0, seed, bounds)
    mujoco.mj_forward(model, data)
    bridge = Bridge()
    hold_target = None
    renderer = mujoco.Renderer(model, height=120, width=160) if capture else None
    try:
        with (directory / 'trace.jsonl').open('x') as stream:
            for index in range(FRAMES):
                fault = mode if index >= FAULT_FRAME and mode != 'nominal' else None
                injection = {'source': 'SYNTHETIC_FAULT_INJECTION', 'fault': fault}
                while data.time < (index + 1) / 30 - 1e-8:
                    mujoco.mj_step(model, data)
                camera = {'identity': f'wrist_cam:{index}', 'frame_index': index,
                          'present': capture, 'captured_at_s': float(data.time),
                          'source': 'SIM_PHYSICS_RENDER', 'path': None, 'sha256': None}
                if renderer is not None:
                    renderer.update_scene(data, camera='wrist_cam')
                    pixels = np.ascontiguousarray(renderer.render())
                    relative = f'frames/{index:04d}.ppm'
                    path = directory / relative
                    with path.open('xb') as image:
                        image.write(b'P6\n160 120\n255\n' + pixels.tobytes())
                    camera.update(path=relative, sha256=sha(path))
                gate = bridge.observe(camera, index, float(data.time), injection)
                # Validate this capture BEFORE issuing the next interval's target.
                emitted = gate['command_allowed']
                hold_override_applied = False
                if emitted:
                    hold_target = None
                    data.ctrl[:] = desired_pose(index, seed, bounds)
                else:
                    if hold_target is None:
                        # Controlled simulated servo hold (NOT power-off E-stop).
                        # Previous moving command must not remain energized.
                        hold_target = np.clip(data.qpos[:6].copy(), bounds[:, 0], bounds[:, 1])
                        data.ctrl[:] = hold_target
                        hold_override_applied = True
                contacts = [{'geom1': int(c.geom1), 'geom2': int(c.geom2),
                             'distance_m': float(c.dist), 'position_m': c.pos.tolist()}
                            for c in data.contact]
                row = {'frame_index': index, 'physics_time_s': float(data.time),
                       'evidence': 'SIM_PHYSICS', 'qpos': data.qpos.tolist(), 'qvel': data.qvel.tolist(),
                       'contacts_count': int(data.ncon), 'contacts': contacts,
                       'servo_target': data.ctrl.tolist(), 'command_emitted': emitted,
                       'hold_override_applied': hold_override_applied,
                       'camera': camera, 'injection': injection, 'bridge': gate}
                stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + '\n')
    finally:
        if renderer is not None:
            renderer.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-root', required=True, type=Path, help='Existing robotstudio_so101 directory; no download')
    parser.add_argument('--output-dir', required=True, type=Path, help='Must not already exist')
    parser.add_argument('--capture', choices=['required', 'disabled'], default='required',
                        help='disabled is a missing-sensor CPU diagnostic; STOP from frame zero')
    parser.add_argument('--seeds', nargs='+', type=int, default=[23, 31])
    parser.add_argument('--cases', nargs='+', choices=SCENARIOS, default=list(SCENARIOS))
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds) or len(set(args.cases)) != len(args.cases):
        parser.error('Duplicate seed or case')
    pin = validate_model(args.model_root)
    import mujoco
    import numpy as np
    import PIL
    if (mujoco.__version__, np.__version__, PIL.__version__) != ('4.0.1', '2.5.4', '13.0.0'):
        parser.error('Install pinned requirements.txt')
    model = mujoco.MjModel.from_xml_path(str(args.model_root / 'scene_box.xml'))
    if not (model.nu == 6 and model.nq == 13 and model.nv == 12 and model.opt.timestep == .005 and
            mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, 'wrist_cam') >= 0):
        parser.error('Unexpected physical model')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {'schema': 1, 'source': source_state(), 'started_at_utc': datetime.now(timezone.utc).isoformat(),
                'executor': platform.node(), 'platform': platform.platform(), 'python': platform.python_version(),
                'versions': {'mujoco': mujoco.__version__, 'numpy': np.__version__, 'pillow': PIL.__version__},
                'model_pin_sha256': pin, 'physics_hz': 200, 'command_hz': 30,
                'capture': {'camera': 'wrist_cam', 'width': 160, 'height': 120, 'every_frame': args.capture == 'required'},
                'capture_state': args.capture, 'frames': FRAMES, 'trace': 'trace.jsonl', 'seeds': args.seeds, 'scenarios': args.cases,
                'evidence': 'SIM_PHYSICS_WITH_SEPARATE_SYNTHETIC_FAULT_INJECTION',
                'sorting': False, 'calibrated_defect_source': False, 'physical_estop': False}
    write_json(args.output_dir / 'run.json', metadata)
    started = time.perf_counter()
    results = []
    for mode in args.cases:
        for seed in args.seeds:
            directory = args.output_dir / f'{mode}-{seed}'
            simulate(model, mode, seed, directory, args.capture == 'required')
            manifest = {**metadata, 'scenario': mode, 'seed': seed, 'trace_sha256': sha(directory / 'trace.jsonl')}
            write_json(directory / 'manifest.json', manifest)
            checked = verify_episode(directory, args.model_root)
            results.append({'scenario': mode, 'seed': seed, **checked,
                            'manifest_sha256': sha(directory / 'manifest.json')})
            print(json.dumps(results[-1]), flush=True)
    write_json(args.output_dir / 'summary.json', {'runs': results, 'wall_seconds': time.perf_counter()-started,
               'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'episodes': len(results),
               'frames': sum(r['frames'] for r in results), 'historical_results_rerun': False})
    print('SUMMARY_SHA256', sha(args.output_dir / 'summary.json'))


if __name__ == '__main__':
    main()
