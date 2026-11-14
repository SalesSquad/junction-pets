// Pure domain logic; source text never becomes an instruction or executable code.
import {createHash} from 'node:crypto';
export const REPLAY = 'REPLAYED_OFFICIAL_FIXTURE';
export const sha256 = text => createHash('sha256').update(text).digest('hex');
export function publicURL(value) {
  const u = new URL(value);
  if (u.protocol !== 'https:' || u.username || u.password || u.port || !['hackjunction.app','slush.org','www.slush.org','exa.ai','discord.com'].includes(u.hostname)) throw new Error('Source URL is outside the public source allowlist');
  u.hash = '';
  return u.href;
}
export function inspectFixture(fixture, anchors, now = new Date()) {
  const seen = new Set();
  const sources = fixture.sources.map(s => {
    const url = publicURL(s.url), anchor = anchors[s.id];
    if (!anchor || anchor.url !== url || anchor.contentSHA256 !== sha256(s.text) || anchor.observedAt !== s.observedAt || anchor.snapshotSHA256 !== s.snapshotSHA256 || s.mode !== REPLAY) throw new Error('Unrecognized or altered source provenance');
    if (seen.has(url)) throw new Error('Duplicate source URL');
    seen.add(url);
    const age = now - new Date(s.observedAt);
    if (!Number.isFinite(age) || age < -86400000) throw new Error('Invalid observation date');
    return {...s, freshness: age > 7 * 86400000 ? 'STALE' : 'DATED_REPLAY', publicationState:s.publishedAt ? 'REPORTED' : 'UNKNOWN'};
  });
  for (const claim of fixture.claims) {
    const source = sources.find(s => s.id === claim.sourceId);
    if (!source || !claim.excerpt || !source.text.includes(claim.excerpt)) throw new Error('Unsupported factual claim');
  }
  return {...fixture, sources, mode:REPLAY, checkedAt:now.toISOString(), sponsorAPI:'NOT VERIFIED', discrepancies:[...fixture.discrepancies,...sources.filter(s=>s.freshness==='STALE').map(s=>({kind:'STALE',sourceIds:[s.id],detail:'Observation is over seven days old. Recheck before relying on it.'}))]};
}
export function makePacket(goal, fixture, anchors, now) {
  if (typeof goal !== 'string' || !goal.trim() || goal.length > 500) throw new Error('Enter a goal of 1–500 characters');
  if (goal.trim() !== fixture.goal) return {state:'CONNECTION_NEEDED',mode:REPLAY,sponsorAPI:'NOT VERIFIED',message:'This goal is outside the dated Exa fixture. No result was searched or invented. Use the named replay or explicitly request a live Exa lookup.'};
  return {...inspectFixture(fixture, anchors, now),state:'EVIDENCE_READY',goal:goal.trim(),actions:[
    {id:'terms',kind:'suggestion',sourceIds:['M298'],text:'Open the official brief and verify the submission deadline, eligibility and current offer terms.',done:false},
    {id:'proof',kind:'suggestion',sourceIds:['M298'],text:'Prepare a demo with a source ledger and one unseen judge query; show a connection-needed state until real Exa retrieval works.',done:false},
    {id:'clarify',kind:'suggestion',sourceIds:['M298','workshop'],text:'Use the draft below to ask the sponsor about unresolved terms. Sending remains your separate decision.',done:false}
  ],draft:'Subject: Clarifying the Exa Junction opportunity\n\nI am preparing an Internet Butler demo for Junction. The dated M298 brief asks for a useful task, clear sources and live judge queries.\n\nCould you confirm the current submission deadline, eligibility and participant credit terms? The narrative prize fields contain placeholders while a later section lists amounts; which terms apply?\n\nMy next step is to prepare a source-grounded demo. I have not redeemed credits or submitted an application.\n\n[Add your own project summary, if useful.]'};
}
