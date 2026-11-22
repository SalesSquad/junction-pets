import {fail, freeze, hashJson, jsonCopy} from './json.mjs';
/** Caller chooses meaningful stable keys; ordinal source IDs are not cross-revision identities. */
export async function compareRecords(before, after, {key, geometry = false, alignmentDeclared = false}) {
  if (typeof key !== 'function') fail('INVALID_COMPARISON', 'Provide a trusted stable-key function; no identity is inferred from ordinal IDs.');
  const a = before.manifest().source, b = after.manifest().source;
  if (a.adapter.id !== b.adapter.id) fail('INCOMPARABLE', 'Cross-format matching requires a separately qualified adapter.');
  if (geometry && (!alignmentDeclared || !a.frame || a.frame !== b.frame || !a.units?.toMetres || a.units.toMetres !== b.units?.toMetres)) fail('ALIGNMENT_REQUIRED', 'Geometry comparison requires declared matching frames and supported identical units.');
  const group = dataset => {
    const map = new Map();
    for (const record of dataset.entities()) {
      const id = key(record);
      if (id === null) continue;
      if (typeof id !== 'string' || !id || id.length > 200) fail('INVALID_KEY', 'Stable keys must be bounded strings or null.');
      if (!map.has(id)) map.set(id, []);
      map.get(id).push(record);
    }
    return map;
  };
  const left = group(before), right = group(after), rows = [];
  for (const key of [...new Set([...left.keys(), ...right.keys()])].sort()) {
    const old = left.get(key) ?? [], next = right.get(key) ?? [];
    const status = old.length > 1 || next.length > 1 ? 'ambiguous' : !old.length ? 'added_key' : !next.length ? 'removed_key' :
      await hashJson(old[0].data) === await hashJson(next[0].data) ? 'unchanged' : 'changed';
    rows.push({key, status, before: old.map(e => before.ref(e.id)), after: next.map(e => after.ref(e.id))});
  }
  const payload = {schema: 'evidence-kit.comparison/v1', before: before.manifest(), after: after.manifest(),
    alignment: {declared: alignmentDeclared, independentlyVerified: false}, rows, physicalChangeVerified: false};
  return freeze({...payload, sha256: await hashJson(payload)});
}
