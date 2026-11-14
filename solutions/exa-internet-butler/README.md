# Fieldnote — Event Opportunity Concierge

Maturity **2/6**, executable local product source; browser and sponsor API qualification
remain outstanding. Independent, event-born code. No Workbase or Chibi IP was copied.
No dependency installation, account, model, database or external effect is required.

## Run

Node 22+ from the repository root:

```sh
node solutions/exa-internet-butler/server.mjs
```

Open **http://127.0.0.1:4318** (not `localhost`; the server deliberately validates Host).
Use `PORT=4319` if needed. Stop with Ctrl-C. No process is intended to persist after
verification. All product code and fixtures live in this directory.

## Named journey: participant → Exa opportunity preparation

1. Keep the prefilled goal, or select **Use named replay**. Prepare the source packet.
2. Inspect two source cards, exact supporting excerpts and provenance. M298 confirms
   a challenge opportunity in the dated brief, not current eligibility or credits.
   The workshop card replays the catalog clarification, not the slide deck itself.
3. Read the prize-placeholder discrepancy and unknown deadline/eligibility/balance.
   Observations older than seven days gain STALE warnings at packet creation.
4. Use the actionable checklist; check local progress or add a user-supplied step.
5. Edit the sponsor clarification draft. Acknowledge the unresolved terms and approve
   locally. **Approval does NOT execute any real-world task.**
6. Export JSON or copy the complete packet, including source ledger, unresolved
   questions, suggestion/user-action distinction, progress and exact reviewed draft.
   Editing draft/checklist clears approval. Reload clears the in-memory session.

An arbitrary goal gets CONNECTION_NEEDED. It never receives the replay as a pretend
search answer. Slush opportunities beyond this named Junction journey need live
source retrieval and curation. No invented deadlines, contacts or available offers.
Keyboard labels, visible focus, skip link, live status feedback, native controls,
responsive layout and reduced-motion preference are implemented. Browser, mobile,
screen-reader and clipboard behavior are **not yet exercised** in this sandbox.

## Source contract and challenge fit

- Initial/current authenticated main at admission: `672da2be99edff2fa25c0ab2703e6da88061a62f`.
- `partnerEvidenceKey=exa`, `ownedBriefRefs=[M298]`, source snapshot **2026-11-14**.
- M298: <https://hackjunction.app/participate/45/challenges/298>.
  Repository observation `2026-11-14T00:38:47.676043+00:00`; text SHA-256
  `3615f5883fd0c42b671f299885c429d9424916b4309d8c67c336bd5883da2bea`.
- Latest clarification read before previous dated guidance:
  <https://discord.com/channels/1268184974784336004/1564622353198088253/1570911365697372380>.
  Catalog observation date only: 2026-11-14. Original PPTX SHA-256
  `43304dd6b7ae21a0bf3a9a9c87ec379f478736cfb82777dfe650da51e45e707c`;
  bytes not reread by this product. Do not confuse that slide hash with the
  clarification-text hash in the fixture.
- Exact developer provenance: root `docs/challenge-research/current-source-catalog.json`.
  Fixtures are selected official-source replays, never an Exa retrieval receipt.
- M298 asks for useful task completion, clear sources, and live arbitrary judge
  queries. This slice completes local preparation and export; **live-query judging
  readiness is not qualified**. No model or human-outcome evaluation is claimed.

The latest workshop clarification covers `/search`, `/contents`, `/monitors`,
`/agent/runs`, Connect and MCP. We implement one core: Search → Contents only.
Monitors/agent runs/Connect/MCP are roadmap context; no speculative schemas or
background polling. Sponsor offer descriptions are dated claims, not account balance.

## Opt-in live adapter

Only an already-provided `EXA_API_KEY` environment value is read. None was present
in this task; no discovery or redemption was attempted. Do not paste a key in the UI.
Select the live consent checkbox for every request. At most five allowlisted-domain
sources, one request at a time, five attempts per minute, ten-second total deadline,
256 KB per response, 8 KB local request limit, redirect rejection. No arbitrary URL
proxy exists. The only provider transport host is `https://api.exa.ai`.

Schemas checked against [official Search](https://exa.ai/docs/reference/search) and
[Contents](https://exa.ai/docs/reference/get-contents) docs on 14 Nov 2026.
LIVE requires actual successful Search and Contents responses with matching public
source URLs, nonempty text and valid publisher timestamps. Missing dates fail closed.
Empty search, missing key and provider errors never fall back to a fabricated replay.
Live excerpts remain untrusted evidence, never instructions, confirmed eligibility
or an automatically authored plan. This adapter is source-implemented and tested
with fake transport, **not sponsor-qualified**. Returned publication times are
provider-reported; observed times record retrieval, not independent fact verification.

## Focused checks

```sh
node --test solutions/exa-internet-butler/tests/guards.test.mjs
node solutions/exa-internet-butler/tests/http-smoke.mjs
```

The first suite includes held-out authored mutations for invented source/citation,
stale and altered dates, duplicate URL, adversarial source instructions, unsupported
claim, consent, SSRF boundaries, provider shape and bounded response handling.
These are deterministic source/transport guards, not model evals. The HTTP smoke
closes its server in `finally`; it requires permitted loopback binding.
See [PROGRESS.md](PROGRESS.md) for actual results and blockers.

## Longer-term product

2 → 3: qualify an authorized Exa connection with a fresh held-out participant goal,
source dates and human-checked claims; extend beyond the named Exa opportunity.
3 → 4: structured sponsor/Slush opportunity intake, eligibility questions and competing
source comparisons; measure preparation usefulness with consenting participants.
4 → 5: optional mentor/organizer views and explicit, revocable draft handoffs, with
privacy and tenant boundaries owned by the appropriate host.
5 → 6: independently qualify reliability, accessibility, real recipient outcomes and
release. Any future effectful integration requires separate authority and confirmation.
No live service, endorsement, deployment or submission is implied by this roadmap.
