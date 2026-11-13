import assert from "node:assert/strict";
import { validateRequest } from "../../../services/meta-spatial/contracts.mjs";

let body = "";
for await (const chunk of process.stdin) {
  body += chunk;
  if (body.length > 16_384) throw new Error("SWIFT_CONTRACT_OUTPUT_TOO_LARGE");
}
const requests = JSON.parse(body);
assert.ok(Array.isArray(requests));
assert.deepEqual(requests.map((request) => request.mode), ["find", "inspect", "verify"]);

for (const request of requests) {
  assert.deepEqual(validateRequest(request), request);
  assert.equal(request.schemaVersion, 1);
}
assert.ok(!("observationRef" in requests[0]));
assert.ok(!("observationSha256" in requests[0]));
assert.ok(!("targetId" in requests[1]));
assert.equal(requests[2].targetId, "charger-a");

for (const mutate of [
  (x) => { x[0].requestId = " bad"; },
  (x) => { x[0].query = "x".repeat(401); },
  (x) => { x[1].observationSha256 = "A".repeat(64); },
  (x) => { x[2].targetId = ""; },
  (x) => { x[0].query = "charger\uFEFF"; },
]) {
  const bad = structuredClone(requests);
  mutate(bad);
  const invalid = bad.find((x, i) => JSON.stringify(x) !== JSON.stringify(requests[i]));
  assert.throws(() => validateRequest(invalid));
}
assert.equal(validateRequest({ ...requests[0], query: "charger\u0085" }).query,
  "charger\u0085");

process.stdout.write("Swift→Meta JS contract parity: 3 valid, 5 invalid + Unicode boundary passed\n");
