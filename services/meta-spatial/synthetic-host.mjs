// Test/demo adapter only. Production memory, identity, idempotency and provider
// execution belong to the Chibi host; this file does not implement that host.
import { digest, procedureDigest, copy, ScanError } from "./contracts.mjs";
export function createSyntheticHost({
  catalogSize = 10000,
  now = () => 100000,
} = {}) {
  const context = {
    tenantId: "synthetic-tenant",
    actorId: "synthetic-parent",
    sourceCommit: "61f10a44cfd833e02fa64462dfc7429046fff210",
  };
  const observation = {
    schemaVersion: 1,
    id: "scan-shelf",
    tenantId: context.tenantId,
    sessionId: "session-1",
    generation: 1,
    receivedAtMs: now(),
    source: { kind: "fixture", deviceId: "synthetic-camera" },
    frame: { sha256: "a".repeat(64), width: 720, height: 1280 },
    entities: [{ id: "pouch", label: "Blue keys pouch", confidence: 0.94 }],
    registration: { state: "unregistered" },
  };
  const procedure = {
    id: "pouch-check",
    revision: "1",
    documentSha256: "b".repeat(64),
    entityId: "pouch",
    instruction:
      "Check the pouch tag before confirming this is your keys pouch.",
    sourceUrl: "https://example.org/synthetic/pouch-check",
  };
  procedure.sha256 = procedureDigest(procedure);
  const sightings = Array.from({ length: catalogSize }, (_, i) => ({
    id: `sighting-${i}`,
    targetId: `object-${i}`,
    label: `Synthetic object ${i}`,
    zone: "Storage",
    observedAtMs: 1,
    observationRef: `old-${i}`,
    observationSha256: "c".repeat(64),
  }));
  sightings.unshift(
    {
      id: "keys-shelf",
      targetId: "my-keys",
      label: "Keys pouch",
      zone: "Shelf",
      observedAtMs: 90000,
      observationRef: "saved-shelf",
      observationSha256: "d".repeat(64),
    },
    {
      id: "keys-desk",
      targetId: "my-keys",
      label: "Keys pouch",
      zone: "Desk",
      observedAtMs: 80000,
      observationRef: "saved-desk",
      observationSha256: "e".repeat(64),
    },
  );
  const jobs = new Map();
  const stats = { modelCalls: 0, lookupCalls: 0, largestModelInput: 0 };
  const host = {
    async authorize(x) {
      return x.tenantId === context.tenantId && x.actorId === context.actorId;
    },
    async runJob(key, work) {
      const id = JSON.stringify([key.tenantId, key.actorId, key.requestId]);
      const existing = jobs.get(id);
      if (existing) {
        if (existing.digest !== key.inputSha256)
          throw new ScanError("IDEMPOTENCY_CONFLICT");
        return copy(await existing.result);
      }
      const result = Promise.resolve().then(work);
      jobs.set(id, { digest: key.inputSha256, result });
      return copy(await result);
    },
    async resolveObservation() {
      return copy(observation);
    },
    async validateCapture({ observation }) {
      return (
        observation.generation === 1 && observation.source.kind === "fixture"
      );
    },
    async validateRegistration() {
      return false;
    },
    async searchSightings({ query, cursor, limit }) {
      stats.lookupCalls++;
      const offset = cursor === null ? 0 : Number(cursor);
      const all =
        query === "all"
          ? sightings
          : sightings.filter((x) => x.targetId === "my-keys");
      return {
        items: copy(all.slice(offset, offset + limit)),
        nextCursor: offset + limit < all.length ? String(offset + limit) : null,
      };
    },
    async searchProcedures() {
      stats.lookupCalls++;
      return { items: [copy(procedure)], nextCursor: null };
    },
    async propose(input) {
      stats.modelCalls++;
      stats.largestModelInput = Math.max(
        stats.largestModelInput,
        Buffer.byteLength(JSON.stringify(input)),
      );
      return {
        entityId: "pouch",
        procedureId: procedure.id,
        procedureSha256: procedure.sha256,
      };
    },
    async verifyIdentity({ targetId, observationSha256 }) {
      return {
        targetId,
        observationSha256,
        status: "verified",
        evidenceRef: "synthetic-tag-proof",
      };
    },
  };
  function request(mode = "inspect", extra = {}) {
    return {
      schemaVersion: 1,
      requestId: `request-${mode}`,
      sessionId: observation.sessionId,
      mode,
      query: mode === "find" ? "keys" : "check pouch",
      ...(mode === "find"
        ? {}
        : {
            observationRef: observation.id,
            observationSha256: digest(observation),
          }),
      ...(mode === "verify" ? { targetId: "my-keys" } : {}),
      ...extra,
    };
  }
  return { host, context, observation, procedure, stats, request };
}
