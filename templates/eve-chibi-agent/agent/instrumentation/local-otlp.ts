import { OTLPHttpProtoTraceExporter } from "@vercel/otel";
import { disableInstrumentation } from "eve/instrumentation";
import { otelIntegration } from "eve/instrumentation/otel";
import {
  localOtlpTraceEndpoint,
  metadataOnlyExportPolicy,
} from "../telemetry-policy.ts";

// Disabled unless the trusted host explicitly enables a LOCAL collector.
// The collector can later forward to Langfuse, Phoenix or another OTLP sink.
// Destination redaction does not modify Eve's durable workflow retention.
const endpoint = localOtlpTraceEndpoint(process.env);

export default endpoint
  ? otelIntegration({
      exportPolicy: metadataOnlyExportPolicy,
      traceExporter: new OTLPHttpProtoTraceExporter({ url: endpoint }),
    })
  : disableInstrumentation();
