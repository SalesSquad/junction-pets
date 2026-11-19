import { defineAgent } from "eve";

// A public starter must not expose Eve's default shell, filesystem, web, or
// delegation tools. Only explicitly authored proposal-only tools are available.
// sessionUsage prompts for continuation; it is not a hard billing limit.
export default defineAgent({
  model: "openai/gpt-6-luna-fast",
  defaultTools: false,
  limits: {
    sessionUsage: ({ window }) =>
      window.inputTokens - window.cacheReadTokens >= 15_000 ||
      window.outputTokens >= 3_000 ||
      (window.costUsd ?? 0) >= 0.25,
  },
});
