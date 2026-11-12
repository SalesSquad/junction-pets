# Junction Pets — portable plugin packages

Each of the 34 independently authored company companions has a **skills-only Agent Plugins 1.0 source package** under `plugins/junction-<company>/`. Packages are generated deterministically from each pet's existing `pet.json`, `AGENTS.md`, `STORY.md`, and `evals.json`. No Chibi.pet private runtime code is included.

## Package contents

| Path | Purpose |
| --- | --- |
| `plugin.json` | Portable Agent Plugins 1.0 identity, version, developer and honest scope |
| `skills/junction-<company>-companion/SKILL.md` | Self-contained company-specific instructions copied from the canonical `pets/` package, with non-endorsement and host-permission boundaries |
| `assets/source-manifest.json` | SHA-256 hashes of the four source files, package version and explicit unverified execution markers |

The supplied 34 packages contain **no `mcp.json`**: there is no verified portable, separately authorized Chibi MCP endpoint for these plugin identities. Do not invent a server URL, scope, tool or connected app ID. A skills-only plugin offers focused behavior instructions, not a real chat service or an agent-to-agent transport. The future shared Chibi host/Gateway can provide those capabilities after exact user grants and connection tests.

## Generate and verify

```sh
node scripts/build-pet-plugins.mjs
node scripts/build-pet-plugins.mjs --check
node --test tests/pet-plugins.test.mjs
```

The generator emits exactly **34 plugin directories / 102 tracked files**. `--check` rejects source drift and never rewrites files. Source manifests bind file content, not the current GitHub commit. The latter stays `null` until a task-owned exact commit is verified. Neither successful generation nor passing Node tests proves account installation, Cloud environment provisioning, model evaluation, provider connection, permission or publishing.

## Installing later

Each package can be reviewed and archived separately under the `plugin.json` root with no extra siblings, then saved as a private personal/workspace plugin through the supported Plugin Creator workflow or an authorized Codex plugin marketplace. Validate schema and the actual installed tool/skill identity, inspect the result and only then store its provider plugin ID in the source-bound operations registry. Preserve a single installed instance per company identity and update its version: do not create duplicates blindly.

The existing **Chibi.pet**, **Valmet Companion** and **Junction Mission Control** Sites plugins must remain distinct from these skills-only packages. They are existing applications. We do not wrap or republish them as 34 competing Sites services. If a verified Chibi MCP service becomes available, add one shared, least-privilege connection adapter with explicit per-pet capability grants and test revocation. Chibi owns adoption, private memory, policy and provider execution. Cross-pet cooperation uses task-scoped messages with provenance and authorization, not arbitrary memory sharing.

No plugin was installed, published, deployed or granted permissions by this development step. Any public directory submission, Chibi production hookup or new paid executor remains separately gated.
