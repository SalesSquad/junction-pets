// Fictional supplied-result exercise only: no retrieval, provider or authority.
const reject = () => { throw new Error('invalid supplied results'); };
function keys(value, expected) {
  if (value === null || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).length !== expected.length ||
      expected.some(key => !Object.hasOwn(value,key))) reject();
}
function text(value, max) {
  if (typeof value !== 'string' || value.trim().length === 0 || value.length > max) reject();
}
function day(value) {
  if (typeof value !== 'string' || !/^(?!0000)\d{4}-\d{2}-\d{2}$/.test(value)) reject();
  const milliseconds=Date.parse(`${value}T00:00:00.000Z`);
  if (!Number.isFinite(milliseconds) || new Date(milliseconds).toISOString().slice(0,10) !== value) reject();
  return milliseconds;
}
function canonicalUrl(value) {
  text(value,2048);
  if (/[\u0000-\u0020\u007f]/.test(value)) reject();
  const url=new URL(value);
  if (url.protocol !== 'https:' || !url.hostname.endsWith('.example') || url.username || url.password) reject();
  url.hash='';
  return url.href;
}
function publication(date, asOf, maxAgeDays) {
  if (date === null) return {date:null, ageDays:null, state:'unknown'};
  const ageDays=(asOf-day(date))/86_400_000;
  return {date, ageDays, state:ageDays < 0 ? 'future' : ageDays <= maxAgeDays ? 'fresh' : 'stale'};
}

/** Accept a primitive JSON string, never executable caller objects. */
export function rankSuppliedResults(jsonText) {
  const boundary={
    mode:'fictional-supplied-results',
    searchExecuted:false, evidenceVerified:false, semanticRelevanceVerified:false, authorization:false,
    rankingBasis:'unique-case-insensitive-ASCII-token-coverage-in-supplied-excerpt',
    limitations:[
      'Supplied URLs, excerpts, publication dates and retrieval declarations are not authenticated.',
      'Literal vocabulary coverage is not semantic relevance, source authority, claim support or truth.',
      'Publication age is relative to the supplied as-of day; retrieval recency does not refresh publication.'
    ]
  };
  try {
    if (typeof jsonText !== 'string' || jsonText.length > 100_000) reject();
    // Native JSON.parse: duplicate object keys keep their final value. No reviver.
    const input=JSON.parse(jsonText);
    keys(input,['query','terms','asOf','maxAgeDays','results']);
    text(input.query,300);
    const asOf=day(input.asOf);
    if (!Number.isSafeInteger(input.maxAgeDays) || input.maxAgeDays < 0 || input.maxAgeDays > 3650) reject();
    if (!Array.isArray(input.terms) || input.terms.length < 1 || input.terms.length > 10 ||
        input.terms.some(term => typeof term !== 'string' || !/^[a-z0-9]{1,30}$/.test(term)) ||
        new Set(input.terms).size !== input.terms.length) reject();
    if (!Array.isArray(input.results) || input.results.length > 50) reject();
    const groups=new Map(), ids=new Set();
    for (const [inputIndex, result] of input.results.entries()) {
      keys(result,['id','url','title','excerpt','publishedOn','retrieval','retrievedOn']);
      if (typeof result.id !== 'string' || !/^[a-zA-Z0-9-]{1,40}$/.test(result.id) || ids.has(result.id)) reject();
      ids.add(result.id);
      const url=canonicalUrl(result.url);
      text(result.title,300);
      if (!['supplied','missing','unknown'].includes(result.retrieval)) reject();
      if (result.retrieval === 'supplied') {
        text(result.excerpt,2000);
        if (result.retrievedOn !== null && day(result.retrievedOn) > asOf) reject();
      } else if (result.excerpt !== null || result.retrievedOn !== null) reject();
      const dateEvidence=publication(result.publishedOn,asOf,input.maxAgeDays);
      if (groups.has(url)) {
        const retained=groups.get(url);
        retained.duplicates.push({...result});
        if (!retained.gaps.includes('duplicate-observations-unreconciled')) retained.gaps.push('duplicate-observations-unreconciled');
        continue;
      }
      const tokens=new Set(result.retrieval === 'supplied' ? result.excerpt.toLowerCase().match(/[a-z0-9]+/g) ?? [] : []);
      const matchedTerms=input.terms.filter(term => tokens.has(term));
      const gaps=[];
      if (result.retrieval !== 'supplied') gaps.push(`retrieval-${result.retrieval}`);
      else if (result.retrievedOn === null) gaps.push('retrieval-date-unknown');
      if (dateEvidence.state === 'unknown') gaps.push('publication-unknown');
      if (dateEvidence.state === 'future') gaps.push('future-publication');
      if (dateEvidence.state === 'stale') gaps.push('publication-older-than-window');
      groups.set(url,{
        ...result, canonicalUrl:url, inputIndex, matchedTerms,
        matchCount:result.retrieval === 'supplied' ? matchedTerms.length : null,
        publication:dateEvidence, gaps, duplicates:[]
      });
    }
    const ranked=[...groups.values()]
      .sort((a,b) => (b.matchCount ?? -1)-(a.matchCount ?? -1) || a.inputIndex-b.inputIndex)
      .map(({inputIndex,...result}, index) => ({rank:index+1,...result}));
    return {...boundary, status:'ranked', query:input.query, asOf:input.asOf,
      maxAgeDays:input.maxAgeDays, terms:[...input.terms], ranked,
      uniqueResultCount:ranked.length, duplicateCount:input.results.length-ranked.length, issues:[]};
  } catch {
    return {...boundary, status:'invalid', ranked:[], uniqueResultCount:null,
      duplicateCount:null, issues:['malformed-or-unsupported-input']};
  }
}
