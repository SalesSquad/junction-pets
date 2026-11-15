import {validate, clean} from './detector.mjs';

// A new observable-coordination contract, not a retuning of radar-v1's intent audit.
export const POLICY_V2 = Object.freeze({
  version: 'coordination-v2', threshold: 80, minAccounts: 4,
  windowSeconds: 60, textOverlap: 0.72, maxEvents: 400, maxBytes: 524288
});
const normalize = value => clean(value).toLowerCase().replace(/https?:\/\/\S+/gu, '')
  .replace(/[^\p{L}\p{N}\s]/gu, ' ').replace(/\s+/gu, ' ').trim();
const tokens = value => new Set(normalize(value).split(' ').filter(Boolean));
function overlap(a, b) {
  if (a.size < 4 || b.size < 4) return 0;
  let common = 0;
  for (const word of a) if (b.has(word)) common++;
  return common / (a.size + b.size - common);
}
function resourceKey(value) {
  try {
    const raw = String(value ?? '');
    if (raw.length > 2048) return ''; // Never equate resources by a truncated identifier.
    const u = new URL(clean(raw, 2048));
    if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password) return '';
    // Only established tracking fields are ignored. Unknown query fields can identify content.
    const pairs = [...u.searchParams].filter(([name]) =>
      !/^utm_/i.test(name) && !['fbclid', 'gclid', 'msclkid'].includes(name.toLowerCase()));
    // Preserve unknown parameter order, including repeated semantic keys.
    const query = new URLSearchParams(pairs).toString();
    return u.origin.toLowerCase() + u.pathname + (query ? '?' + query : '');
  } catch { return ''; }
}
function redactURLQueries(value, limit = 600) {
  return clean(value, limit).replace(/https?:\/\/[^\s]+/gu, raw => {
    try { const u = new URL(raw); return u.protocol + '//' + u.host + u.pathname; }
    catch { return '[unparseable URL]'; }
  });
}
const ordered = es => [...es].sort((a, b) => a.ms - b.ms || a.id.localeCompare(b.id));

