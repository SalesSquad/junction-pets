---
name: evidence-workflow
description: Build or inspect source-bound DXF/CSV claims, exact citations, local reviews and replayable packets using a pinned Evidence Kit package.
---

# Evidence workflow

Read the package README, capability inventory and qualification limits. This is portable source
guidance, not an installed tool or a permission grant. Follow the user's host/data authority.

1. Identify actual bytes, format/licence, adapter version, units and declared frame.
2. Use a supported adapter. Reject unsupported formats and ambiguity instead of inventing a parser.
3. Run a supported method. Cite only references resolved by the admitted dataset.
4. Separate engine output, evidence basis and human review. A model result is a candidate, hash
   equality is consistency, and a reviewer name is not authenticated independent review.
5. Export source/claim references and review history. On import, check integrity then re-extract
   and rerun against the original bytes before adopting the result as current.
6. Preserve changed results and old review separately. Never silently rebind approval or overwrite
   an output file. Unknown protocol versions require an explicit migration adapter.
7. Qualify the consumer on frozen positives, ambiguity, absent data, mixed units, duplicate IDs and
   stale evidence. State which inputs are synthetic and which real inputs were actually tested.

From the package root: `npm test`, `npm run demo`, `npm run benchmark`,
`node cli.mjs verify packet.json original`, `node cli.mjs replay packet.json original`.
No model call, deployment, public release or privileged action is part of this workflow.

For Stoa-derived capabilities, consult [the reuse map](../../docs/STOA-REUSE.md) before choosing
an engine. Pin the Evidence Kit commit and record adapter/method versions. Use the current DXF
adapter and room method (1.1 or later). Treat parsing errors and abstentions as unresolved evidence.
Historical Stoa benchmark scores, caller-supplied extraction and packet checksums cannot qualify
a downstream capability. Report exact citations and the evidence level separately from review.
