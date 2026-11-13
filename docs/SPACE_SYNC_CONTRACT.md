# Junction 2026 Space sync contract (source-bound)

**Owner:** One Man Raid / Junction 2026 Space.
**Canonical Space:** [Junction 2026](https://chatgpt.com/space/page_6af3b8dc0344819187d978137d64c52d).
**GitHub repository:** `SalesSquad/junction-pets` (private).

## Scope and source priority

| Source | Owns | Required verification | Fallback when unavailable |
| --- | --- | --- | --- |
| Official Junction brief / Participant Guide | Challenge rules, deadlines, submission acceptance | Exact canonical URL, observation time, authenticated page if necessary | Preserve last verified value, mark stale/blocked, never invent |
| Junction Platform / authorized organizer notice | Team-specific submission state, organizer exceptions | Signed-in account, original notice link and timestamp | Mark unverified; do not infer Chrome drafts from Safari |
| GitHub repository | Source implementation, PR states, agent registry | Live `main` SHA, PR number/state/head/merged-at and source integration path | Retain previous SHA and source age; never treat dated index as live |
| ChatGPT Pages | Canonical Space card identity/content and sync receipts | Parent-child Page ID readback, target hash before/after write | Do not create a duplicate Page or erase prior receipt |
| Discord | Partner announcements | Authorized existing read path, original message URL, timestamp | Bot install explicitly unavailable; no unauthorized bypass |

**Hard distinctions:** submitted ≠ saved draft; merged source ≠ provider connected; test passed ≠ deployed; agent graph edge ≠ permission to call another agent. A PR still open can have its implementation already integrated via another PR.

## Current topology (observed 14 Nov 2026)

- 53 Pages total: root and first-level Pages plus nested challenge, technology, Discord and evidence pages.
- 19 main challenge brief URLs mapped to 19 main cards.
- 19 technology brief URLs mapped to 16 canonical technology cards (some cover multiple briefs).
- 34 agent packages; the composition graph has 122 **proposed** edges, not automatic live dispatch.
- Canonical Page inventory: `ops/challenge-spaces-reconciliation-20261113.json#canonical_page_inventory`. Its `outcome.card_pages=30` is **historical** (13 Nov earlier reconciliation); the newly verified inventory is 35.

## Two independent refresh paths, one source of truth

1. **GitHub PR event worker**: Page-managed task `Automation_e5143ffe82bc81919c13d4b56eab2429`, child of controller `Automation_678484eb87648191bea1e57f60d626fc`. Webhook: `SalesSquad/junction-pets` pull-request lifecycle plus new commits/reviews. Updates only the single `J26-GH-PR-EVENT` checkpoint on canonical [07 Testit ja todisteet](https://chatgpt.com/space/page_3c473ad5272c8191b95c24dadc5141ab). It does **not** write challenge cards.
2. **Scheduled full reconciliation**: Page-managed task `Automation_ba429296e6348191a9c7ea2531e905cb`, hourly (Europe/Helsinki), verifies current main and relevant PRs and refreshes canonical child Pages with source-bound differences. Responsible for missed PR notifications and direct main changes outside the PR event schema.
3. **Root controller**: Page Auto update `Automation_678484eb87648191bea1e57f60d626fc` owns root navigation and child attachment checks.

The webhook subscription cannot deliver arbitrary GitHub branch `push` events. The schedule is the safety net. None of these task configurations alone proves a successful hosted run or source access; record a real run receipt.

## One-source machine contract

The agent routing index is `docs/AGENT_SOURCE_INDEX.json`:

- `observedAt`, `observedMainHead`: dated readback, **never** a substitute for GitHub.
- `agents[34]`: one `junction.<slug>` ID, manifest, runtime instruction source, challenge research and development configuration per package.
- `extensions[].observedState`: status of the **original** PR at the observation time.
- `extensions[].isMainImplementation` and optional `mainIntegration`: source presence in main, with the actual integration PR and commit. This may be true even while the origin PR remains open.
- `ops/challenge-spaces-reconciliation-20261113.json`: brief URL coverage and canonical Page IDs, including 5 additional technology Pages verified on 14 Nov.

Consumers (Codex, Claude, Chibi, Pages workers) must read the same index, pin exact source commits and recheck status with GitHub. The index is routing information, not an access grant or a shared secret store. Skill/agent invocation still requires its host's existing authorization and receipt boundaries.

## Minimal refresh algorithm

For each event or hourly pass:

1. Verify active current controller and owned task attachment. If missing, exit without mutation.
2. Fetch live repository head and affected PRs. Compare with previous successful receipt, not with a historic README alone.
3. Resolve source PR and integration PR separately. Confirm challenge rule changes against organizer sources.
4. For each changed canonical Page, read its exact current block IDs/hashes; update only the owned section. If source or target is unchanged, perform **no write**.
5. Read the modified Page back. Record a bounded receipt: `source`, `last_attempt_at`, `last_success_at`, `source_ref`, `main_sha`, `access_status=verified|stale|blocked`, `changed_page_ids`, `automation_run_id`, `outcome`, `blocker`.
6. On a 403, 429, stale hash or failed external auth, preserve the previous successful result and make the blocker visible. Do not create a replacement Page, forge an observation timestamp, downgrade tests or repeatedly retry.

**Write ownership:** PR-event task owns the event checkpoint only; hourly child worker owns challenge/technology and source summaries; root controller owns root. Collision: fail closed on stale Page block hash, re-read before retry. Never write historical test evidence as if it were a fresh run.

## Verification

```sh
npm run source-sync:check
npm run agents:check
npm run validate
npm test
npm run build
```

`source-sync:check` is an **offline structural gate**. It checks 34 agent entries, 19+19 source mappings, 35 unique canonical card IDs, and that integration receipts do not coexist with false `isMainImplementation:false`. It cannot validate future GitHub merges or authenticate to Pages; live reads are mandatory.

**Do not sync:** raw Discord dumps, provider credentials, private video bodies, Chrome session databases, confidential family data, or unapproved cross-agent histories. Any new Discord bot installation, Junction API scope, production webhook service, or live submission requires the normal authority of its owning service.
