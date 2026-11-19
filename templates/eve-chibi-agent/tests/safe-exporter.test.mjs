import assert from "node:assert/strict";
import { test } from "node:test";
import { createServer } from "node:http";
import { once } from "node:events";
import { OTLPHttpProtoTraceExporter } from "@vercel/otel";
import { ExportResultCode } from "@opentelemetry/core";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { otelIntegration } from "eve/instrumentation/otel";
import {
  createSafeTraceExporter,
  sanitizeSpan,
} from "../agent/safe-trace-exporter.ts";
import { metadataOnlyExportPolicy } from "../agent/telemetry-policy.ts";

const SECRET = "synthetic-private-user@example.invalid";
const traceId = "a".repeat(32);
const spanId = "b".repeat(16);

function syntheticSpan(overrides = {}) {
  return {
    name: SECRET,
    kind: 2,
    spanContext: () => ({
      traceId,
      spanId,
      traceFlags: 1,
      traceState: { serialize: () => SECRET },
    }),
    parentSpanContext: {
      traceId: "c".repeat(32),
      spanId: "d".repeat(16),
      traceFlags: 1,
      traceState: { serialize: () => SECRET },
    },
    startTime: [1, 10],
    endTime: [2, 20],
    duration: [1, 10],
    status: { code: 2, message: SECRET },
    attributes: {
      "gen_ai.input.messages": SECRET,
      "gen_ai.output.messages": SECRET,
      "gen_ai.request.model": SECRET,
      "gen_ai.usage.input_tokens": 12,
      "gen_ai.usage.output_tokens": Number.NaN,
      "gen_ai.usage.cost": 0.001,
      "user.id": SECRET,
      "tenant.id": SECRET,
      "http.url": SECRET,
    },
    links: [{ context: { traceId, spanId, traceFlags: 1 }, attributes: { user: SECRET } }],
    events: [{ name: SECRET, time: [1, 15], attributes: { error: SECRET } }],
    ended: true,
    resource: resourceFromAttributes({
      "deployment.id": SECRET,
      "vcs.ref.head.name": SECRET,
      "service.name": SECRET,
    }),
    instrumentationScope: { name: SECRET, version: SECRET },
    droppedAttributesCount: 0,
    droppedEventsCount: 0,
    droppedLinksCount: 0,
    ...overrides,
  };
}

test("sanitizer reconstructs a content-free, fixed-resource OTLP span", () => {
  const safe = sanitizeSpan(syntheticSpan());
  assert.ok(safe);
  assert.equal(safe.name, "eve.operation");
  assert.equal(safe.kind, 0);
  assert.deepEqual(safe.attributes, {
    "gen_ai.usage.input_tokens": 12,
    "gen_ai.usage.cost": 0.001,
  });
  assert.deepEqual(safe.events, []);
  assert.deepEqual(safe.links, []);
  assert.deepEqual(safe.status, { code: 2 });
  assert.deepEqual(safe.resource.attributes, { "service.name": "chibi-eve-starter" });
  assert.deepEqual(safe.instrumentationScope, { name: "chibi-eve-starter" });
  assert.deepEqual(safe.duration, [1, 10]);
  assert.equal("traceState" in safe.spanContext(), false);
  assert.equal("traceState" in safe.parentSpanContext, false);
  assert.equal(
    JSON.stringify({ ...safe, context: safe.spanContext() }).includes(SECRET),
    false,
  );
});

test("sanitized resource and scope cannot contaminate later spans", () => {
  const first = sanitizeSpan(syntheticSpan());
  const second = sanitizeSpan(syntheticSpan());
  assert.ok(first && second);
  assert.notEqual(first.resource, second.resource);
  assert.notEqual(first.instrumentationScope, second.instrumentationScope);
  first.instrumentationScope.name = SECRET;
  try {
    first.resource.attributes["service.name"] = SECRET;
  } catch {
    // Some OTel Resource implementations protect the attributes object.
  }
  assert.deepEqual(second.instrumentationScope, { name: "chibi-eve-starter" });
  assert.deepEqual(second.resource.attributes, { "service.name": "chibi-eve-starter" });
});

