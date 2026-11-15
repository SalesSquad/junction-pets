// The page reads web/data/app.json. It must be what `npm run build` would write now, apart from builtAt.
// buildApp() only returns the object (the file is written by the CLI block of src/build.mjs), so this test writes nothing.
// If it fails, run `npm run build` and commit web/data/app.json.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildApp } from '../src/build.mjs';

test('web/data/app.json equals a fresh buildApp() except builtAt', () => {
  const committed = JSON.parse(readFileSync(new URL('../web/data/app.json', import.meta.url), 'utf8'));
  const fresh = JSON.parse(JSON.stringify(buildApp()));
  assert.equal(typeof fresh.builtAt, 'string');
  delete committed.builtAt; delete fresh.builtAt;
  const keys = [...new Set([...Object.keys(committed), ...Object.keys(fresh)])];
  const drift = keys.filter((k) => JSON.stringify(committed[k]) !== JSON.stringify(fresh[k]));
  assert.deepEqual(drift, [], `web/data/app.json is stale in: ${drift.join(', ')}. Run npm run build.`);
  assert.deepEqual(fresh, committed);
});
