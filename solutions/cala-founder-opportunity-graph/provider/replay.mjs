// Every company, claim, source and proof in this module is FICTIONAL.
import { MODE, sha } from './provider.mjs';
export const INVESTOR = '11111111-1111-4111-8111-111111111111';
export const ISSUER = '22222222-2222-4222-8222-222222222222';
export const CASES = ['lead','issuer','missing','duplicates','wrong-id','stale','forged-source','timeout','overlarge','ambiguous-identity','ambiguous-fields','contradiction','filing-only','private-source','revoked'];
export const request = () => ({ query: 'Fictional Nordic climate seed leads', approvedEntityId: INVESTOR, goal: { sector: 'Climate software', geography: 'Nordics', stage: 'Seed', from: '2025-11-15', to: '2026-11-15' }, clock: { now: '2026-11-15T09:00:00.000Z', asOf: '2026-11-15' }, identity: { actorRef: 'synthetic-actor', tenantRef: 'synthetic-tenant', approvalRef: 'fictional-exact-uuid-approval' } });
const meanings = ['investorId','issuerId','economicRoundId','kind','role','lead','eventDate','stage','sector','geography','source'];
export function fakeHost(scenario = 'lead') {
  if (!CASES.includes(scenario)) throw Error('Unknown replay case');
  const calls = [];
  const source = { id: 'fictional-release-1', originId: 'fictional-issuer-newsroom', url: 'https://example.invalid/fictional/issuer-announcement', publishedAt: '2026-08-12', credibility: 'primary' };
  const row = { investorId: INVESTOR, issuerId: ISSUER, economicRoundId: 'fictional-moss-seed-2026', kind: 'FUNDING_ROUND', role: 'INVESTOR', lead: true, eventDate: '2026-08-12', stage: 'Seed', sector: 'Climate software', geography: 'Nordics', source };
  if (scenario === 'issuer') row.role = 'ISSUER';
  if (scenario === 'missing') delete row.lead;
  if (scenario === 'wrong-id') row.investorId = ISSUER;
  if (scenario === 'stale') row.eventDate = '2022-01-01';
  if (scenario === 'filing-only') row.kind = 'FILING';
  const rows = [row];
  if (scenario === 'duplicates') rows.push(structuredClone(row), { ...row, kind: 'FILING', lead: null });
  if (scenario === 'contradiction') rows.push({ ...row, lead: false });
  // Deliberately arbitrary keys: the adapter must inspect introspection, never assume wire names.
  const fields = meanings.map((semantic,i) => ({ semantic, key: `observed_${i}` }));
  return {
    mode: MODE, calls,
    tools: ['entity_search','entity_introspection','entity_retrieval'].map(name => ({ name, capability: 'read', readOnly: true })),
    authorize: async ({ name }) => !(scenario === 'revoked' && name === 'entity_retrieval'),
    async callTool({ name, signal, maxResponseBytes }) {
      calls.push(name);
      if (scenario === 'timeout') return new Promise((_, reject) => signal.addEventListener('abort', () => reject(Error('aborted')), { once: true }));
      if (scenario === 'overlarge') return ' '.repeat(maxResponseBytes + 1);
      if (name === 'entity_search') return JSON.stringify({ entities: [{ id: INVESTOR, identity: scenario === 'ambiguous-identity' ? 'ambiguous' : 'resolved', public: true }] });
      if (name === 'entity_introspection') return JSON.stringify({ entityId: INVESTOR, fields: scenario === 'ambiguous-fields' ? [...fields, fields[0]] : fields });
      if (name === 'entity_retrieval') return JSON.stringify({ entityId: INVESTOR, rows: rows.map(r => Object.fromEntries(fields.filter(f => Object.hasOwn(r,f.semantic)).map(f => [f.key,r[f.semantic]]))) });
      throw Error('Disallowed fake tool');
    },
    async verifySource({ claim, claimDigest, clock }) {
      if (scenario === 'forged-source') return { claimDigest: sha('unrelated assertion') };
      return { claimDigest, url: source.url, originId: source.originId, issuerId: claim.issuerId, primary: true, public: scenario !== 'private-source', verifiedAt: clock.now };
    }
  };
}
