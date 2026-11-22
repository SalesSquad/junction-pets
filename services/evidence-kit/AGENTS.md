# Evidence Kit

Use [Stoa reuse map](docs/STOA-REUSE.md) and [Evidence workflow](skills/evidence-workflow/SKILL.md)
before extending or integrating this package. Record the exact version, supported inputs and
evidence level. Keep source bytes, extraction, claim and review bound to one another. Report
ambiguity, unsupported inputs and missing evidence as unresolved. Treat historical packets as
history until replay succeeds against the original bytes with a trusted adapter and method.

Run `npm test` and `npm run benchmark:check` for runtime changes. Keep previous benchmark
receipts when qualifying a changed runtime. Synthetic passes establish the covered mechanics.
Downstream use with real documents requires qualification on representative documents.
