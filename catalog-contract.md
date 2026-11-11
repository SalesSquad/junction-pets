# Junction pet package contract v1

Work ID: JUNCTION-PETS-20261111. The separate source repository is
SalesSquad/junction-pets. The Chibi host remains the only authority for accounts,
adoptions, grants, conversation persistence and provider execution.

Each `pets/<company-slug>/pet.json` has this shape:

```json
{
  "schemaVersion": 1,
  "id": "junction.mariadb",
  "slug": "junction-mariadb",
  "version": "0.1.0",
  "agentName": "MariaDB",
  "displayName": "MariaDB companion",
  "company": {"name":"MariaDB","slug":"mariadb","role":"challenge","website":"https://mariadb.com/"},
  "tagline": "One clear, company-specific useful job.",
  "introduction": "A plain-language description of the companion.",
  "welcome": "A useful first question with no unsupported product promise.",
  "accent": "#0b7189",
  "artIndex": 7,
  "capabilities": [{"id":"query-review","title":"Review a query","description":"Explain a user-supplied query and propose a measured check.","kind":"guidance","inputs":["redacted SQL"],"outputs":["review and verification plan"],"requiresConnection":false},{"id":"plan-review","title":"Review an EXPLAIN plan","description":"Explain supplied query-plan fields and identify the next measurement.","kind":"analysis","inputs":["redacted EXPLAIN output"],"outputs":["interpretation and measurement plan"],"requiresConnection":false}],
  "starterPrompts": ["One company-specific starting prompt", "A second one", "A third one"],
  "sources": [{"id":"official-docs","title":"Official documentation","url":"https://mariadb.com/docs/","publisher":"MariaDB","checkedAt":"2026-11-11","summary":"An original short summary of what this source supports."}],
  "sourceEvidence": {"roster":"Junction Space / observed partner list","roleVerified":false,"notes":"Archived role observation; no invented unpublished challenge brief."},
  "availability": {"content":"ready","runtime":"chibi-host-required","companyEndorsed":false}
}
```

Allowed company roles: `challenge`, `technology`, `main`, `collaborator`.
Allowed capability kinds: `guidance`, `analysis`, `planning`, `connection-required`.
IDs/slugs use lowercase ASCII with hyphens/dots only. `artIndex` is stable and
unique across the 34-package roster. Source URLs must be official HTTPS URLs.
No secret, access token, invitation bearer or per-user information belongs here.

Each package also owns `AGENTS.md`, `STORY.md`, and `evals.json`. Evals have
`schemaVersion:1`, `petId`, and `cases` of `{id,prompt,mustInclude,mustNotClaim}`.
AGENTS contains the full company-specific system guidance, scope, first-turn
behavior, useful workflows, evidence and uncertainty rules, connection boundaries,
privacy and refusal/recovery behavior. STORY is English first with concise Finnish
summary, company use cases, how the user can interact, and honest current limits.

No pet is an official company representative. Company references identify the
subject of an independently created companion. An event QR is a public routing
URL to the canonical Chibi product page; it is never a bearer grant or login token.

Writer ownership: company-content worker owns `pets/` and
`evidence/company-roster.json`; UI worker owns `apps/catalog/` and `design/`;
coordinator owns schemas, shared tooling, package manifests, generated outputs,
release bundles, adapters and integration. Do not alter another writer's files.
