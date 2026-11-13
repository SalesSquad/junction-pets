# Source-only RED/GREEN record

Work: `junction.city-of-espoo.capability-proof`; logical owner:
`junction-dev-city-of-espoo`; native author: `/root/junction_dev_city_of_espoo`.
Baseline source: `602bdaf46a704a694584c6448083229bf74f3f15`, tree
`a49cd8009a86b9741fa71d8bd65abee72dda03f6`. The isolated worktree started clean.

Runner was the existing attached portable cloud executor, Node `24.22.1`, npm
`11.9.0`, not a newly launched Codex Pro task or a per-company provider receipt.
The code tree was materialized; two unavailable binary assets were preserved in
the index with `skip-worktree`: `apps/catalog/public/assets/company-mascots.png`
and `design/catalog-concept.png`. Build success is not browser/artwork acceptance.

Baseline gates passed: `npm ci --ignore-scripts --offline`, `plugins:check`,
`validate` (34 packages / 204 authored evals), `npm test` (342/342), `npm run build`,
`node scripts/ops-build-status.mjs`, and `git diff --check`. Ops remained advisory:
zero executed model evals, zero active/published/Cloud-qualified companions.

`targeted-red.txt` preserves the first `node --test tests/pet-city-of-espoo.test.mjs`
run after writing tests and the fixture, before implementation. It failed with
`ERR_MODULE_NOT_FOUND`; this is one module-load failure, **not** 18 individually
executed failures. `targeted-green.txt` records all 18 tests passing after the
checker was implemented. These are pre-commit, file-hash-bound observations.
Final committed-HEAD verification belongs in the task PR; these files are never
rewritten to imply a later HEAD was tested.

| Evidence | SHA-256 |
| --- | --- |
| `targeted-red.txt` | `9262c4a9e40d3199671085172aa7f082ff827e800cb2f9d6743c64c0c51dd3ae` |
| `targeted-green.txt` | `a9eba56276231debd3e8cc00e5eec4e9b68d002049efd34e14ec8b871530d1e3` |
| Targeted tests | `affab3950751c50078de75ce3a5ef8da02db3f8928983f0e6a33e79f9512d647` |
| Checker at GREEN | `6606a65daedffed3bb26781872a6d854bfcb0dc774ffa799586ffbf38c855fd7` |
| Invented example | `c33d632bb6d831ffef0ee1b16f7da407a4a30521ce876216c4a093335bf2f6c1` |
| Unchanged six eval definitions | `8edecc83253041eef8c1605d749b053289242d518aec904bb87f11259ea28a74` |

Generated plugin changes were produced by the unchanged `buildPlugin` export in
`scripts/build-pet-plugins.mjs`, writing only the three City of Espoo outputs.
No model invocation, source fetch, real resident data, service availability,
host/recipient journey, accessibility certification, paid executor, company
endorsement, challenge rules, merge or deployment was introduced or verified.

Next bounded company work: independent Finnish/English content and exact-source
review. A real-source adapter would need separately scoped current evidence and
privacy review; the invented source contract is deliberately not that adapter.
