# ProofMatch — sourced skill vocabulary (development only)

**Source:** European Commission ESCO public API, fixed `v1.2.0` request, English and Finnish, collected as a public-only local snapshot. The ESCO classification portal lists a newer 1.2.1 release, but the web API documentation explicitly documents `selectedVersion=v1.2.0`. The requested version is retained in the evidence; the response's own self links do not prove a version.

**What changes:** a bilingual, sourced glossary in the *private synthetic event demo*. It helps an employer and a candidate discuss the meaning of a skill label and explore a European vocabulary URI. It **does not** assert that two skills are equivalent, measure proficiency, change matching scores, rank people, send personal data, make hiring decisions, or claim Espoo sponsor endorsement.

The two fixed public queries are `accessibility` and `software`. The six returned rows are an **illustrative vocabulary**, not an exhaustive classification; the relevance order comes from the external API and is not an independently qualified ranking. No private candidate or event inputs are sent to ESCO. The browser runs entirely from the locally shipped snapshot.

To refresh explicitly (never automatically on page load):
```
node solutions/espoo-proofmatch/esco/refresh.mjs
node --test solutions/espoo-proofmatch/esco/catalog.test.mjs
```
Each response is SHA-256 recorded with the fixed query, the observed time, and original public source URI. This is not a sponsor API connection or an authenticated account. Confirm ESCO reuse terms and source rights before external publication. Existing private Workbase provenance and no-submission restriction still apply.
