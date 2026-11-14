/**
 * Read-only CRACI API evidence adapter. No dispatch, CI flag, auth or spend mutation.
 * Official API: https://docs.craci.com/api/reference/ (v1preview1).
 * Network/SBOM are provider API observations, not signed attestations or an invoice.
 */
import {sha256} from './adaptive-core.mjs';

const ROOT = 'https://api.craci.com/v1preview1/';
const COMMIT = /^[a-f0-9]{40}$/;
const DECIMAL = /^[0-9]{1,20}$/;
const REPOSITORY = 'SalesSquad/junction-pets';

function valid(condition, code) {if (!condition) throw new Error(code);}
function checkedIdentity(query) {
  valid(query && query.repository === REPOSITORY && DECIMAL.test(query.jobId || '') &&
    DECIMAL.test(query.runId || '') && COMMIT.test(query.expectedHarnessSha || ''), 'INVALID_PROOF_SELECTOR');
  valid(query.runAttempt === undefined || (Number.isInteger(query.runAttempt) && query.runAttempt >= 1), 'INVALID_RUN_ATTEMPT');
  return {repository: REPOSITORY, jobId: query.jobId, runId: query.runId,
    harnessSha: query.expectedHarnessSha, runAttempt: query.runAttempt ?? null};
}

async function apiJson(path, params, token, fetchImpl, timeoutMs, bytesLimit) {
  const url = new URL(path, ROOT);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), timeoutMs);
  try {
    const response = await fetchImpl(url.toString(), {method:'GET',redirect:'error',signal:abort.signal,
      headers:{Authorization:`Bearer ${token}`,Accept:'application/json'}});
    if (response.status !== 200) return {status:'unavailable', code:`HTTP_${response.status}`};
    const type = response.headers.get('content-type') || '';
    if (!/(?:application\/json|application\/vnd\.cyclonedx\+json)/i.test(type))
      return {status:'unavailable',code:'UNEXPECTED_CONTENT_TYPE'};
    const reader = response.body?.getReader();
    if (!reader) return {status:'unavailable',code:'NO_RESPONSE_BODY'};
    let count=0;const chunks=[];
    while (true) {
      const {done,value} = await reader.read();if (done) break;
      count += value.byteLength;
      if (count > bytesLimit) {await reader.cancel();return {status:'unavailable',code:'RESPONSE_TOO_LARGE'};}
      chunks.push(value);
    }
    const raw = Buffer.concat(chunks.map(value => Buffer.from(value)));
    let data;
    try {data = JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(raw));}
    catch {return {status:'unavailable',code:'INVALID_JSON'};}
    return {status:'ok',data,bodySha256:sha256(raw),responseBytes:raw.byteLength};
  } catch {return {status:'unavailable',code:'NETWORK_OR_TIMEOUT'};}
  finally {clearTimeout(timer);}
}

function evaluateNetwork(raw, q) {
  if (raw.status !== 'ok') return {status:'unknown',reason:raw.code};
  const {job,observations} = raw.data || {};
  if (!job || typeof job !== 'object' || job.provider !== 'github' ||
    job.repository !== q.repository || job.jobId !== q.jobId || job.runId !== q.runId ||
    job.commitSha !== q.harnessSha ||
    (q.runAttempt !== null && job.runAttempt !== q.runAttempt) ||
    !Array.isArray(observations) || observations.length > 10000)
    return {status:'unknown',reason:'PROVIDER_JOB_BINDING_MISMATCH'};
  const protocols = Object.create(null);let denied=0;
  for (const observed of observations) {
    if (!observed || typeof observed !== 'object' ||
      !['http','dns','tcp','ssh'].includes(observed.protocol))
      return {status:'unknown',reason:'UNKNOWN_OBSERVATION_SHAPE'};
    protocols[observed.protocol]=(protocols[observed.protocol]||0)+1;
    if (observed.http?.policyDenied === true || observed.tcp?.policyDenied === true ||
        observed.dns?.policyDenied === true || observed.ssh?.policyDenied === true) denied++;
  }
  return {status:'provider_api_observed',runId:q.runId,jobId:q.jobId,
    harnessSha:job.commitSha,jobStatus:String(job.status).slice(0,40),
    observations:observations.length,denied,protocolCounts:{...protocols},
    responseSha256:raw.bodySha256};
}

