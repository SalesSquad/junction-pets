#!/usr/bin/env node
// Builds the proposed Chibi export for routed guidance:
//   chibi.companion.guidance-modules/v1  (dist/chibi/junction-aiven.guidance-modules.json)
// The host (not the model) selects modules from the user's message with the
// trigger patterns, composes core + selected modules as the system prompt, asks
// the provider for structured output with responseSchema, validates the response,
// and turns action_proposals into PendingActions for a human decision.
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { MODULES, selectModules } from './router.mjs';

const here = n => new URL(n, import.meta.url);
const sha = s => createHash('sha256').update(s).digest('hex');
const pet = JSON.parse(readFileSync(here('../pet.json'), 'utf8'));
const schemaText = readFileSync(here('../schemas/response.v2.json'), 'utf8');
const LIMIT = 20000;

export function buildManifest() {
  const text = n => readFileSync(here(`./${n}.md`), 'utf8');
  const modules = [{ id: 'core', alwaysLoad: true, trigger: null }, ...Object.entries(MODULES).map(([id, rx]) => ({ id, alwaysLoad: false, trigger: { pattern: rx.source, flags: rx.flags } }))]
    .map(m => { const t = text(m.id); return { ...m, chars: [...t].length, sha256: sha(t), text: t }; });
  const composedMax = modules.reduce((a, m) => a + m.chars + 2, 0);
  if (composedMax > LIMIT) throw new Error(`all modules together exceed ${LIMIT} characters`);
  const vectors = JSON.parse(readFileSync(here('./router-vectors.json'), 'utf8'));
  for (const v of vectors) if (JSON.stringify(selectModules(v.request)) !== JSON.stringify(v.expected)) throw new Error('router vector drift: ' + v.request.slice(0, 60));
  const body = { schema: 'chibi.companion.guidance-modules/v1', petId: pet.id, petVersion: pet.version, fallbackInstructions: 'AGENTS.md', composeOrder: 'core first, then selected modules in manifest order, joined by a blank line', defaultWhenNoTrigger: ['services'], maxComposedChars: composedMax, manifestLimitChars: LIMIT,
    responseSchema: { id: JSON.parse(schemaText).$id, sha256: sha(schemaText), json: JSON.parse(schemaText) }, modules, routerVectorsSha256: sha(JSON.stringify(vectors)) };
  return { ...body, sha256: sha(JSON.stringify(body)) };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const m = buildManifest();
  const out = new URL('../../../dist/chibi/junction-aiven.guidance-modules.json', import.meta.url);
  mkdirSync(new URL('./', out), { recursive: true });
  writeFileSync(out, JSON.stringify(m, null, 2) + '\n');
  console.log(JSON.stringify({ written: out.pathname, modules: m.modules.length, maxComposedChars: m.maxComposedChars, sha256: m.sha256 }));
}
