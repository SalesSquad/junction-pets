import { createScanLane } from "./agent.mjs";
import { createSyntheticHost } from "./synthetic-host.mjs";

const fixture = createSyntheticHost();
const agent = createScanLane(fixture.host, { now: () => 100000 });
const results = [];
for (const mode of ["find", "inspect", "verify"])
  results.push(await agent.execute(fixture.context, fixture.request(mode)));
fixture.host.verifyIdentity = async ({ targetId, observationSha256 }) => ({
  targetId,
  observationSha256,
  status: "not-observed",
});
results.push(
  await agent.execute(
    fixture.context,
    fixture.request("verify", { requestId: "removed-pouch" }),
  ),
);
console.log(
  JSON.stringify(
    {
      product: "Chibi Lens — Find & Verify",
      execution: "synthetic-fixture-only",
      catalogObjects: 10002,
      trace: results,
      stats: fixture.stats,
      limits:
        "No real camera, spatial registration, model, persistent memory or production host was exercised.",
    },
    null,
    2,
  ),
);
