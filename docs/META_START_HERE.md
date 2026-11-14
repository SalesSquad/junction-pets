# Meta / Chibi Lens — start here

Canonical repository: **SalesSquad/junction-pets**. Work lane:
`junction.meta.scan-lane-v1`, developer `junction-dev-meta`.

This page lets another Codex/Claude/developer agent resume without this chat or
access to a Mac. This integration branch incorporates the original [PR #60](https://github.com/SalesSquad/junction-pets/pull/60)
source-only runtime kernel and these research records. Confirm current GitHub main and merged PR before treating runtime as default-branch code; even successful source integration does not grant live Meta-device or Chibi-host access.

## Read in this order

| Need | Repository source |
| --- | --- |
| Product, scale, ownership and next native work | [META_SPATIAL_ARCHITECTURE.md](META_SPATIAL_ARCHITECTURE.md) |
| Full hardware / SDK / ARKit / spatial research | [Technical deep dive](research/META_GLASSES_ARKIT_20261113.md) |
| Official Discord posts and original links | [Discord source record](evidence/meta-discord-20261113.json) |
| Machine-readable discovery | [Source index](evidence/meta-source-index-20261113.json) |
| Runnable agent and host-port contracts | [Service README](../services/meta-spatial/README.md) |
| Runtime behavior and tool meanings | [Agent profile](../services/meta-spatial/agent-profile.md) |
| Code, tests and synthetic fixture | [Service directory](../services/meta-spatial/) |
| Source hashes, checks and review repairs | [Validation record](evidence/meta-scan-validation-20261113.json) |
| Existing Meta subject companion | [Meta package](../pets/meta/) |

## Native SDK development

[Apple source port](../apps/meta-lens-apple/README.md) and
[official DAT mock-video harness](../apps/meta-lens-apple/DATMockApp/README.md)
provide separate Mac replay and iOS SDK development paths. The latter uses
Meta SDK 1.0.1, a synthetic HEVC video and local Vision OCR; it does not grant
Chibi host authority or claim real glasses. Check the open implementation PR
for the latest source and native verification before resuming.

## Official resources confirmed in Discord

Meta staff posted these in [Junction #meta](https://discord.com/channels/1268184974784336004/1570753500630220820).
The [20:05 EET resource message](https://discord.com/channels/1268184974784336004/1570753500630220820/1570862075478020186)
on 13 November 2026 links:

- [Wearables Developer Center](https://wearables.developer.meta.com/)
- [DAT getting started](https://wearables.developer.meta.com/docs/develop/dat/getting-started-toolkit)
- [Web Apps docs](https://wearables.developer.meta.com/docs/develop/webapps)
- [iOS SDK and samples](https://github.com/meta/meta-wearables-dat-ios)
- [Android SDK and samples](https://github.com/meta/meta-wearables-dat-android)
- [Display web-app toolkit](https://github.com/meta/meta-wearables-webapp)
- [Display Simulator](https://chromewebstore.google.com/detail/jpjlmmodokemlepklkdbimceggpbjcll)

The public documentation MCP is `https://mcp.developer.meta.com/wearables`.
Anonymous initialization, tool discovery and DAT/Web Apps searches were actually
verified during this research. Documentation access is distinct from Developer
Center account permissions. The report records source versions and limits.

## Product and implemented slice

**Chibi Lens — Find & Verify:** retrieve where an important object was last
observed, then verify the current physical candidate with fresh evidence.
The first kernel implements inspect, find and verify through trusted host ports.
It preserves historical sightings, uncertainty, source revisions, capture identity
and registration boundaries. It does not implement the real capture adapter,
private persistent memory or a production provider route.

```sh
node --test services/meta-spatial/agent.test.mjs
node services/meta-spatial/demo.mjs
```

The recorded code slice passed 37/37 focused tests and 744/744 full Node tests at
`56b306b405b8bee4026a29460a469e08efc49b0e`, with independent focused review and
remote-byte matching. Later documentation-only commits retain that code evidence;
do not generalize it to later code edits or physical glasses qualification.

## Non-negotiable technical distinctions

- DAT is the native route for our own glasses camera pipeline. Display web apps
  provide an optional small UI and WebMCP tools, without raw camera capture.
- ARKit tracks the phone. Glasses-to-map registration needs independently
  calibrated geometry and trustworthy timing; pairing is insufficient.
- A remembered sighting is not proof of an object's current location. Visual
  similarity is a candidate, not physical identity verification.
- Chibi remains the authority for identity, consent, private memory and effects.
  The existing dispatch ledger is the durable-worker path.
- A synthetic demo, source registration and live hardware execution are separate
  evidence classes. Current gaps are listed in the architecture and validation.

## Hardware and next step

[Hardware lending instructions](https://discord.com/channels/1268184974784336004/1570821452188483715/1570851584168960052)
require a request at [the hardware page](https://2026.hackjunction.com/hardware),
up to two prioritized items, a table number and physical pickup at Arduino
Hardware Lab with the responsible person's ID. No stock/allocation, request,
pairing or reset is claimed here. Troubleshooting links are in the Discord record.

Next native lane: connect one real DAT frame and routed audio reply to Lens
evidence admission, then implement host-owned append-only sightings/corrections.
Keep calibration/marker registration as an independently measured step. Check
current PR ownership before editing shared contracts or generated packages.
