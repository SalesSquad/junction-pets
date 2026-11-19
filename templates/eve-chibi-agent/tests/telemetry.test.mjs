import assert from "node:assert/strict";
import { test } from "node:test";
import {
  localOtlpTraceEndpoint,
  mayExportAttribute,
  metadataOnlyExportPolicy,
} from "../agent/telemetry-policy.ts";

const local = "http://127.0.0.1:4318/v1/traces";
const config = (url = local) => ({
  CHIBI_EVE_OTLP_ENABLED: "true",
  CHIBI_EVE_OTLP_TRACES_URL: url,
});

test("telemetry is explicitly opt-in and stays local", () => {
  assert.equal(localOtlpTraceEndpoint({}), null);
  assert.equal(localOtlpTraceEndpoint({ CHIBI_EVE_OTLP_TRACES_URL: local }), null);
  assert.equal(localOtlpTraceEndpoint({ CHIBI_EVE_OTLP_ENABLED: "true" }), null);
  assert.equal(localOtlpTraceEndpoint(config()), local);
  assert.equal(
    localOtlpTraceEndpoint(config("https://[::1]:4318/v1/traces")),
    "https://[::1]:4318/v1/traces",
  );
});

test("external egress, embedded credentials and non-trace paths are rejected", () => {
  for (const url of [
    "https://cloud.langfuse.com/api/public/otel/v1/traces",
    "http://127.0.0.1.evil.example/v1/traces",
    "http://user:password@127.0.0.1:4318/v1/traces",
    "http://127.0.0.1:4318/v1/traces?key=secret",
    "http://127.0.0.1:4318/v1/traces#fragment",
    "http://127.0.0.1:4318/v1/metrics",
    "file:///v1/traces",
  ]) {
    assert.equal(localOtlpTraceEndpoint(config(url)), null, url);
  }
});

test("Eve export policy redacts content and applies the attribute allowlist", () => {
  assert.deepEqual(metadataOnlyExportPolicy.span(), {
    redact: true,
    inputs: true,
    outputs: true,
  });
  assert.deepEqual(
    metadataOnlyExportPolicy.attribute({ key: "gen_ai.usage.input_tokens" }),
    { emit: true },
  );
  assert.deepEqual(
    metadataOnlyExportPolicy.attribute({ key: "gen_ai.input.messages" }),
    { emit: false },
  );
});

test("only non-content, non-identity attributes may be emitted on Eve spans", () => {
  for (const key of [
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.request.model",
    "error.type",
  ]) {
    assert.equal(mayExportAttribute(key), true, key);
  }
  for (const key of [
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.conversation.id",
    "agent.run.id",
    "vercel.session_id",
    "user.id",
    "customer.email",
    "http.url",
    "gen_ai.tool.call.arguments",
    "claim_token",
    "original_key",
    "input_digest",
    "ai.settings.context.goal",
  ]) {
    assert.equal(mayExportAttribute(key), false, key);
  }
});
