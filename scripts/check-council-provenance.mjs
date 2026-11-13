import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const MANIFEST = 'services/council/upstream-provenance.json';
const README = 'services/council/README.md';
const LICENSE = 'services/council/LICENSE-UPSTREAM';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

export async function verifyCouncilProvenance(root = ROOT) {
  const manifest = JSON.parse(await readFile(resolve(root, MANIFEST), 'utf8'));
  const readme = await readFile(resolve(root, README), 'utf8');
  const license = await readFile(resolve(root, LICENSE));
  const errors = [];

  if (manifest.schemaVersion !== 1 || manifest.adaptation !== 'independent') {
    errors.push('manifest must identify schema v1 and an independent adaptation');
  }

  const sources = [manifest.prototype, manifest.foundation];
  for (const source of sources) {
    if (!/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(source?.repository ?? '')) {
      errors.push('source repository must be a canonical GitHub URL');
    }
    if (!/^[a-f0-9]{40}$/.test(source?.commit ?? '')) {
      errors.push('source commit must be a full lowercase Git SHA');
    }
    if (!readme.includes(source?.repository ?? '') || !readme.includes(source?.commit ?? '')) {
      errors.push(`README is missing the pinned source ref for ${source?.repository ?? 'unknown source'}`);
    }
  }

  if (!Array.isArray(manifest.prototype?.files) || manifest.prototype.files.length === 0) {
    errors.push('prototype must list its source files and blob SHAs');
  } else {
    for (const file of manifest.prototype.files) {
      if (!/^[a-f0-9]{40}$/.test(file?.blobSha ?? '')) {
        errors.push(`invalid blob SHA for ${file?.path ?? 'unknown file'}`);
      }
      if (!readme.includes(file?.path ?? '') || !readme.includes(file?.blobSha ?? '')) {
        errors.push(`README is missing the pinned blob ref for ${file?.path ?? 'unknown file'}`);
      }
    }
  }

  const licenseSha256 = createHash('sha256').update(license).digest('hex');
  if (manifest.license?.localPath !== LICENSE || manifest.license?.upstreamPath !== 'LICENSE') {
    errors.push('license paths must match the reviewed source and local notice');
  }
  if (!/^[a-f0-9]{64}$/.test(manifest.license?.sha256 ?? '')
      || manifest.license?.spdx !== 'MIT' || licenseSha256 !== manifest.license?.sha256) {
    errors.push('local upstream license does not match its pinned MIT SHA-256');
  }
  if (!readme.includes('independently adapted for Junction')
      || !readme.includes('neither an Aiven endorsement')
      || !readme.includes('MIT attribution is retained')) {
    errors.push('README must preserve adaptation, attribution and non-endorsement statements');
  }

  assert(errors.length === 0, `Council provenance check failed:\n- ${errors.join('\n- ')}`);
  return {
    status: 'pass',
    scope: 'local-record-consistency-only',
    adaptation: manifest.adaptation,
    prototypeCommit: manifest.prototype.commit,
    foundationCommit: manifest.foundation.commit,
    prototypeFiles: manifest.prototype.files.length,
    licenseSha256
  };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    console.log(JSON.stringify(await verifyCouncilProvenance(), null, 2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
