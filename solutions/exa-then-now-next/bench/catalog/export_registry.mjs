#!/usr/bin/env node
// Writes the app's built-in registry of rights (src/timetravel/timetravel.ts: REGISTRY) as JSON for the catalog
// service, which embeds each entry's description so the built-in rights can be matched in any language.
// Usage: node --experimental-strip-types bench/catalog/export_registry.mjs
import { writeFileSync } from "node:fs";
import { REGISTRY } from "../../src/timetravel/timetravel.ts";
const out = new URL("./out/registry.json", import.meta.url);
writeFileSync(out, JSON.stringify(REGISTRY.map((k) => ({ title: k.title, about: k.about, jurisdiction: k.jurisdiction, ref: k.ref, also: k.also ?? [] })), null, 1));
console.log(`${REGISTRY.length} registry entries -> ${out.pathname}`);
