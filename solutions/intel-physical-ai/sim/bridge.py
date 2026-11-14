"""Offline fail-closed replay. Hashes detect corruption, not authenticated provenance."""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REVISION = '370c43965323c0944b433b202aac5058b5f907a9'
SCENARIOS = ('nominal', 'grip_loss', 'camera_missing', 'camera_disagreement',
             'stale_capture', 'low_confidence', 'operator_global_stop',
             'threshold_ambiguous', 'operator_local_stop')
FRAMES = 180
FAULT_FRAME = 70


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    def reject_constant(value):
        raise ValueError('Nonfinite JSON: ' + value)
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError('Duplicate JSON key: ' + k)
            obj[k] = v
        return obj
    return json.loads(Path(path).read_text(), parse_constant=reject_constant,
                      object_pairs_hook=unique)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def safe_path(root, name):
    require(isinstance(name, str) and name and not Path(name).is_absolute(), 'Invalid path')
    require('..' not in Path(name).parts, 'Path traversal')
    target = (Path(root) / name).resolve()
    require(target.is_relative_to(Path(root).resolve()), 'Path escapes root')
    return target


def validate_model(root):
    pin = load(ROOT / 'model-pin.json')
    require(pin['revision'] == REVISION, 'Invalid revision')
    for name, digest in pin['files'].items():
        require(sha(safe_path(root, name)) == digest, 'Invalid model pin: ' + name)
    return sha(ROOT / 'model-pin.json')


def finite_numbers(value):
    if isinstance(value, dict):
        return all(finite_numbers(v) for v in value.values())
    if isinstance(value, list):
        return all(finite_numbers(v) for v in value)
    return not isinstance(value, float) or math.isfinite(value)


def verify_camera_bytes(path, digest, width, height):
    require(sha(path) == digest, 'Camera bytes hash mismatch')
    image = Path(path).read_bytes()
    header = f'P6\n{width} {height}\n255\n'.encode()
    require(image.startswith(header) and len(image) == len(header) + width * height * 3,
            'Invalid rendered frame')


class Bridge:
    """One episode, terminal software latch, no rearm API and no sorting adapter."""
    def __init__(self):
        self.latched = False

    def observe(self, observation, frame, physics_time, injection):
        try:
            return self._observe(observation, frame, physics_time, injection)
        except (ValueError, KeyError, TypeError):
            self.latched = True
            return {'state': 'GLOBAL_STOP_LATCHED', 'route': 'HOLD',
                    'sorting_allowed': False, 'reason': 'INVALID_OR_ABSENT_SENSOR',
                    'command_allowed': False}

    def _observe(self, observation, frame, physics_time, injection):
        require(observation['identity'] == f'wrist_cam:{frame}', 'Wrong observation identity')
        require(observation['frame_index'] == frame, 'Wrong camera frame')
        require(observation['present'] is True, 'Missing camera')
        captured = observation['captured_at_s']
        require(isinstance(captured, (int, float)) and math.isfinite(captured), 'Invalid capture time')
        require(0 <= physics_time - captured <= .1, 'Stale or future camera')
        require(observation['source'] == 'SIM_PHYSICS_RENDER', 'Wrong camera source')
        require(injection['source'] == 'SYNTHETIC_FAULT_INJECTION', 'Wrong injection source')
        fault = injection['fault']
        require(fault is None or fault in SCENARIOS[1:], 'Unknown injected fault')
        self.latched = self.latched or fault is not None
        # No defect label/region/score/calibration has been produced by a model.
        return {'state': 'GLOBAL_STOP_LATCHED' if self.latched else 'DEMO_ONLY',
                'route': 'HOLD', 'sorting_allowed': False,
                'reason': 'NO_REAL_CALIBRATED_DEFECT_SOURCE',
                'command_allowed': not self.latched}


