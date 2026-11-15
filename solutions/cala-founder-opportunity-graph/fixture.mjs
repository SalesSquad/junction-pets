// All identities, assertions and URLs below are invented. Never provider data.
export const MODE = 'FICTIONAL_FIXTURE';
export const AS_OF = '2026-11-14';
const entity = (id, name, extra = {}) => ({ id, name, url: `https://example.invalid/entities/${id}`, sector: 'Climate software', geography: 'Nordics', identity: 'resolved', ...extra });
export const entities = [
  entity('inv-larch', 'Larch Seed Partners'), entity('inv-tide', 'Tide Foundry'),
  entity('inv-echo', 'Echo Ventures', { identity: 'ambiguous', collisionIds: ['inv-echo-uk'] }),
  entity('inv-echo-uk', 'Echo Ventures', { geography: 'UK', identity: 'ambiguous', collisionIds: ['inv-echo'] }),
  entity('inv-archive', 'Archive Capital'), entity('inv-blank', 'Blank Slate Fund'),
  entity('inv-loop', 'Loop Signal Ventures'), entity('co-moss', 'Moss Grid', { kind: 'company' }),
  entity('co-kite', 'Kite Heat', { kind: 'company' }), entity('co-reed', 'Reed Systems', { kind: 'company' })
];
const ev = (id, investorId, roundId, date, extra = {}) => ({
  id, investorId, roundId, issuerId: 'co-moss', role: 'INVESTOR', lead: true,
  stage: 'Seed', sector: 'Climate software', geography: 'Nordics', eventDate: date,
  kind: 'FUNDING_ROUND', amount: null, currency: 'EUR',
  source: { id: `src-${id}`, url: `https://example.invalid/sources/${id}`, title: `Fictional announcement ${id}`, publishedAt: date, credibility: 'primary', originId: `origin-${id}`, excerpt: 'Fictional issuer announcement explicitly names this investor as lead.' }, ...extra
});
export const events = [
  ev('moss-round', 'inv-larch', 'round-moss-seed-2026', '2026-08-12'),
  ev('moss-filing', 'inv-larch', 'round-moss-seed-2026', '2026-08-12', { kind: 'FILING', lead: null }),
  ev('kite-round', 'inv-tide', 'round-kite-seed-2026', '2026-06-05', { issuerId: 'co-kite', amount: 2200000 }),
  ev('echo-round', 'inv-echo', 'round-reed-seed-2026', '2026-09-02', { issuerId: 'co-reed' }),
  ev('old-round', 'inv-archive', 'round-moss-seed-2022', '2022-04-01'),
  ev('unknown-lead', 'inv-blank', 'round-reed-seed-2026', '2026-07-19', { lead: null }),
  ev('issuer-entry', 'co-moss', 'round-moss-seed-2026', '2026-08-12', { role: 'ISSUER' }),
  ev('loop-blog', 'inv-loop', 'round-kite-seed-2026', '2026-06-05', { source: { id: 'src-loop', url: 'https://example.invalid/sources/loop', title: 'Fictional circular aggregator', publishedAt: '2026-06-06', credibility: 'secondary', originId: 'origin-loop', excerpt: 'Aggregator repeats another aggregator; no primary lead evidence.' } }),
  ev('tide-contradiction', 'inv-tide', 'round-reed-seed-2026', '2026-10-01', { issuerId: 'co-reed', lead: false }),
  ev('tide-claim', 'inv-tide', 'round-reed-seed-2026', '2026-10-01', { issuerId: 'co-reed' })
];
export const fixture = { mode: MODE, asOf: AS_OF, entities, events };