export function analyzeCoordination(input, {omit = []} = {}) {
  const events = validate(input);
  const excluded = new Set(omit);
  const rawById = new Map(input.map(e => [clean(e.id, 60), e]));
  // Resource keys are invocation-local and never returned or persisted.
  const keys = events.map(e => resourceKey(rawById.get(e.id)?.url));
  const words = events.map(e => tokens(e.text));
  const neighbors = events.map(() => new Set());
  const edges = new Map();
  for (let i = 0; i < events.length; i++) {
    for (let j = i + 1; j < events.length; j++) {
      if (events[j].ms - events[i].ms > POLICY_V2.windowSeconds * 1000) break;
      if (events[i].account === events[j].account || excluded.has('timing') || excluded.has('text')) continue;
      const similarity = overlap(words[i], words[j]);
      if (similarity < POLICY_V2.textOverlap) continue;
      const destination = !excluded.has('url') && keys[i] && keys[i] === keys[j];
      const amplification = !excluded.has('amplification') && events[i].amplifies &&
        events[i].amplifies === events[j].amplifies;
      if (!destination && !amplification) continue;
      neighbors[i].add(j); neighbors[j].add(i);
      edges.set(i + ':' + j, {
        a: events[i].id, b: events[j].id,
        types: ['timing', 'text', ...(destination ? ['url'] : []), ...(amplification ? ['amplification'] : [])],
        similarity: Math.round(similarity * 100)
      });
    }
  }

  // Deterministic greedy complete-link cohorts: all pairs must have strong support.
  // This deliberately favors precision over recall; it is not maximal-clique enumeration.
  const unused = new Set(events.map((_, i) => i));
  const priority = (a, b) => neighbors[b].size - neighbors[a].size || events[a].id.localeCompare(events[b].id);
  const cohorts = [];
  for (const seed of [...unused].sort(priority)) {
    if (!unused.has(seed)) continue;
    const members = [seed];
    for (const candidate of [...neighbors[seed]].filter(i => unused.has(i)).sort(priority)) {
      if (members.every(i => events[i].account !== events[candidate].account && neighbors[i].has(candidate))) {
        members.push(candidate);
      }
    }
    if (members.length < POLICY_V2.minAccounts) continue;
    for (const i of members) unused.delete(i);
    cohorts.push(members.sort((a, b) => events[a].ms - events[b].ms || events[a].id.localeCompare(events[b].id)));
  }

  // Repeated complete-link rounds with the exact same participating accounts are shown together.
  const groups = [];
  for (const cohort of cohorts.sort((a, b) => events[a[0]].ms - events[b[0]].ms || events[a[0]].id.localeCompare(events[b[0]].id))) {
    const signature = JSON.stringify(cohort.map(i => events[i].account).sort());
    const prior = groups.find(g => g.signature === signature &&
      events[cohort[0]].ms - events[g.rounds[0][0]].ms <= 86400000);
    if (prior) prior.rounds.push(cohort);
    else groups.push({signature, rounds: [cohort], indices: []});
  }
  for (const group of groups) group.indices = group.rounds.flat();

  // Unqualified observations stay in exact-payload context groups, never transitive components.
  const context = new Map();
  for (const i of unused) {
    const text = normalize(events[i].text);
    const key = text && words[i].size >= 4 ? JSON.stringify([text, keys[i], events[i].amplifies]) : 'event:' + events[i].id;
    if (!context.has(key)) context.set(key, []);
    context.get(key).push(i);
  }
  for (const indices of context.values()) groups.push({rounds: [], indices});

  const findings = groups.map(group => {
    const indices = [...group.indices].sort((a, b) => events[a].ms - events[b].ms || events[a].id.localeCompare(events[b].id));
    const es = indices.map(i => {
      const e = events[i];
      return {...e, text: redactURLQueries(e.text), attribution: redactURLQueries(e.attribution, 100),
        amplifies: redactURLQueries(e.amplifies, 60)};
    });
    const qualified = group.rounds.length > 0;
    const ids = es.map(e => e.id);
    const pairEvidence = [];
    for (const round of group.rounds) for (let a = 0; a < round.length; a++) {
      for (let b = a + 1; b < round.length; b++) {
        const x = Math.min(round[a], round[b]), y = Math.max(round[a], round[b]);
        pairEvidence.push(edges.get(x + ':' + y));
      }
    }
    const spec = [
      ['timing', 'Complete-link synchronized rounds', qualified ? 35 : 0,
        qualified ? group.rounds.length + ' round(s), every participating pair within 60 seconds.' : 'No complete-link four-account synchronized round.'],
      ['text', 'Pairwise near-copy text', qualified ? 35 : 0,
        qualified ? 'Every within-round pair has at least 72% token overlap with four or more tokens.' : 'Text repetition alone cannot trigger a coordination finding.'],
      ['joint', 'Independent shared trace', qualified ? 20 : 0,
        qualified ? 'Every pair also shares a content-aware destination or amplification target.' : 'Shared destinations alone do not merge unrelated observations.'],
      ['persistence', 'Repeated participating cohort', group.rounds.length > 1 && !excluded.has('persistence') ? 10 : 0,
        group.rounds.length > 1 ? group.rounds.length + ' qualifying rounds share the exact participating account set within 24 hours.' : 'No repeated qualifying cohort observed.']
    ];
    const signals = spec.map(([key, label, points, detail]) => ({
      key, label, points, originalPoints: points, detail, eventIds: points ? ids : []
    }));
    const score = signals.reduce((sum, signal) => sum + signal.points, 0);
    const review = qualified && score >= POLICY_V2.threshold;
    const peakRound = group.rounds.reduce((best, round) => round.length > best.length ? round : best, []);
    return {
      id: es[0].id, score, review,
      status: review ? 'Possible coordination — intent unknown' : 'Insufficient pairwise coordination evidence',
      intent: 'UNKNOWN', evidenceClass: qualified ? 'OBSERVABLE_COMPLETE_LINK_COACTION' : 'CONTEXT_ONLY',
      events: es, accountCount: new Set(es.map(e => e.account)).size,
      peak: peakRound.map(i => events[i].id), signals, links: pairEvidence.slice(0, 100),
      roundCount: group.rounds.length, pairCount: pairEvidence.length,
      start: es[0].time, end: es.at(-1).time,
      uncertainty: [
        'Observed coordination does not establish deception, automation, shared control or malicious intent.',
        'Legitimate volunteers, syndication and planned launches can produce the same observations.',
        'Account names, ages and declared attribution are unverified context and never decide this finding.',
        'Greedy complete-link grouping can miss partial, text-only, delayed or overlapping coordination.',
        'Unknown query parameters distinguish resources internally; URL query strings are omitted from returned evidence.'
      ]
    };
  }).sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
  return {
    mode: 'OFFLINE_DETERMINISTIC / INPUT_PROVENANCE_UNVERIFIED',
    policy: POLICY_V2, eventCount: events.length, findings,
    limits: 'Observable-coordination review aid only. Rule points are not probabilities. Intent always UNKNOWN; no enforcement or field-accuracy claim.'
  };
}
