import {validateEnvironment,REPOSITORY} from './registry.mjs';

const shaPattern=/^[a-f0-9]{40}$/;
const providerIdPattern=/^[A-Za-z0-9_.:-]{5,160}$/;
const CLOUD_PROVIDER_NAME='codex-cloud';

/**
 * A safe *plan* for the optional Mac Mini Codex CLI lane.
 * This never starts a task, creates an environment, rotates accounts or reads keys.
 * A provider UI/API check is still required after planning.
 */
export function planCloudDispatch(manifest,{petSlug,branch,sourceCommit,profile}){
  const company=petSlug?.startsWith('junction-')?petSlug.slice('junction-'.length):null;
  if(!company)throw new Error('Pet slug required');
  validateEnvironment(manifest,company);
  if(manifest.petSlug!==petSlug)throw new Error('Pet/environment mismatch');
  if(!shaPattern.test(sourceCommit??''))throw new Error('Exact source commit SHA required');
  if(typeof branch!=='string'||!new RegExp('^codex/junction-'+company+'-[a-z0-9-]+$').test(branch)) {
    throw new Error('Task branch must be isolated to this pet');
  }
  if(!['pro','plus'].includes(profile))throw new Error('Choose explicitly pro or plus; never rotate accounts automatically');
  if(!['ready','running'].includes(manifest.provisioning.state)) {
    throw new Error('Environment is not declared ready/running; provision and publish it with provider evidence first');
  }
  if(!providerIdPattern.test(manifest.provisioning.environmentId??''))throw new Error('Invalid provider environment ID');
  const task=[
    'Work ID: junction.'+company+'.cloud-task',
    'Repository: '+REPOSITORY,
    'Source SHA: '+sourceCommit,
    'Owned path: '+manifest.ownedPath,
    'Read root AGENTS.md, catalog-contract.md, ops/AGENTS.md and the selected pet instructions.',
    'Before writing, fetch and compare the exact source SHA and verify a clean baseline.',
    'Run npm ci --ignore-scripts, npm run validate, npm test and npm run build.',
    'Commit on the isolated task branch. Open a draft PR. Do not merge or deploy.',
    'Return source-bound checks, PR URL, blocker, owner and next action.',
    'Keep Chibi private code outside this repository and never move credentials.'
  ].join('\n');
  const executable=profile==='plus'?'codex-plus':'codex';
  return {
    schemaVersion:1,mode:'dry-run-only',provider:CLOUD_PROVIDER_NAME,
    profile,petSlug,sourceCommit,branch,
    environmentId:manifest.provisioning.environmentId,
    providerEvidenceUrl:manifest.provisioning.evidenceUrl,
    providerIndependentlyRechecked:false,
    executable:false,
    requires:['Live provider environment + publication recheck','Remote source HEAD recheck','User-authorized execution channel'],
    argv:[executable,'cloud','exec','--env',manifest.provisioning.environmentId,'--branch',branch,task],
    task
  };
}
