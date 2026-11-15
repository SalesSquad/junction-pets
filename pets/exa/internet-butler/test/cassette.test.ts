import assert from "node:assert/strict";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { Cassette } from "../src/eval/cassette.ts";
import type { DecisionProvider } from "../src/decide/decide.ts";

test("cassette: record once, replay identically, fail loudly on a replay miss", async () => {
  const dir = await mkdtemp(join(tmpdir(), "cassette-"));
  const path = join(dir, "run.jsonl");
  let live = 0;
  const search = async (q: string) => { live++; return [{ url: `https://x.example/${q}`, highlights: [String(Math.random())] }]; };
  let p = 0.3;
  const judge: DecisionProvider = { id: "j", decide: async (_s, qs) => ({ provider: "j", model: "m", answers: qs.map((q) => ({ name: q.name, kind: q.kind, p: (p += 0.1) })), usage: { inputTokens: 1, cachedTokens: 0 }, ms: 1 }) };

  const rec = new Cassette(path, "auto");
  const a1 = await rec.search(search)("eu261", "o");
  const d1 = await rec.decisions(judge).decide({ x: 1 }, [{ kind: "yesno", name: "q", instructions: "?" }]);
  assert.equal(live, 1);
  assert.equal(rec.misses, 2);

  const rep = new Cassette(path, "replay");
  assert.deepEqual(await rep.search(search)("eu261", "o"), a1); // same "random" highlights
  assert.deepEqual(await rep.decisions(judge).decide({ x: 1 }, [{ kind: "yesno", name: "q", instructions: "?" }]), d1); // a drifting judge replays exactly
  assert.equal(live, 1);
  assert.equal(rep.hits, 2);
  await assert.rejects(rep.search(search)("other", "o"), /cassette miss/);
  assert.equal(rep.digest(), rec.digest());
});
