/** Operator-private host configuration. No account registration or secret provisioning. */
import { lstatSync, readFileSync, realpathSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { createBuyerIdentity } from './buyer-identity.mjs';

export function readPrivateIdentityConfig(path) {
  path = resolve(path);
  const stat = lstatSync(path);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1 || stat.size > 65536 ||
      (stat.mode & 0o077) || (process.getuid && stat.uid !== process.getuid()) || realpathSync(path) !== path) {
    throw Error('Host identity configuration must be an owner-held 0600 regular file without symlinks.');
  }
  try { return JSON.parse(readFileSync(path, 'utf8')); }
  catch { throw Error('Host identity configuration is unreadable or invalid.'); }
}
const verifierSettings = config => Object.fromEntries(['issuer','accessAudience','decisionAudience','jwks',
  'accessTyp','decisionTyp','algorithms','maxAccessAgeSeconds','maxDecisionAgeSeconds'].filter(key => config[key] !== undefined).map(key => [key,config[key]]));
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');

export async function loadBuyerIdentity(path) {
  const config = readPrivateIdentityConfig(path);
  if (!config || typeof config !== 'object' || Array.isArray(config)) throw Error('Invalid identity configuration.');
  const initial = digest([config.profileId, verifierSettings(config)]);
  const { createJwtHostVerifier } = await import('../identity/jwt-host.mjs');
  const verifier = await createJwtHostVerifier(verifierSettings(config));
  return createBuyerIdentity({ profileId: config.profileId, issuer: config.issuer, verifier,
    grants: () => {
      const fresh = readPrivateIdentityConfig(path);
      if (digest([fresh.profileId, verifierSettings(fresh)]) !== initial) throw Error('Identity verifier settings changed; restart this executor explicitly.');
      return fresh.grants;
    } });
}