test("exporter refuses unsafe batches and delegates only sanitized spans", async () => {
  let exported = [];
  let flushes = 0;
  let shutdowns = 0;
  const delegate = {
    export(spans, callback) {
      exported.push(...spans);
      callback({ code: ExportResultCode.SUCCESS });
    },
    forceFlush: async () => { flushes += 1; },
    shutdown: async () => { shutdowns += 1; },
  };
  const exporter = createSafeTraceExporter(delegate);
  let result;
  exporter.export([syntheticSpan()], (value) => { result = value; });
  assert.equal(result.code, ExportResultCode.SUCCESS);
  assert.equal(exported.length, 1);
  assert.equal(exported[0].resource.attributes["deployment.id"], undefined);

  const bad = syntheticSpan({
    spanContext: () => ({ traceId: "invalid", spanId, traceFlags: 1 }),
  });
  exporter.export([syntheticSpan(), bad], (value) => { result = value; });
  assert.equal(result.code, ExportResultCode.FAILED);
  assert.equal(exported.length, 1, "no partially sanitized batch may be sent");
  exporter.export([syntheticSpan({ status: { code: 2, message: SECRET }, ended: false })],
    (value) => { result = value; });
  assert.equal(result.code, ExportResultCode.FAILED);
  assert.equal(exported.length, 1);
  await exporter.forceFlush();
  await exporter.shutdown();
  assert.equal(flushes, 1);
  assert.equal(shutdowns, 1);
});

test("Eve's actual v1.1 export processor filters synthetic private content", () => {
  const captured = [];
  const delegate = {
    onStart() {},
    onEnd(span) { captured.push(span); },
    forceFlush: async () => {},
    shutdown: async () => {},
  };
  const integration = otelIntegration({
    exportPolicy: metadataOnlyExportPolicy,
    spanProcessors: [delegate],
  });
  assert.equal(integration.spanProcessors.length, 1);
  integration.spanProcessors[0].onEnd(syntheticSpan());
  assert.equal(captured.length, 1);
  assert.equal(captured[0].attributes["gen_ai.input.messages"], undefined);
  assert.equal(captured[0].attributes["gen_ai.usage.input_tokens"], 12);
  const sanitized = sanitizeSpan(captured[0]);
  assert.ok(sanitized);
  assert.deepEqual(sanitized.resource.attributes, { "service.name": "chibi-eve-starter" });
  assert.equal(JSON.stringify(sanitized).includes(SECRET), false);
});

test("actual OTLP/protobuf transport sends only sanitized synthetic bytes locally", async () => {
  let received = null;
  let method = null;
  let url = null;
  const server = createServer((request, response) => {
    method = request.method;
    url = request.url;
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      received = Buffer.concat(chunks);
      response.writeHead(200, { "content-type": "application/x-protobuf" });
      response.end();
    });
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  const exporter = createSafeTraceExporter(
    new OTLPHttpProtoTraceExporter({
      url: `http://127.0.0.1:${address.port}/v1/traces`,
      timeoutMillis: 2_000,
    }),
  );
  try {
    const result = await new Promise((resolve) => {
      exporter.export([syntheticSpan()], resolve);
    });
    assert.equal(result.code, ExportResultCode.SUCCESS);
    assert.equal(method, "POST");
    assert.equal(url, "/v1/traces");
    assert.ok(received?.length > 0);
    assert.equal(received.includes(Buffer.from(SECRET)), false);
    assert.equal(received.includes(Buffer.from("deployment.id")), false);
    assert.equal(received.includes(Buffer.from("gen_ai.request.model")), false);
    assert.equal(received.includes(Buffer.from("chibi-eve-starter")), true);
    assert.equal(received.includes(Buffer.from("gen_ai.usage.input_tokens")), true);
  } finally {
    await exporter.shutdown();
    await new Promise((resolve) => server.close(resolve));
  }
});
