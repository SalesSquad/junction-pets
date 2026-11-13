import { createHash } from "node:crypto";

export class ScanError extends Error {
  constructor(code) {
    super(code);
    this.name = "ScanError";
    this.code = code;
  }
}
export function fail(code) {
  throw new ScanError(code);
}
export function shape(x, keys) {
  if (
    !x ||
    Object.getPrototypeOf(x) !== Object.prototype ||
    Object.keys(x).some((k) => !keys.includes(k))
  )
    fail("INVALID_INPUT");
  return x;
}
export function text(x, max = 160) {
  if (
    typeof x !== "string" ||
    !x.length ||
    x.length > max ||
    x.trim() !== x ||
    /[\u0000-\u001f]/.test(x)
  )
    fail("INVALID_INPUT");
  return x;
}
export function integer(x, min = 0, max = Number.MAX_SAFE_INTEGER) {
  if (!Number.isSafeInteger(x) || x < min || x > max) fail("INVALID_INPUT");
  return x;
}
export function sha(x, n = 64) {
  if (typeof x !== "string" || !new RegExp(`^[a-f0-9]{${n}}$`).test(x))
    fail("INVALID_INPUT");
  return x;
}
export function canonical(x) {
  if (x === null || typeof x !== "object") return JSON.stringify(x);
  if (Array.isArray(x)) return "[" + x.map(canonical).join(",") + "]";
  return (
    "{" +
    Object.keys(x)
      .sort()
      .map((k) => JSON.stringify(k) + ":" + canonical(x[k]))
      .join(",") +
    "}"
  );
}
export function digest(x) {
  return createHash("sha256").update(canonical(x)).digest("hex");
}
export function procedureDigest(p) {
  const { sha256, ...record } = p;
  return digest(record);
}
export function copy(x) {
  return structuredClone(x);
}
export function validateContext(x) {
  shape(x, ["tenantId", "actorId", "sourceCommit"]);
  text(x.tenantId);
  text(x.actorId);
  sha(x.sourceCommit, 40);
  return copy(x);
}
export function validateRequest(x) {
  shape(x, [
    "schemaVersion",
    "requestId",
    "sessionId",
    "mode",
    "query",
    "observationRef",
    "observationSha256",
    "targetId",
  ]);
  if (x.schemaVersion !== 1 || !["inspect", "find", "verify"].includes(x.mode))
    fail("INVALID_INPUT");
  text(x.requestId);
  text(x.sessionId);
  text(x.query, 400);
  if (x.mode !== "find") {
    text(x.observationRef);
    sha(x.observationSha256);
  } else if (
    x.observationRef !== undefined ||
    x.observationSha256 !== undefined
  )
    fail("INVALID_INPUT");
  if (x.mode === "verify") text(x.targetId);
  else if (x.targetId !== undefined) fail("INVALID_INPUT");
  return copy(x);
}
export function validateObservation(x) {
  shape(x, [
    "schemaVersion",
    "id",
    "tenantId",
    "sessionId",
    "generation",
    "receivedAtMs",
    "source",
    "frame",
    "entities",
    "registration",
  ]);
  if (x.schemaVersion !== 1) fail("INVALID_OBSERVATION");
  for (const k of ["id", "tenantId", "sessionId"]) text(x[k]);
  integer(x.generation, 1);
  integer(x.receivedAtMs);
  shape(x.source, ["kind", "deviceId"]);
  text(x.source.deviceId);
  if (
    !["meta-camera", "phone-camera", "import", "fixture"].includes(
      x.source.kind,
    )
  )
    fail("INVALID_OBSERVATION");
  shape(x.frame, ["sha256", "width", "height"]);
  sha(x.frame.sha256);
  integer(x.frame.width, 1, 16384);
  integer(x.frame.height, 1, 16384);
  if (!Array.isArray(x.entities) || x.entities.length > 32)
    fail("INVALID_OBSERVATION");
  const ids = new Set();
  for (const e of x.entities) {
    shape(e, ["id", "label", "confidence"]);
    text(e.id);
    text(e.label, 240);
    if (
      ids.has(e.id) ||
      typeof e.confidence !== "number" ||
      !Number.isFinite(e.confidence) ||
      e.confidence < 0 ||
      e.confidence > 1
    )
      fail("INVALID_OBSERVATION");
    ids.add(e.id);
  }
  shape(x.registration, [
    "state",
    "mapId",
    "poseRef",
    "calibrationRef",
    "expiresAtMs",
  ]);
  if (x.registration.state === "unregistered") {
    if (Object.keys(x.registration).length !== 1) fail("INVALID_REGISTRATION");
  } else if (x.registration.state === "registered") {
    for (const k of ["mapId", "poseRef", "calibrationRef"])
      text(x.registration[k]);
    integer(x.registration.expiresAtMs);
  } else fail("INVALID_REGISTRATION");
  return copy(x);
}
export function validateSighting(x) {
  shape(x, [
    "id",
    "targetId",
    "label",
    "zone",
    "observedAtMs",
    "observationRef",
    "observationSha256",
  ]);
  for (const k of ["id", "targetId", "observationRef"]) text(x[k]);
  text(x.label, 240);
  text(x.zone, 240);
  integer(x.observedAtMs);
  sha(x.observationSha256);
  return copy(x);
}
export const LIMITS = Object.freeze({
  catalogPages: 2,
  pageItems: 8,
  pageBytes: 16384,
  maxAgeMs: 15000,
  maxEntities: 32,
});
export const TOOL_DESCRIPTORS = Object.freeze([
  {
    name: "meta.scan.inspect",
    mode: "inspect",
    effect: "read-and-propose",
    description:
      "Select a visible entity and a cited next step from bounded evidence.",
  },
  {
    name: "meta.memory.find",
    mode: "find",
    effect: "read",
    description:
      "Retrieve last-observed sightings; never asserts present location.",
  },
  {
    name: "meta.object.verify",
    mode: "verify",
    effect: "read",
    description: "Request host-verified identity against a fresh observation.",
  },
]);
