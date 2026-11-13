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

## Private registrations and installation boundary

All **34 canonical plugin identities** have now been registered privately through ChatGPT Plugin Creator, with provider IDs, release IDs and USER/PRIVATE scope read back. Their exact source-bound receipts live under `ops/plugin-registrations/<company>.json`; Mission Control reports `registered-source-matched-reported` only when the three generated plugin files still match these receipts. This means **account-level registration**, not installation in Chibi, connected tool permissions, working Codex Cloud environments or a live model demonstration. Treat the provider readback timestamp as a point-in-time observation, not an always-live status.

Two additional private registration IDs were observed for `junction-s-pankki` and `junction-scailab` during an asynchronous batch. These are **not canonical** and are not connected to the per-pet registry. They were preserved rather than removed without separate deletion authority. Future updates must target the canonical per-pet ID and release; never create another identity as an unverified retry.

Each package can be reviewed and archived separately under the `plugin.json` root with no extra siblings. When connecting it to a host, verify the actual installed tool/skill identity and separately record the Chibi-specific capability grant. A provider plugin ID alone cannot establish Chibi installation or model execution.

The existing **Chibi.pet**, **Valmet Companion** and **Junction Mission Control** Sites plugins must remain distinct from these skills-only packages. They are existing applications. We do not wrap or republish them as 34 competing Sites services. If a verified Chibi MCP service becomes available, add one shared, least-privilege connection adapter with explicit per-pet capability grants and test revocation. Chibi owns adoption, private memory, policy and provider execution. Cross-pet cooperation uses task-scoped messages with provenance and authorization, not arbitrary memory sharing.

The 34 plugins were **privately registered**; none was publicly published, verified as installed in Chibi, deployed as a Chibi runtime, or granted additional host permissions by this development step. Any public directory submission, Chibi production hookup or new paid executor remains separately gated.
