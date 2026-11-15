// Read-only availability signals; NEVER opens motors/cameras, never installs SDKs.
import {execFileSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {platform,arch} from 'node:os';
const exists=cmd=>{
  try{execFileSync('/usr/bin/env',['which',cmd],{stdio:'ignore',timeout:1200});return true;}
  catch{return false;}
};
const py=exists('python3');
const mods={};
if(py)for(const m of ['openvino','anomalib','lerobot']){
  try{
    const r=execFileSync('python3',['-c',
      'import importlib.util,sys;print(int(importlib.util.find_spec(sys.argv[1]) is not None))',m],
      {encoding:'utf8',timeout:1500,stdio:['ignore','pipe','ignore']});
    mods[m]=r.trim()==='1';
  }catch{mods[m]=false;}
}
const usb=(platform()==='darwin')?['/dev/tty.usbmodem','/dev/tty.usbserial']:
  ['/dev/ttyACM0','/dev/ttyUSB0'];
// We deliberately DO NOT scan or open device nodes: these are only useful
// generic prefixes; a port listing alone is not hardware identity proof.
console.log(JSON.stringify({
  evidence:'READ_ONLY_LOCAL_CAPABILITY_HINT_NOT_STATION_ATTESTATION',
  platform:platform(),arch:arch(),node:process.version,pythonFound:py,
  pythonModules:mods,benchmarkAppInPath:exists('benchmark_app'),
  lerobotCalibrateInPath:exists('lerobot-calibrate'),
  physicalSO101Qualified:false,physicalEstopQualified:false,
  realCameraQualified:false,anomalibModelQualified:false,vlaModelQualified:false,
  intelCPU_GPU_NPU_Qualification:false,
  action:'NO_HARDWARE_CONTROL',
  next:'Use an authorized station with actual device/camera IDs, safety wiring and independent tests'
},null,2));
