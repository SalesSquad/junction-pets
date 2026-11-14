# Shared challenge sources for Codex Claude and ChatGPT

Use [current-source-catalog.json](current-source-catalog.json) for the 14 November source snapshot. It contains all 19 main and 19 technology briefs, 35 partner routes, sponsor clarifications, 26 attachment records and the organizer's 21 video links plus opening PDF. The full private discussion/attachment archive remains in [Junction Space](https://chatgpt.com/space/page_2ed761ae8e8481918373f001743f05fb).

## Start a company task

1. Fetch the repository through your existing authorized GitHub account. Read current main and task/PR HEAD; an old checkout or chat memory is not current source.
2. Read root AGENTS.md, START_HERE.md and docs/AGENT_SOURCE_INDEX.json. Select the assigned agent's `partnerEvidenceKey` and `currentSourceCatalog`.
3. In the catalog, select `partners[]` by `partnerKey`; use its `ownedBriefRefs` to read only the matching `briefs[]` records. Read `latestClarification` before the explicitly dated `previousDatedGuidance`.
4. Follow `materials[]` source-message/archive references only with your own existing access. A GitHub checkout does not grant Pages or Discord access. Report a missing capability instead of copying accounts or assuming another agent's access.
5. Record the source commit and snapshot date in the task handoff. Existing sessions must fetch/reopen these files before continuing. A future agent needs this repository and its normal permissions, not the original ChatGPT conversation.

## Minimal company lookup

```sh
python3 - afterquery <<'PYTHON'
import json, sys
p = json.load(open('docs/challenge-research/current-source-catalog.json'))
r = next(x for x in p['partners'] if x['partnerKey'] == sys.argv[1])
print(json.dumps({'partner': r, 'briefs': [b for b in p['briefs'] if b['brief_ref'] in r['ownedBriefRefs']]}, ensure_ascii=False, indent=2))
PYTHON
```

Both `junction.ignite-next` and `junction.intel` route to the same evidence key; that is shared evidence, not two independent challenges or permission to take another writer's scope. MLH's six briefs remain catalog entries without inventing an MLH runtime agent. XRCC has observations without an owned challenge.

## Changes that affect implementation

- **AfterQuery:** Harbor task layout (`instruction.md`, `task.toml`, `environment/Dockerfile`, `tests/`, `solution/`); verifier score 0–1 in `/logs/verifier/reward.txt`; include a scored Harbor run log. OpenCode harness recommended. **The sponsor withdrew inference credits.** See its linked clarification in the catalog.
- **Cala:** MCP `https://api.cala.ai/mcp/`, own secret-store value in `X-API-KEY`; search/lookup → introspection → retrieval. Missing is not zero; distinguish ISSUER rounds and duplicated filing events.
- **Exa:** 21-slide workshop covers search, contents, monitors, agent runs, Connect and MCP. Its prices/credit offers are dated source statements, not your account's balance.
- **Aalto Humanoid:** first data drop has 20 episodes and 11,720 frames; provider explicitly marks demonstrations suboptimal. It is separate from Beyond the Clinic.
- **Ignite × Intel:** the repository guide and presentation use different judging rubrics. Keep both; no resolving sponsor reply was observed.
- **Hostinger:** dedicated team coupon, KVM 2 for one month, 5000 AI credits and Instant web scraping; verify your own redemption before claiming availability.

## Refresh and access boundaries

The snapshot covers 650 partner messages plus 66 announcement/hardware-help messages. Google and NVIDIA yielded 121 messages each without reaching their oldest history; 33 other channel starts were observed, including empty Qualia. The repo exports sponsor guidance and source links, not raw participant discussions or screenshot OCR. Exact message/attachment evidence remains in the authorized Space archive. It is not a continuous Discord feed. No API-key values, passwords, cookies or session databases belong in this export.

When authorized new evidence arrives, update the current catalog and its source timestamps through a task-owned PR; preserve old snapshots and unrelated agent-index fields. The existing Space sync can consume accepted repository changes; this file does not start a worker or grant repository/Pages access. Do not infer that an already-running agent has reread a newly merged document.
