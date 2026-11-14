import { readFile,realpath,lstat,writeFile } from 'node:fs/promises';
import { resolve,dirname,basename } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { inspectVisionImage } from '../nemotron-vl/index.mjs';
import { validateObservation,reject } from './observation-contract.mjs';

const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
async function boundedFile(path,maxBytes) {
  const info=await lstat(path);
  if(!info.isFile() || info.isSymbolicLink() || info.size>maxBytes)reject('invalid-artifact-file');
  const bytes=await readFile(path);
  if(bytes.length>maxBytes)reject('artifact-too-large');
  return bytes;
}

/** Convert a published worker artifact into the exact browser/API bundle. No network or relabelling. */
export async function bundleObservation({workerOutput,framePath,trackId=null}) {
  const root=await realpath(workerOutput);
  const observationBytes=await boundedFile(resolve(root,'observation.json'),1024*1024);
  const observation=validateObservation(JSON.parse(observationBytes));
  const manifestBytes=await boundedFile(resolve(root,'artifacts.json'),256*1024);
  const manifest=JSON.parse(manifestBytes);
  if(manifest.schemaVersion!==1 || manifest.runId!==observation.runId || manifest.frameSha256!==observation.frame.sha256 ||
    !Array.isArray(manifest.artifacts) || manifest.artifacts.length>16)reject('artifact-manifest-mismatch');
  if(observation.evidenceMode==='MODEL') {
    const receipt=JSON.parse(await boundedFile(resolve(root,'receipt.json'),1024*1024));
    if(receipt.status!=='MODEL_COMPLETED' || receipt.runId!==observation.runId || receipt.evidenceMode!=='MODEL' ||
      receipt.observationSha256!==sha(observationBytes) || receipt.artifactManifestSha256!==sha(manifestBytes) ||
      Object.entries(observation.model).some(([key,value])=>receipt.model?.[key]!==value))reject('incomplete-worker-receipt');
    // This verifies supplied artifact consistency, not a cryptographic worker attestation.
  }
  let imagePath,expected,kind;
  if(trackId===null) {
    if(!framePath)reject('source-frame-required');
    imagePath=resolve(framePath);expected=observation.frame;kind='frame';
  } else {
    const track=observation.tracks.find(t=>t.trackId===trackId);
    const matches=manifest.artifacts.filter(a=>a.kind==='crop' && a.trackId===trackId);
    if(!track || matches.length!==1)reject('crop-not-found');
    const artifact=matches[0];
    if(typeof artifact.path!=='string' || artifact.path!==basename(artifact.path) || !/^[A-Za-z0-9._-]+\.png$/.test(artifact.path) ||
      artifact.sha256!==track.crop.sha256)reject('invalid-crop-artifact');
    imagePath=resolve(root,artifact.path);
    if(dirname(await realpath(imagePath))!==root)reject('artifact-path-escape');
    expected=track.crop;kind='crop';
  }
  const bytes=await boundedFile(imagePath,1048576);
  const mime=bytes[0]===137?'image/png':'image/jpeg';
  const image={kind,dataUrl:'data:'+mime+';base64,'+bytes.toString('base64'),sha256:sha(bytes),trackId};
  const metadata=inspectVisionImage(image.dataUrl);
  if(metadata.sha256!==expected.sha256 || metadata.width!==expected.width || metadata.height!==expected.height ||
    kind==='crop' && metadata.mimeType!==expected.mimeType)reject('artifact-image-mismatch');
  return {observation,image};
}

if(process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const args=process.argv.slice(2),options={};
    for(let i=0;i<args.length;i+=2) {
      if(!['--worker-output','--frame','--track','--output'].includes(args[i]) || !args[i+1])reject('invalid-bundle-arguments');
      options[args[i]]=args[i+1];
    }
    if(!options['--worker-output'] || !options['--output'])reject('worker-output-and-output-required');
    const bundle=await bundleObservation({workerOutput:options['--worker-output'],framePath:options['--frame'],trackId:options['--track']??null});
    await writeFile(options['--output'],JSON.stringify(bundle,null,2)+'\n',{flag:'wx',mode:0o600});
    console.log(JSON.stringify({status:'bundle-written',evidenceMode:bundle.observation.evidenceMode,
      frameSha256:bundle.observation.frame.sha256,physicalIdentityVerified:false}));
  } catch(error) {console.error(JSON.stringify({status:'rejected',code:error.code??'bundle-failed'}));process.exitCode=2;}
}