function evaluateSbom(raw) {
  if (raw.status !== 'ok') return {status:'unknown',reason:raw.code};
  const doc = raw.data;
  if (!doc || doc.bomFormat !== 'CycloneDX' || !/^1\.[0-9]+$/.test(doc.specVersion || '') ||
    !Array.isArray(doc.components)) return {status:'unknown',reason:'INVALID_CYCLONEDX_SHAPE'};
  // An inventory can be incomplete; this never declares complete SBOM coverage.
  return {status:'provider_api_observed',format:'CycloneDX',version:doc.specVersion,
    components:doc.components.length,responseSha256:raw.bodySha256,coverage:'unverified'};
}

function evaluateUsage(raw, period) {
  if (raw.status !== 'ok') return {status:'unknown',reason:raw.code};
  const doc=raw.data;
  const count=doc?.total?.vcpuSeconds;
  if (!doc || doc.start !== period.start || doc.end !== period.end ||
    !/^[0-9]+$/.test(String(count)) || typeof count === 'object')
    return {status:'unknown',reason:'INVALID_AGGREGATE_USAGE_SHAPE'};
  return {status:'provider_api_observed',periodStart:doc.start,periodEnd:doc.end,
    aggregatedVcpuSeconds:String(count),responseSha256:raw.bodySha256,
    billedEur:null,scope:'organization_total_completed_jobs_delayed_not_job_cost'};
}

/** Token supplied by operator's already-authorized host environment; never returned/logged. */
export async function fetchCraciEvidence(query, {token,fetchImpl=fetch,timeoutMs=7000,usagePeriod} = {}) {
  const q = checkedIdentity(query);
  valid(Number.isInteger(timeoutMs) && timeoutMs >= 1000 && timeoutMs <= 20000,'INVALID_TIMEOUT');
  const base={schema:'craci-provider-proof-v1',repository:q.repository,runId:q.runId,jobId:q.jobId,
    expectedHarnessSha:q.harnessSha,providerAttestationVerified:false,
    perJobBilledEur:null,source:'craci_read_only_api',
    network:{status:'unknown',reason:'NO_AUTHENTICATED_CRACI_API'},
    sbom:{status:'unknown',reason:'NO_AUTHENTICATED_CRACI_API'},
    usage:{status:'unknown',reason:'NOT_REQUESTED'}};
  if (!token || typeof token !== 'string' || token.length < 8)
    return {...base,reason:'CRACI_API_TOKEN_NOT_CONFIGURED'};
  const params={provider:'github',repo:q.repository,job_id:q.jobId};
  const [network,sbom]=await Promise.all([
    apiJson('network-trace',params,token,fetchImpl,timeoutMs,8*1024*1024),
    apiJson('sbom',params,token,fetchImpl,timeoutMs,8*1024*1024),
  ]);
  let usage={status:'unknown',reason:'NOT_REQUESTED'};
  if (usagePeriod) {
    valid(usagePeriod && typeof usagePeriod.start === 'string' && typeof usagePeriod.end === 'string' &&
      Number.isFinite(Date.parse(usagePeriod.start)) && Number.isFinite(Date.parse(usagePeriod.end)) &&
      Date.parse(usagePeriod.end) > Date.parse(usagePeriod.start) &&
      Date.parse(usagePeriod.end)-Date.parse(usagePeriod.start) <= 48*3600_000,'INVALID_USAGE_PERIOD');
    const result = await apiJson('usage',{start:usagePeriod.start,end:usagePeriod.end},token,fetchImpl,timeoutMs,1024*1024);
    usage=evaluateUsage(result,usagePeriod);
  }
  const networkResult=evaluateNetwork(network,q),sbomResult=evaluateSbom(sbom);
  return {...base,reason:networkResult.status==='provider_api_observed' || sbomResult.status==='provider_api_observed' ?
    'PROVIDER_API_OBSERVATION_NOT_SIGNED_ATTESTATION_OR_EURO_BILL':'NO_VERIFIED_PROVIDER_OBSERVATION',
    network:networkResult,sbom:sbomResult,usage};
}
