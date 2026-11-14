import {constants} from 'node:fs';
import {lstat, open, opendir} from 'node:fs/promises';
import {resolve, parse, join, isAbsolute} from 'node:path';
import {pathToFileURL} from 'node:url';
import {canonicalJson, sha256} from '../../lib/artifact.mjs';
import {recordRun, validateRun, validatePolicy} from './registry.mjs';

const MAX_JSON = 256 * 1024;
const MAX_RECEIPT = 4 * 1024 * 1024;
const reject = () => {throw new Error('inbox validation failed');};
const same = (a, b) => a.dev === b.dev && a.ino === b.ino && a.mode === b.mode && a.size === b.size && a.mtimeNs === b.mtimeNs && a.ctimeNs === b.ctimeNs;

// Snapshot every component, including the approved root and its ancestors.
async function chain(path, directory = false) {
  const absolute = resolve(path);
  let current = parse(absolute).root;
  const parts = absolute.slice(current.length).split('/').filter(Boolean);
  const entries = [];
  for (let i = -1; i < parts.length; i++) {
    if (i >= 0) current = join(current, parts[i]);
    const stat = await lstat(current, {bigint: true});
    if (stat.isSymbolicLink() || ((i < parts.length - 1 || directory) ? !stat.isDirectory() : !stat.isFile())) reject();
    entries.push([current, stat]);
  }
  return entries;
}
async function unchanged(entries) {
  for (const [path, stat] of entries) if (!same(stat, await lstat(path, {bigint: true}))) reject();
}
async function bounded(path, limit) {
  const before = await chain(path);
  const handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const start = await handle.stat({bigint: true});
    if (!start.isFile() || start.size > BigInt(limit) || !same(start, before.at(-1)[1])) reject();
    const buffer = Buffer.alloc(limit + 1);
    let length = 0;
    while (length < buffer.length) {
      const {bytesRead} = await handle.read(buffer, length, buffer.length - length, null);
      if (!bytesRead) break;
      length += bytesRead;
    }
    if (length > limit || !same(start, await handle.stat({bigint: true}))) reject();
    await unchanged(before);
    return {bytes: buffer.subarray(0, length), before};
  } finally {await handle.close();}
}
function json(bytes) {return JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));}
function exact(value, fields) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join() !== [...fields].sort().join()) reject();
}
async function existing(path) {
  try {return json((await bounded(path, MAX_JSON)).bytes);}
  catch (error) {if (error.code === 'ENOENT') return undefined; throw error;}
}
async function prerequisites(root, run) {
  if (run.kind === 'model-evaluation') {
    const policy = validatePolicy(await existing(join(root, 'policies', `policy.${run.policySha256}.json`)));
    if (sha256(canonicalJson(policy)) !== run.policySha256 || policy.taskId !== run.taskId || Date.parse(policy.frozenAt) > Date.parse(run.capturedAt)) reject();
  }
  if (run.planId) {
    const plan = await existing(join(root, 'plans', `${run.planId}.json`));
    if (!plan || plan.taskId !== run.taskId || plan.status !== 'planned-not-dispatched' || Date.parse(run.capturedAt) < Date.parse(plan.createdAt)) reject();
  }
}

export async function importInbox({inbox, receiptsRoot, root, dryRun = false, limit = 100} = {}) {
  const result = {created: 0, existing: 0, failed: 0, validated: 0, items: [], exitCode: 0, providerAttestationVerified: false};
  try {
    if (!inbox || !receiptsRoot || !root || !Number.isSafeInteger(limit) || limit < 1 || limit > 1000) reject();
    const inboxChain = await chain(inbox, true);
    const privateDir = inboxChain.at(-1)[1];
    if ((privateDir.mode & 0o077n) !== 0n || (process.getuid && privateDir.uid !== BigInt(process.getuid()))) reject();
    const receiptChain = await chain(receiptsRoot, true);
    await chain(root, true);
    // Bounded directory enumeration; refuse oversized inboxes rather than selecting an arbitrary subset.
    const names = [];
    const dir = await opendir(inbox);
    for await (const entry of dir) {
      names.push(entry.name);
      if (names.length > 10000) reject();
    }
    await unchanged(inboxChain);
    const candidates = names.filter(x => x.endsWith('.json')).sort();
    if (candidates.length > limit) reject(); // Refuse silent starvation of later envelopes.
    for (const name of candidates) {
      const item = {index: result.items.length + 1, status: 'failed'};
      try {
        const envelopeFile = await bounded(join(inbox, name), MAX_JSON);
        const envelope = json(envelopeFile.bytes);
        exact(envelope, ['schemaVersion', 'run', 'receipt']);
        if (envelope.schemaVersion !== 1) reject();
        exact(envelope.receipt, ['path', 'sha256', 'runId']);
        const run = validateRun(envelope.run);
        const receipt = envelope.receipt;
        if (receipt.runId !== run.runId || typeof receipt.path !== 'string' || !receipt.path || isAbsolute(receipt.path) || receipt.path.includes('\\') || receipt.path.split('/').some(p => !p || p === '.' || p === '..')) reject();
        if (!/^[a-f0-9]{64}$/.test(receipt.sha256) || run.evidence.receiptSha256 !== receipt.sha256) reject();
        await unchanged(receiptChain);
        const file = await bounded(join(resolve(receiptsRoot), receipt.path), MAX_RECEIPT);
        if (sha256(file.bytes) !== receipt.sha256) reject();
        // Receipts are JSON statements, not arbitrary media. Identity must agree in all three places.
        if (json(file.bytes)?.runId !== run.runId) reject();
        await prerequisites(root, run);
        const previous = await existing(join(root, 'runs', `${run.runId}.json`));
        if (previous !== undefined && canonicalJson(previous) !== canonicalJson(run)) reject();
        await unchanged(envelopeFile.before);
        await unchanged(file.before);
        await unchanged(receiptChain);
        if (dryRun) {item.status = 'validated'; result.validated++;}
        else {
          const saved = await recordRun(root, run);
          item.status = saved.created ? 'created' : 'existing';
          result[item.status]++;
        }
        item.admission = run.kind === 'model-evaluation' ? 'not-compared' : 'evidence-only';
        if (item.admission === 'not-compared') result.exitCode = 2;
      } catch {result.failed++;}
      result.items.push(item);
    }
  } catch {result.failed++; result.error = 'inbox unavailable or invalid authority/options';}
  if (result.failed) result.exitCode = 1;
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const args = process.argv.slice(2);
    const options = {};
    const flags = {'--inbox': 'inbox', '--receipts-root': 'receiptsRoot', '--root': 'root', '--limit': 'limit'};
    while (args.length) {
      const flag = args.shift();
      if (flag === '--dry-run' && options.dryRun === undefined) options.dryRun = true;
      else if (flags[flag] && options[flags[flag]] === undefined && args.length && !args[0].startsWith('--')) options[flags[flag]] = args.shift();
      else reject();
    }
    if (options.limit !== undefined) options.limit = Number(options.limit);
    const result = await importInbox(options);
    console.log(JSON.stringify(result));
    process.exitCode = result.exitCode;
  } catch {console.log(JSON.stringify({failed: 1, exitCode: 1, error: 'invalid inbox options'})); process.exitCode = 1;}
}
