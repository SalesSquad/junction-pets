// Metadata-only telemetry contract. Never put prompts, replies, user IDs,
// claim tokens, tool arguments, or private context into exported attributes.
const ALLOWED_ATTRIBUTES = new Set([
  "gen_ai.operation.name",
  "gen_ai.system",
  "gen_ai.request.model",
  "gen_ai.response.model",
  "gen_ai.usage.input_tokens",
  "gen_ai.usage.output_tokens",
  "gen_ai.usage.cache_read.input_tokens",
  "gen_ai.usage.cache_write.input_tokens",
  "gen_ai.usage.cost",
  "agent.usage.input_tokens",
  "agent.usage.output_tokens",
  "agent.usage.cache_read_tokens",
  "agent.usage.cost_usd",
  "error.type",
]);

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

export function mayExportAttribute(key: string): boolean {
  return ALLOWED_ATTRIBUTES.has(key);
}

// Eve applies this policy to span attributes and content events before export.
// Resource metadata, span names and links still require a collector-side review.
export const metadataOnlyExportPolicy = {
  span: () => ({ redact: true as const, inputs: true, outputs: true }),
  attribute: ({ key }: { key: string }) => ({ emit: mayExportAttribute(key) }),
};

export function localOtlpTraceEndpoint(
  env: Readonly<Record<string, string | undefined>>,
): string | null {
  // The initial destination must be local; the trusted collector must prevent
  // off-host redirects/forwarding. No credentials come from Maker/conversation.
  if (env.CHIBI_EVE_OTLP_ENABLED !== "true") return null;
  const raw = env.CHIBI_EVE_OTLP_TRACES_URL;
  if (!raw || raw.length > 512 || raw !== raw.trim()) return null;

  let target: URL;
  try {
    target = new URL(raw);
  } catch {
    return null;
  }
  if (
    !LOOPBACK_HOSTS.has(target.hostname) ||
    !["http:", "https:"].includes(target.protocol) ||
    target.pathname !== "/v1/traces" ||
    target.username ||
    target.password ||
    target.search ||
    target.hash
  ) {
    return null;
  }
  return target.toString();
}
