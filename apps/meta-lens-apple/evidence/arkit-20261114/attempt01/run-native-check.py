import datetime, hashlib, json, os, pathlib, shutil, signal, subprocess, sys, time
ROOT=pathlib.Path('/Users/mikaelervamaa/Developer/junction-meta-arkit-screen-context-20261114')
PKG=ROOT/'apps/meta-lens-apple'
PROOF=pathlib.Path('/Users/mikaelervamaa/Developer/lens-arkit-screen-context-proof-20261114')
SHA='4d3dc8665b79b4ac99c290f3c6d9b734f0dca42a'
COMMAND_ID='lens-arkit-native-20261114-01'
ENV=dict(os.environ, DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
EXPECTED={
'Sources/ChibiLensARKit/PhoneSpatialCapture.swift':'5187717fd6a68d9ec70347b4ee5f04453cbf840b11a189109ab209437ca5caaa',
'Sources/ChibiLensARKit/PhoneSpatialObservation.swift':'95ecb5225851aab186483e41dfab10e6bb43971a62ca4784fa160676dcec3dd6',
'Tests/ChibiLensARKitTests/PhoneSpatialObservationTests.swift':'3ea93eb308c00d0e9b2e3a7a87fc40c5ee75043f38cbb49fb61d35bff531b4d3',
'Package.swift':'a0b5078864a55e0b2d8437569b77c9432a85eae56c6a71d3f7d5284b1938e103'}
report={'schemaVersion':1,'commandId':COMMAND_ID,'sourceHead':SHA,'startedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cameraStarted':False,'simulatorStarted':False,'physicalDeviceUsed':False,'phases':[],'result':'RUNNING'}
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def out(args): return subprocess.check_output(args,cwd=ROOT,env=ENV,text=True,timeout=20).strip()
def save():
 (PROOF/'execution.json').write_text(json.dumps(report,indent=2)+'\n')
def run(name,args,timeout):
 log=PROOF/(name+'.txt')
 start=time.monotonic()
 stopped=None
 with log.open('w') as stream:
  p=subprocess.Popen(args,cwd=PKG,env=ENV,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
  while p.poll() is None:
   if shutil.disk_usage('/System/Volumes/Data').free<20*2**30: stopped='disk_guard_20GiB'
   if time.monotonic()-start>timeout: stopped='timeout'
   if log.stat().st_size>8_000_000: stopped='log_guard'
   if stopped:
    os.killpg(p.pid,signal.SIGTERM)
    try: p.wait(timeout=8)
    except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGKILL); p.wait()
    break
   time.sleep(0.5)
  code=p.wait()
 entry={'name':name,'argv':args,'cwd':str(PKG),'timeoutSeconds':timeout,'elapsedSeconds':round(time.monotonic()-start,3),'exitCode':code,'stoppedReason':stopped,'rawLog':str(log),'rawLogSha256':digest(log)}
 report['phases'].append(entry);save();print(json.dumps(entry),flush=True)
 if code or stopped: raise RuntimeError(name+' failed')
try:
 report['dirtyBefore']=out(['git','status','--porcelain'])
 assert out(['git','rev-parse','HEAD'])==SHA and not report['dirtyBefore'],'source pin/clean check failed'
 report['sourceFilesSha256']={p:digest(PKG/p) for p in EXPECTED}
 assert report['sourceFilesSha256']==EXPECTED,'source bytes changed'
 report['runnerSha256']=digest(pathlib.Path(__file__))
 report['initialFreeGiB']=round(shutil.disk_usage('/System/Volumes/Data').free/2**30,3)
 assert report['initialFreeGiB']>=20,'native admission disk guard'
 processes=out(['ps','-axo','pid,ppid,comm']).splitlines()
 busy=[line for line in processes if any(x in line.lower() for x in ['xcodebuild','swift-frontend','xctest','swift-driver'])]
 assert not busy,'another native lane active'
 report['xcode']=out(['/usr/bin/xcodebuild','-version'])
 swiftc=out(['/usr/bin/xcrun','--find','swiftc'])
 swift=out(['/usr/bin/xcrun','--find','swift'])
 sdk=out(['/usr/bin/xcrun','--sdk','iphoneos','--show-sdk-path'])
 report['swift']=out([swiftc,'--version'])
 report['sdk']=sdk
 report['environment']={'DEVELOPER_DIR':ENV['DEVELOPER_DIR'],'target':'arm64-apple-ios17.0','nativeJobs':1}
 modules=PROOF/'iOSModules';modules.mkdir(exist_ok=True)
 common=[swiftc,'-swift-version','6','-parse-as-library','-emit-module','-target','arm64-apple-ios17.0','-sdk',sdk,'-module-cache-path',str(PROOF/'ModuleCache')]
 core=sorted(str(p) for p in (PKG/'Sources/ChibiLensCore').glob('*.swift'))
 run('ios-core-module',common+['-module-name','ChibiLensCore','-emit-module-path',str(modules/'ChibiLensCore.swiftmodule')]+core,180)
 arkit=sorted(str(p) for p in (PKG/'Sources/ChibiLensARKit').glob('*.swift'))
 run('ios-arkit-module',common+['-I',str(modules),'-module-name','ChibiLensARKit','-emit-module-path',str(modules/'ChibiLensARKit.swiftmodule')]+arkit,180)
 run('macos-observation-tests',[swift,'test','--package-path',str(PKG),'--scratch-path',str(PROOF/'SwiftPM'),'--jobs','1','--filter','PhoneSpatialObservationTests'],300)
 report['artifactSha256']={str(p.relative_to(PROOF)):digest(p) for p in sorted(modules.glob('*')) if p.is_file()}
 report['result']='PASS'
except Exception as exc:
 report['result']='FAIL'
 report['error']=str(exc)
finally:
 report['headAfter']=out(['git','rev-parse','HEAD'])
 report['dirtyAfter']=out(['git','status','--porcelain'])
 if report['headAfter']!=SHA or report['dirtyAfter']: report['result']='FAIL';report['error']='source changed during check'
 report['completedAt']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 report['finalFreeGiB']=round(shutil.disk_usage('/System/Volumes/Data').free/2**30,3)
 save()
 print(json.dumps({'result':report['result'],'sourceHead':SHA,'evidence':str(PROOF/'execution.json'),'sha256':digest(PROOF/'execution.json')}),flush=True)
sys.exit(0 if report['result']=='PASS' else 1)
