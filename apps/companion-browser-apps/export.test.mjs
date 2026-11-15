import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {exportApps} from './export.mjs';

test('export maps each selected pet to a real entry and its browser assets', async () => {
  const temp = await mkdtemp(join(tmpdir(), 'junction-app-export-'));
  const output = join(temp, 'bundle');
  try {
    const apps = await exportApps(output);
    const catalog = JSON.parse(await readFile(join(output, 'catalog.json'), 'utf8'));
    assert.deepEqual(catalog.apps, apps);
    assert.deepEqual(new Set(apps.map(app => app.petSlug)), new Set(['junction-arduino','junction-intel','junction-city-of-espoo','junction-rokoko','junction-bahn-express']));
    for (const app of apps) assert.match(await readFile(join(output, app.path), 'utf8'), /<html/i);
    assert.match(await readFile(join(output,'apps/spread-director/index.html'), 'utf8'), /Use synthetic example/);
    const example = JSON.parse(await readFile(join(output,'apps/spread-director/demo.json'), 'utf8'));
    assert.equal(example.mode, 'SYNTHETIC_OFFLINE');
    assert.match(await readFile(join(output,'apps/proofmatch/app.mjs'), 'utf8'), /cached in this browser/);
    await assert.rejects(exportApps(output), {code:'EEXIST'});
  } finally { await rm(temp, {recursive:true,force:true}); }
});
