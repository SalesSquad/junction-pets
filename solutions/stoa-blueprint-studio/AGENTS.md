# Stoa Atlas local worker rules

- Ownership: only `solutions/stoa-blueprint-studio/**`. Shared root and other company slices belong to integration owners.
- The real sponsor drawing is **never copied to git**, published, cached in cloud or used commercially. Read the per-source licence; keep Swiss Dwellings CC BY 4.0 credit. Repo demo must remain clearly labeled synthetic and unverified.
- Evidence integrity: answers must have source coordinates and entity IDs. Room area is accepted only with unique room number, unique closed polygon, unique area annotation, known DXF units and within 2% arithmetic tolerance.
- Unknown layer conventions, missing units, prompt injection, labels with multiple matching regions, or unsupported categories require deterministic abstention, not unsupported guesses.
- Preserve CLI independence, localhost defaults and capped memory/import size. No external inference or spending without fresh authorization.
- Focus targeted tests around modified parsing/geometry/answer modes; optional sponsor sample uses locally downloaded exact SHA-256 only. No blanket full-suite loop or test relaxation to pass.
- Product workspace metadata may be reconciled only by the product integrator; source commit must be recorded and reviewed before PR handoff. No merge/deploy/release authority is implied.
