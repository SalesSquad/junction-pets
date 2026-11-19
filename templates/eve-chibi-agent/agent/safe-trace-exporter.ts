import { ExportResultCode } from "@opentelemetry/core";
import type { ExportResult } from "@opentelemetry/core";
import { resourceFromAttributes } from "@opentelemetry/resources";
import type { ReadableSpan, SpanExporter } from "@opentelemetry/sdk-trace";
import { SAFE_USAGE_ATTRIBUTES } from "./telemetry-policy.ts";

// The exporter is the LAST privacy boundary before OTLP serialization.
// Eve's exportPolicy filters span attributes, but not resource, links or names.
const SAFE_SERVICE_NAME = "chibi-eve-starter";
const USAGE_METRICS = SAFE_USAGE_ATTRIBUTES;

type SpanContext = ReturnType<ReadableSpan["spanContext"]>;
function safeContext(context: SpanContext): SpanContext | null {
  if (
    !/^[a-f0-9]{32}$/i.test(context.traceId) ||
    !/^[a-f0-9]{16}$/i.test(context.spanId) ||
    /^0+$/.test(context.traceId) ||
    /^0+$/.test(context.spanId) ||
    !Number.isInteger(context.traceFlags) ||
    context.traceFlags < 0 ||
    context.traceFlags > 255
  ) return null;
  // Drop traceState/baggage, remote metadata and any other contextual fields.
  return {
    traceId: context.traceId.toLowerCase(),
    spanId: context.spanId.toLowerCase(),
    traceFlags: context.traceFlags,
  };
}

function safeTime(value: ReadableSpan["startTime"]): [number, number] | null {
  if (
    !Array.isArray(value) ||
    value.length !== 2 ||
    !Number.isSafeInteger(value[0]) ||
    value[0] < 0 ||
    !Number.isInteger(value[1]) ||
    value[1] < 0 ||
    value[1] >= 1_000_000_000
  ) return null;
  return [value[0], value[1]];
}

// Returns a NEW complete ReadableSpan. Never spread Eve's span proxy or retain
// arbitrary string values. Invalid structural fields fail closed.
export function sanitizeSpan(span: ReadableSpan): ReadableSpan | null {
  const context = safeContext(span.spanContext());
  const start = safeTime(span.startTime);
  const end = safeTime(span.endTime);
  if (!context || !start || !end || !span.ended) return null;
  if (end[0] < start[0] || (end[0] === start[0] && end[1] < start[1])) {
    return null;
  }
  if (!Number.isInteger(span.status.code) || span.status.code < 0 ||
      span.status.code > 2) return null;

  const attributes: Record<string, number> = {};
  for (const key of USAGE_METRICS) {
    const value = span.attributes[key];
    if (
      typeof value === "number" &&
      Number.isFinite(value) &&
      value >= 0 &&
      value <= Number.MAX_SAFE_INTEGER
    ) attributes[key] = value;
  }
  const parent = span.parentSpanContext
    ? safeContext(span.parentSpanContext)
    : null;
  let seconds = end[0] - start[0];
  let nanos = end[1] - start[1];
  if (nanos < 0) {
    seconds -= 1;
    nanos += 1_000_000_000;
  }

  return {
    name: "eve.operation",
    kind: 0, // INTERNAL; never use an untrusted span kind to select actions.
    spanContext: () => context,
    ...(parent ? { parentSpanContext: parent } : {}),
    startTime: start,
    endTime: end,
    duration: [seconds, nanos],
    status: { code: span.status.code }, // Never copy status.message.
    attributes,
    links: [],
    events: [],
    ended: true,
    // Fresh objects per span prevent a mutating downstream exporter from
    // contaminating a later batch with resource or scope data.
    resource: resourceFromAttributes({ "service.name": SAFE_SERVICE_NAME }),
    instrumentationScope: { name: SAFE_SERVICE_NAME },
    droppedAttributesCount: 0,
    droppedEventsCount: 0,
    droppedLinksCount: 0,
  };
}

// No network calls or credentials here. Delegation happens only after the
// entire batch has passed sanitization; one unsafe span rejects the batch.
export function createSafeTraceExporter(delegate: SpanExporter): SpanExporter {
  return {
    export(spans: ReadableSpan[], callback: (result: ExportResult) => void) {
      let reported = false;
      const report = (result: ExportResult) => {
        if (!reported) {
          reported = true;
          callback(result);
        }
      };
      try {
        const safe: ReadableSpan[] = [];
        for (const span of spans) {
          const clean = sanitizeSpan(span);
          if (!clean) {
            report({
              code: ExportResultCode.FAILED,
              error: new Error("OTLP span rejected by privacy policy"),
            });
            return;
          }
          safe.push(clean);
        }
        if (!safe.length) {
          report({ code: ExportResultCode.SUCCESS });
          return;
        }
        delegate.export(safe, report);
      } catch {
        report({
          code: ExportResultCode.FAILED,
          error: new Error("OTLP export blocked"),
        });
      }
    },
    shutdown: () => delegate.shutdown(),
    forceFlush: () => delegate.forceFlush?.() ?? Promise.resolve(),
  };
}
