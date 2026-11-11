# Independent review receipt

Work: JUNCTION-PETS-20261111. Read-only native sol specialist; coordinator stores this receipt. No external request or publication occurred in the reproductions.

## Original findings and repair

1. **P2 — incomplete Maker identity binding.** The original `createMakerDraft` checked only the manifest digest. The reviewer changed `makerRequest.slug` from `junction-mariadb` to `junction-other` and `taxonomy.product_type` to `agent`; the injected recording transport was still called while the reported pet identity stayed MariaDB. The repair binds the complete request plus pet, package and manifest identities, rejects unexpected request keys and snapshots the candidate before the one transport call. Regression tests reject slug, taxonomy, tag, manifest, pet, package and extra-field mutations before transport. Re-review: closed.
2. **P2 — inconsistent verification timestamp checks.** Original UI used a truthy verification string; malformed or future dates could enable a recipient CTA. Both clients now require a string, a valid parsed date and a timestamp no later than now, in addition to verified host status and the exact published slug. A follow-up numeric `1` coercion issue in the shared helper was also fixed and tested. Re-review: closed.

The exporter deliberately returns only `draft-response-received` with raw unverified response bytes and `published:false`. It has no caller that promotes the response to published or runtime-ready. A thrown transport remains `unknown`, with no automatic retry. Hashes prove integrity, not authenticated host authority.

## Chibi review

Canonical base: `243c272c13668418decd67af3a9b88566927d5ee`.

Eight-file integration patch SHA-256: `485ff22928f99f0fb40efc9e3aebdecec8fbd6622c3c985fb832b14d1058b10a`.

The original five-file owned-adoption handoff was independently reviewed for exact-ID selection, missing/foreign IDs, later-page lookup, principal/profile/generation retirement, pack snapshots, effect cleanup and reuse of existing activation/conversation components. No blocking introduced defect was found. Those five files are unchanged in the integration patch.

The reviewer separately examined the localized collection component, both Marketplace branches and the actual-source component tests. No blocking finding or false publication/adoption/runtime claim was found. `/junction/index.html` is public collection discovery only.

Independent execution observed 11/11 monorepo contract tests, 6/6 owned-selector tests, 2/2 collection component tests and Chibi TypeScript checks passing. These are distinct suites, not a combined hosted qualification. The implementation worker also ran the 53-test focused Chibi suite (45 pre-existing + 8 added).

Exact reviewed Chibi hashes:

| File | SHA-256 |
| --- | --- |
| `web/features/den.tsx` | `4c4f48e0429b71582ec70ac275c64456b6c1f47413cde119bdfb17a9541d0ef8` |
| `web/features/first-adoption-consumer.tsx` | `7c8f65c6ac13c4e81597e6f92447e8f04d23608e407fe859ab81c88c04292485` |
| `web/lib/owned-adoption-selector.mjs` | `5c424c786aadf11bc2152269af52260a9674728357322bf34365c41695ea6dd2` |
| `web/lib/owned-adoption-selector.d.mts` | `8e028b0151de737f2f6a9197b6a3474f07e6ad66adaebc58f71e3beed1665b3b` |
| `tests/sites/owned-adoption-selector.test.mjs` | `e84e1ac0c25291bc31e69c20109380747b94a2713feb5fbda808168ad0c40bfc` |
| `web/features/junction-collection.tsx` | `e4d46e8cc12c3c8df1943d9f2956a7b6c7ca07e30b844f41b1f330cd436a2109` |
| `web/features/market.tsx` | `36609591b04cdfd4592948754af9d36676d3ed46fac486732f3bccbf298e53e9` |
| `tests/sites/junction-collection.test.mjs` | `f95f43525bd979bec6232793b48d65a7c165681d8840b40184db67ec76086a6d` |

Review limits: source transfer was not itself a canonical Git checkout. Reviewed file hashes and patch bind the findings. Deployed static routing, actual authentication, owned entitlements, live provider response and physical mobile browsers remain separate acceptance requirements. Model behavior cases were authored but not executed.
