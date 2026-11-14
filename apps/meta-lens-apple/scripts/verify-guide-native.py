"""One admitted Mac lane: pinned source bytes, iOS modules, synthetic state checks.

Usage: python3 verify-guide-native.py SOURCE_BUNDLE_JSON NEW_OUTPUT_DIRECTORY
The bundle is made from the exact GitHub commit; its Git blob bindings must be
checked by the coordinator. This runner never signs, launches a simulator/camera,
requests credentials, installs dependencies, or alters existing source.
"""
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

bundle_path, output = Path(sys.argv[1]), Path(sys.argv[2])
output.mkdir(parents=True, exist_ok=False)
source = output / 'source'
source.mkdir()
env = dict(os.environ, DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
report = dict(sourceCommit=None, result='RUNNING', phases=[], cameraStarted=False,
              simulatorStarted=False, physicalDeviceUsed=False,
              startedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
sha = lambda data: hashlib.sha256(data).hexdigest()

def save():
    (output / 'execution.json').write_text(json.dumps(report, indent=2) + '\n')

def capture(argv):
    return subprocess.check_output(argv, env=env, text=True, timeout=20).strip()

def run(name, argv, limit=180):
    log = output / (name + '.txt')
    start, stop = time.monotonic(), None
    with log.open('w') as stream:
        process = subprocess.Popen(argv, cwd=source, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        while process.poll() is None:
            if shutil.disk_usage('/System/Volumes/Data').free < 20 * 2**30:
                stop = 'disk-reserve-20GiB'
            if time.monotonic() - start > limit:
                stop = 'timeout'
            if log.stat().st_size > 8_000_000:
                stop = 'log-limit'
            if stop:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                break
            time.sleep(0.5)
        code = process.wait()
    item = dict(name=name, argv=argv, exitCode=code, stoppedReason=stop,
                elapsedSeconds=round(time.monotonic()-start, 3),
                rawLog=log.name, rawLogSha256=sha(log.read_bytes()))
    report['phases'].append(item)
    save()
    print(json.dumps(item), flush=True)
    if code or stop:
        raise RuntimeError(name + ' failed')

try:
    bundle = json.loads(bundle_path.read_text())
    report['sourceCommit'] = bundle['sourceCommit']
    report['sourceFiles'] = {}
    for item in bundle['files']:
        path = Path(item['path'])
        assert not path.is_absolute() and '..' not in path.parts
        data = item['content'].encode()
        assert sha(data) == item['sha256']
        assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == item['gitBlob']
        target = source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        report['sourceFiles'][str(path)] = item['sha256']
    report['runnerSha256'] = sha(Path(__file__).read_bytes())
    report['initialFreeGiB'] = round(shutil.disk_usage('/System/Volumes/Data').free/2**30, 3)
    assert report['initialFreeGiB'] >= 20, 'insufficient native disk reserve'
    lib = ctypes.CDLL('/usr/lib/libproc.dylib')
    lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    lib.proc_pidpath.restype = ctypes.c_int
    candidates = []
    for line in capture(['ps', '-axo', 'pid,comm']).splitlines():
        if not any(name in line.lower() for name in ['xcodebuild', 'swift-frontend', 'xctest', 'swift-driver']):
            continue
        pid = int(line.split()[0])
        buffer = ctypes.create_string_buffer(4096)
        assert lib.proc_pidpath(pid, buffer, 4096) > 0, 'native process identity unavailable'
        name = Path(buffer.value.decode()).name
        candidates.append(dict(pid=pid, executable=name))
    report['nativeAdmissionCandidates'] = candidates
    assert not any(x['executable'] in ['xcodebuild', 'swift-frontend', 'xctest', 'swift-driver'] for x in candidates), 'another native lane active'
    report['xcode'] = capture(['/usr/bin/xcodebuild', '-version'])
    swiftc = capture(['/usr/bin/xcrun', '--find', 'swiftc'])
    sdk = capture(['/usr/bin/xcrun', '--sdk', 'iphoneos', '--show-sdk-path'])
    report['swift'] = capture([swiftc, '--version'])
    report['sdk'] = sdk
    modules = output / 'modules'
    modules.mkdir()
    common = [swiftc, '-swift-version', '6', '-parse-as-library', '-emit-module',
              '-target', 'arm64-apple-ios17.0', '-sdk', sdk,
              '-module-cache-path', str(output/'ModuleCache'), '-I', str(modules)]
    for module in ['ChibiLensCore', 'ChibiLensARKit', 'ChibiLensUI']:
        files = sorted(str(p) for p in (source/'Sources'/module).glob('*.swift'))
        run('ios-' + module, common + ['-module-name', module, '-emit-module-path', str(modules/(module+'.swiftmodule'))] + files)
    executable = output / 'guide-checks'
    run('compile-state-checks', [swiftc, '-swift-version', '6', '-parse-as-library',
        str(source/'Sources/ChibiLensCore/GuideSession.swift'), str(source/'scripts/verify-guide.swift'),
        '-module-cache-path', str(output/'HostModuleCache'), '-o', str(executable)])
    run('state-checks', [str(executable)], 20)
    assert all(sha((source/path).read_bytes()) == value for path, value in report['sourceFiles'].items()), 'source bytes changed'
    report['result'] = 'PASS'
except Exception as error:
    report['result'] = 'FAIL'
    report['error'] = str(error)
finally:
    report['completedAt'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report['finalFreeGiB'] = round(shutil.disk_usage('/System/Volumes/Data').free/2**30, 3)
    save()
    print(json.dumps(dict(result=report['result'], sourceCommit=report['sourceCommit'], evidence=str(output/'execution.json'))), flush=True)
sys.exit(0 if report['result'] == 'PASS' else 1)