def verify_episode(directory, model_root):
    directory = Path(directory)
    model_digest = validate_model(model_root)
    manifest = load(directory / 'manifest.json')
    require(manifest['schema'] == 1 and manifest['frames'] == FRAMES, 'Invalid episode contract')
    require(manifest['model_pin_sha256'] == model_digest, 'Invalid model manifest')
    require(manifest['scenario'] in SCENARIOS and type(manifest['seed']) is int, 'Invalid case')
    require(manifest['physics_hz'] == 200 and manifest['command_hz'] == 30, 'Invalid rates')
    capture = manifest['capture']
    require(capture['camera'] == 'wrist_cam' and
            all(type(capture[k]) is int and 0 < capture[k] <= 1024 for k in ('width', 'height')),
            'Invalid capture contract')
    require(manifest['capture_state'] in ('required', 'disabled') and
            capture['every_frame'] is (manifest['capture_state'] == 'required'), 'Invalid capture state')
    trace = safe_path(directory, manifest['trace'])
    raw = trace.read_bytes()
    require(raw.endswith(b'\n'), 'Truncated JSONL')
    require(sha(trace) == manifest['trace_sha256'], 'Trace hash mismatch')
    lines = raw.splitlines()
    require(len(lines) == FRAMES, 'Missing or extra frames')
    bridge = Bridge()
    sensor_valid = True
    previous_time = -1
    previous_command = None
    drift = 0.0
    held_qpos = None
    camera_paths = set()
    for index, line in enumerate(lines):
        # Use the same strict JSON decoder for rows, including duplicate keys.
        row = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')),
                         object_pairs_hook=_unique_row)
        require(finite_numbers(row), 'Nonfinite trace')
        require(row['frame_index'] == index and type(row['frame_index']) is int, 'Nonmonotonic frame')
        t = row['physics_time_s']
        require(t > previous_time and abs(t - (index + 1) / 30) <= .005001, 'Nonmonotonic/rate time')
        previous_time = t
        require(row['evidence'] == 'SIM_PHYSICS', 'Wrong physics evidence')
        require(len(row['qpos']) == 13 and len(row['qvel']) == 12 and len(row['servo_target']) == 6,
                'Missing physics state')
        for key in ('qpos', 'qvel', 'servo_target'):
            require(all(type(x) in (int, float) for x in row[key]), 'Invalid numerical state')
        require(type(row['contacts_count']) is int and row['contacts_count'] >= 0 and
                len(row['contacts']) == row['contacts_count'], 'Invalid contacts')
        for contact in row['contacts']:
            require(type(contact['geom1']) is int and type(contact['geom2']) is int and
                    len(contact['position_m']) == 3 and type(contact['distance_m']) in (int, float),
                    'Invalid contact state')
        camera = row['camera']
        require(type(camera['present']) is bool, 'Invalid camera presence')
        if camera['present'] is True:
            require(camera['path'] not in camera_paths, 'Reused camera path')
            camera_paths.add(camera['path'])
            path = safe_path(directory, camera['path'])
            verify_camera_bytes(path, camera['sha256'], capture['width'], capture['height'])
        else:
            require(camera.get('path') is None and camera.get('sha256') is None, 'Absent camera claims bytes')
        injection = row['injection']
        expected_fault = manifest['scenario'] if index >= FAULT_FRAME and manifest['scenario'] != 'nominal' else None
        require(injection['fault'] == expected_fault, 'Injection/case mismatch')
        gate = bridge.observe(camera, index, t, injection)
        sensor_valid = sensor_valid and gate['reason'] != 'INVALID_OR_ABSENT_SENSOR'
        require(row['bridge'] == gate, 'Bridge replay mismatch')
        require(row['command_emitted'] is gate['command_allowed'], 'Command after latch')
        if bridge.latched:
            require(previous_command is None or previous_command == row['servo_target'], 'Servo target changed after latch')
            if held_qpos is None:
                held_qpos = row['qpos'][:6]
            drift = max(drift, math.sqrt(sum((a-b)**2 for a,b in zip(row['qpos'][:6], held_qpos))))
        previous_command = row['servo_target']
    return {'integrity_valid': True, 'sensor_replay_accepted': sensor_valid, 'frames': len(lines), 'routing': 'REFUSED_HOLD',
            'global_stop_latched': bridge.latched, 'commands_after_latch': 0,
            'post_latch_drift_from_first_latched_frame_rad': drift}


def _unique_row(pairs):
    obj = {}
    for k, v in pairs:
        require(k not in obj, 'Duplicate JSON key')
        obj[k] = v
    return obj


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode-dir', required=True, type=Path)
    parser.add_argument('--model-root', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify_episode(args.episode_dir, args.model_root), indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'integrity_valid': False, 'routing': 'REFUSED_HOLD', 'error': str(exc)}))
        raise SystemExit(2)
