import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { capabilities } from "../agent/capabilities.ts";

const root = new URL("../", import.meta.url);
const read = (file) => readFile(new URL(file, root), "utf8");

test("Maker draft contains only portable, locally staged fields", async () => {
  const draft = JSON.parse(await read("maker-draft.json"));
  assert.deepEqual(Object.keys(draft).sort(), [
    "goal", "instructions", "introduction", "name", "scenarios",
  ]);
  for (const key of ["goal", "instructions", "introduction", "name"]) {
    assert.ok(typeof draft[key] === "string" && draft[key].trim());
  }
  assert.ok(Array.isArray(draft.scenarios) && draft.scenarios.length >= 2);
  assert.ok(draft.scenarios.every((scenario) => typeof scenario === "string" && scenario.trim()));
});

test("example capability graph is finite, acyclic and side-effect-free", () => {
  const ids = new Set(capabilities.map((capability) => capability.id));
  assert.equal(ids.size, capabilities.length);
  const seen = new Set();
  const visit = (id, stack = new Set()) => {
    assert.ok(ids.has(id), `unknown prerequisite: ${id}`);
    assert.ok(!stack.has(id), `cycle at ${id}`);
    if (seen.has(id)) return;
    const nextStack = new Set(stack).add(id);
    const capability = capabilities.find((item) => item.id === id);
    assert.equal(capability.effect, "proposal-only");
    for (const requirement of capability.prerequisites) visit(requirement, nextStack);
    seen.add(id);
  };
  for (const id of ids) visit(id);
});

test("Eve runtime disables its default powerful tools and sets a continuation threshold", async () => {
  const source = await read("agent/agent.ts");
  assert.match(source, /defaultTools:\s*false/);
  assert.match(source, /sessionUsage:/);
  assert.doesNotMatch(source, /process\.env|from\s+["']eve\/tools\/(?:bash|agent|web_fetch)/);
});

test("time-box tool needs no user goal and rejects undeclared input", async () => {
  const { default: tool } = await import("../agent/tools/propose_next_step.ts");
  const input = tool.inputSchema.parse({ minutes: 20 });
  assert.equal(tool.inputSchema.safeParse({ goal: "private goal", minutes: 20 }).success, false);
  const output = await tool.execute(input);
  assert.equal(output.status, "draft-not-saved");
  assert.equal(output.externalEffect, false);
  assert.equal(output.suggestedSteps.reduce((sum, step) => sum + step.minutes, 0), 20);
});

test("starter does not include live Chibi or provider credentials", async () => {
  const text = [
    await read("agent/instructions.md"),
    await read("maker-draft.json"),
  ].join("\n");
  assert.doesNotMatch(text, /(?:sk_(?:live|test)_|ghp_|AKIA[0-9A-Z]{16})/);
  assert.match(text, /no Chibi account/i);
});
