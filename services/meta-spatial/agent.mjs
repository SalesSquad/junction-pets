import {
  ScanError,
  fail,
  shape,
  text,
  integer,
  sha,
  digest,
  procedureDigest,
  copy,
  validateContext,
  validateRequest,
  validateObservation,
  validateSighting,
  LIMITS,
} from "./contracts.mjs";

const REQUIRED = [
  "runJob",
  "authorize",
  "resolveObservation",
  "validateCapture",
  "validateRegistration",
  "searchSightings",
  "searchProcedures",
  "propose",
  "verifyIdentity",
];

/** Portable execution kernel. Trusted host supplies identity, storage, durable
 * idempotency, real model calls and policy. No server or authority is created. */
export function createScanLane(
  host,
  { maxConcurrent = 4, maxQueued = 32, timeoutMs = 10000, now = Date.now } = {},
) {
  for (const k of REQUIRED)
    if (typeof host?.[k] !== "function")
      throw new TypeError(`host.${k} required`);
  integer(maxConcurrent, 1, 32);
  integer(maxQueued, 0, 1024);
  integer(timeoutMs, 1, 60000);
  if (typeof now !== "function") throw new TypeError("clock required");
  let active = 0;
  const queue = [];
  function drain() {
    while (active < maxConcurrent && queue.length) {
      const job = queue.shift();
      job.start();
    }
  }
  function schedule(work, signal, cleanup) {
    return new Promise((resolve, reject) => {
      let started = false;
      const abort = () => {
        if (started) return;
        const i = queue.indexOf(job);
        if (i >= 0) queue.splice(i, 1);
        signal.removeEventListener("abort", abort);
        reject(new ScanError("CANCELLED"));
      };
      const job = {
        start() {
          started = true;
          signal.removeEventListener("abort", abort);
          active++;
          Promise.resolve()
            .then(work)
            .then(resolve, reject)
            .finally(async () => {
              await cleanup();
              active--;
              drain();
            });
        },
      };
      if (signal.aborted) return reject(new ScanError("CANCELLED"));
      if (active < maxConcurrent) job.start();
      else if (queue.length < maxQueued) {
        queue.push(job);
        signal.addEventListener("abort", abort, { once: true });
      } else reject(new ScanError("BUSY"));
    });
  }
  async function execute(context, request, { signal: userSignal } = {}) {
    // Snapshot before the first await; a client cannot change admitted bytes.
    const ctx = validateContext(context),
      req = validateRequest(request);
    const signal = AbortSignal.any([
      ...(userSignal ? [userSignal] : []),
      AbortSignal.timeout(timeoutMs),
    ]);
    const requestDigest = digest({ context: ctx, request: req });
    const checkAbort = () => {
      if (signal.aborted) fail("CANCELLED");
    };
    const pending = new Set();
    let admittedObservation = null;
    function fresh(receivedAtMs, expiresAtMs = null) {
      const time = integer(now());
      integer(receivedAtMs);
      if (receivedAtMs > time || time - receivedAtMs > LIMITS.maxAgeMs)
        fail("STALE_OBSERVATION");
      if (expiresAtMs !== null && integer(expiresAtMs) <= time)
        fail("STALE_REGISTRATION");
    }
    function waitPort(fn) {
      checkAbort();
      const p = Promise.resolve().then(fn);
      pending.add(p);
      // Abort returns promptly; scheduler capacity remains reserved until an
      // uncooperative port settles, bounding abandoned provider operations.
      return new Promise((resolve, reject) => {
        const abort = () => reject(new ScanError("CANCELLED"));
        signal.addEventListener("abort", abort, { once: true });
        p.then(
          (v) => {
            pending.delete(p);
            signal.removeEventListener("abort", abort);
            resolve(v);
          },
          (e) => {
            pending.delete(p);
            signal.removeEventListener("abort", abort);
            reject(e);
          },
        );
        if (signal.aborted) abort();
      });
    }
    async function gate(operation) {
      checkAbort();
      const ok = await waitPort(() =>
        host.authorize(
          copy({
            ...ctx,
            requestId: req.requestId,
            sessionId: req.sessionId,
            operation,
          }),
          { signal },
        ),
      );
      checkAbort();
      if (ok !== true) fail("DENIED");
      if (operation === "publish" && admittedObservation)
        fresh(
          admittedObservation.receivedAtMs,
          admittedObservation.registration.state === "registered"
            ? admittedObservation.registration.expiresAtMs
            : null,
        );
    }
    async function call(operation, fn) {
      await gate(operation);
      const value = copy(await waitPort(fn));
      checkAbort();
      await gate(operation);
      return value;
    }
    async function run() {
      await gate("admit");
      // Host MUST atomically deduplicate tenant+actor+request ID and digest,
      // fence workers and prevent publication after revocation/cancellation.
      const result = copy(
        await waitPort(() =>
          host.runJob(
            copy({
              ...ctx,
              requestId: req.requestId,
              inputSha256: requestDigest,
            }),
            async () => {
              let observation = null,
                registration = "unregistered";
              if (req.mode !== "find") {
                const loaded = await call("read-observation", () =>
                  host.resolveObservation(
                    copy({ ...ctx, reference: req.observationRef }),
                    { signal },
                  ),
                );
                observation = validateObservation(loaded);
                if (digest(observation) !== req.observationSha256)
                  fail("OBSERVATION_CONFLICT");
                if (
                  observation.id !== req.observationRef ||
                  observation.tenantId !== ctx.tenantId ||
                  observation.sessionId !== req.sessionId
                )
                  fail("SCOPE_MISMATCH");
                admittedObservation = observation;
                const validCapture = await call("validate-capture", () =>
                  host.validateCapture(copy({ ...ctx, observation }), {
                    signal,
                  }),
                );
                if (validCapture !== true) fail("INVALID_CAPTURE");
                const time = integer(now());
                if (
                  observation.receivedAtMs > time ||
                  time - observation.receivedAtMs > LIMITS.maxAgeMs
                )
                  fail("STALE_OBSERVATION");
                if (observation.registration.state === "registered") {
                  if (observation.registration.expiresAtMs <= time)
                    fail("STALE_REGISTRATION");
                  const accepted = await call("validate-registration", () =>
                    host.validateRegistration(copy({ ...ctx, observation }), {
                      signal,
                    }),
                  );
                  if (accepted !== true) fail("INVALID_REGISTRATION");
                  registration = "registered";
                }
              }
              const base = {
                schemaVersion: 1,
                requestId: req.requestId,
                requestSha256: requestDigest,
                sourceCommit: ctx.sourceCommit,
                mode: req.mode,
                qualification: "host-injected-not-device-qualified",
                captureSourceKind: observation?.source.kind ?? null,
                registration,
                observationSha256: observation ? req.observationSha256 : null,
                observationReceivedAtMs: observation?.receivedAtMs ?? null,
                registrationExpiresAtMs:
                  registration === "registered"
                    ? observation.registration.expiresAtMs
                    : null,
              };
              if (req.mode === "find") {
                const found = await pages("read-memory", "searchSightings");
                const items = found.items.map(validateSighting);
                for (const x of items)
                  if (x.observedAtMs > integer(now()))
                    fail("INVALID_HOST_RESULT");
                items.sort(
                  (a, b) =>
                    b.observedAtMs - a.observedAtMs || a.id.localeCompare(b.id),
                );
                await gate("publish");
                return {
                  ...base,
                  status: items.length ? "last-observed" : "needs-evidence",
                  sightings: items,
                  hasMore: found.hasMore,
                  currentPresenceVerified: false,
                  actionAuthorized: false,
                };
              }
              if (req.mode === "verify") {
                const proof = await call("verify-identity", () =>
                  host.verifyIdentity(
                    copy({
                      ...ctx,
                      targetId: req.targetId,
                      observationRef: observation.id,
                      observationSha256: req.observationSha256,
                    }),
                    { signal },
                  ),
                );
                shape(proof, [
                  "targetId",
                  "observationSha256",
                  "status",
                  "evidenceRef",
                ]);
                text(proof.targetId);
                sha(proof.observationSha256);
                if (
                  proof.targetId !== req.targetId ||
                  proof.observationSha256 !== req.observationSha256 ||
                  !["verified", "ambiguous", "not-observed"].includes(
                    proof.status,
                  )
                )
                  fail("INVALID_IDENTITY_PROOF");
                if (proof.status === "verified") text(proof.evidenceRef);
                else if (proof.evidenceRef !== undefined)
                  fail("INVALID_IDENTITY_PROOF");
                await gate("publish");
                return {
                  ...base,
                  status:
                    proof.status === "verified"
                      ? "identity-verified"
                      : proof.status,
                  targetId: req.targetId,
                  identityEvidenceRef: proof.evidenceRef ?? null,
                  currentPresenceVerified: proof.status === "verified",
                  actionAuthorized: false,
                };
              }
              if (!observation.entities.length) {
                await gate("publish");
                return {
                  ...base,
                  status: "needs-evidence",
                  actionAuthorized: false,
                };
              }
              const found = await pages("read-procedures", "searchProcedures");
              const procedures = found.items;
              for (const p of procedures) {
                shape(p, [
                  "id",
                  "revision",
                  "sha256",
                  "documentSha256",
                  "entityId",
                  "instruction",
                  "sourceUrl",
                ]);
                for (const k of ["id", "revision", "entityId"]) text(p[k]);
                sha(p.sha256);
                sha(p.documentSha256);
                text(p.instruction, 1200);
                text(p.sourceUrl, 1000);
                if (procedureDigest(p) !== p.sha256) fail("PROCEDURE_CONFLICT");
                let url;
                try {
                  url = new URL(p.sourceUrl);
                } catch {
                  fail("INVALID_HOST_RESULT");
                }
                if (
                  url.protocol !== "https:" ||
                  url.username ||
                  url.password ||
                  !observation.entities.some((e) => e.id === p.entityId)
                )
                  fail("INVALID_HOST_RESULT");
              }
              if (!procedures.length) {
                await gate("publish");
                return {
                  ...base,
                  status: "needs-evidence",
                  actionAuthorized: false,
                };
              }
              // Exactly one model proposal. It chooses IDs; it cannot invent the
              // instruction, identity proof, pose, tools, authority or source text.
              const proposal = await call("model-proposal", () =>
                host.propose(
                  copy({
                    query: req.query,
                    observation: {
                      id: observation.id,
                      sha256: req.observationSha256,
                      entities: observation.entities,
                    },
                    procedures,
                  }),
                  { context: copy(ctx), signal },
                ),
              );
              shape(proposal, ["entityId", "procedureId", "procedureSha256"]);
              text(proposal.entityId);
              text(proposal.procedureId);
              sha(proposal.procedureSha256);
              const selected = procedures.find(
                (p) =>
                  p.id === proposal.procedureId &&
                  p.sha256 === proposal.procedureSha256 &&
                  p.entityId === proposal.entityId,
              );
              if (!selected) fail("UNGROUNDED_PROPOSAL");
              await gate("publish");
              return {
                ...base,
                status: "guidance-proposed",
                entityId: selected.entityId,
                instruction: selected.instruction,
                source: {
                  id: selected.id,
                  revision: selected.revision,
                  sha256: selected.sha256,
                  documentSha256: selected.documentSha256,
                  url: selected.sourceUrl,
                },
                requiresConfirmation: true,
                currentPresenceVerified: false,
                actionAuthorized: false,
              };

              async function pages(operation, method) {
                const items = [],
                  seen = new Set();
                let cursor = null;
                const cursors = new Set();
                for (let i = 0; i < LIMITS.catalogPages; i++) {
                  const page = await call(operation, () =>
                    host[method](
                      copy({
                        ...ctx,
                        query: req.query,
                        cursor,
                        limit: LIMITS.pageItems,
                        observationRef: observation?.id ?? null,
                      }),
                      { signal },
                    ),
                  );
                  // Host adapters must enforce limits before deserializing remote data.
                  if (
                    Buffer.byteLength(JSON.stringify(page) ?? "") >
                    LIMITS.pageBytes
                  )
                    fail("CATALOG_LIMIT");
                  shape(page, ["items", "nextCursor"]);
                  if (
                    !Array.isArray(page.items) ||
                    page.items.length > LIMITS.pageItems
                  )
                    fail("CATALOG_LIMIT");
                  for (const x of page.items) {
                    text(x?.id);
                    if (seen.has(x.id)) fail("DUPLICATE_EVIDENCE");
                    seen.add(x.id);
                    items.push(copy(x));
                  }
                  cursor = page.nextCursor;
                  if (cursor === null) return { items, hasMore: false };
                  text(cursor, 240);
                  if (cursors.has(cursor)) fail("CURSOR_LOOP");
                  cursors.add(cursor);
                }
                return { items, hasMore: true };
              }
            },
            { signal },
          ),
        ),
      );
      checkAbort();
      if (
        !result ||
        result.requestId !== req.requestId ||
        result.requestSha256 !== requestDigest ||
        result.sourceCommit !== ctx.sourceCommit ||
        result.mode !== req.mode ||
        result.schemaVersion !== 1 ||
        result.qualification !== "host-injected-not-device-qualified" ||
        result.actionAuthorized !== false ||
        result.observationSha256 !==
          (req.mode === "find" ? null : req.observationSha256)
      )
        fail("REPLAY_CONFLICT");
      if (req.mode !== "find" && !admittedObservation) {
        admittedObservation = validateObservation(
          await call("read-observation", () =>
            host.resolveObservation(
              copy({ ...ctx, reference: req.observationRef }),
              { signal },
            ),
          ),
        );
        if (
          digest(admittedObservation) !== req.observationSha256 ||
          admittedObservation.id !== req.observationRef ||
          admittedObservation.tenantId !== ctx.tenantId ||
          admittedObservation.sessionId !== req.sessionId
        )
          fail("REPLAY_CONFLICT");
      }
      if (admittedObservation) {
        if (
          result.captureSourceKind !== admittedObservation.source.kind ||
          result.observationReceivedAtMs !== admittedObservation.receivedAtMs ||
          result.registration !== admittedObservation.registration.state ||
          result.registrationExpiresAtMs !==
            (admittedObservation.registration.state === "registered"
              ? admittedObservation.registration.expiresAtMs
              : null)
        )
          fail("REPLAY_CONFLICT");
        if (
          (await call("validate-capture", () =>
            host.validateCapture(
              copy({ ...ctx, observation: admittedObservation }),
              { signal },
            ),
          )) !== true
        )
          fail("INVALID_CAPTURE");
        if (
          result.registration === "registered" &&
          (await call("validate-registration", () =>
            host.validateRegistration(
              copy({ ...ctx, observation: admittedObservation }),
              { signal },
            ),
          )) !== true
        )
          fail("INVALID_REGISTRATION");
      }
      await gate("publish");
      if (req.mode !== "find")
        fresh(result.observationReceivedAtMs, result.registrationExpiresAtMs);
      return copy(result);
    }
    try {
      return await schedule(run, signal, () =>
        Promise.allSettled([...pending]),
      );
    } catch (error) {
      // No provider exception messages, scene contents or raw media leak out.
      if (signal.aborted) throw new ScanError("CANCELLED");
      if (error instanceof ScanError) throw error;
      throw new ScanError("HOST_FAILURE");
    }
  }
  return Object.freeze({
    execute,
    stats: () => ({ active, queued: queue.length, maxConcurrent, maxQueued }),
  });
}
