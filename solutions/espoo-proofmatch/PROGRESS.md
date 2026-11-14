# J26-PF-ESPOO-20261114-A

- Exact base: `bb1f50908e05ada32e947abff86ac5e31e82e22d`.
- Branch: `codex/j26-product-espoo-matcher-20261114`; clean baseline confirmed.
- Exclusive writer scope: `solutions/espoo-proofmatch/**`. No companion, shared
  CLI, root manifest/tests, existing solution, Tieto L9 or Actions changes.
- Implemented: runnable static role → ranking → source cards → shared UTC slot →
  two simulated consent fields → local intro DRAFT flow; synthetic benchmark;
  deterministic core; local server and offline app-shell fallback.
- Manifest stage is declared `idea`; capability use is `planned`, not execution.
- Source discovery: pinned company research and official brief snapshot read.
  Authenticated GitHub main/PR #64 refresh failed (`error connecting to
  api.github.com`); official challenge page refresh was inaccessible. The supplied
  source and manifest shape govern this isolated slice; no fresh remote state is
  asserted by the writing sandbox. Coordinator independently verified GitHub
  main `bb1f50908e05ada32e947abff86ac5e31e82e22d` via authenticated
  remote before admission and checked PR #64 still open via GitHub connector.
  newcomp recruitment search returned no reusable component.
- Verification on the local Mac mini restricted executor, Node v26.13.0,
  14 November 2026: `node --test solutions/espoo-proofmatch/matcher.test.mjs`
  **18 passed, 0 failed**. `node solutions/espoo-proofmatch/benchmark.mjs` printed
  evidence **2/2** versus keyword **0/2**; repair=Mira 94, co-design=Jules 96,
  baseline=Devon with 9 hits for each role. These results cover the authored
  product bytes based on the exact base above; final local commit identifies
  those bytes. They do not qualify future changes.
- HTTP smoke **PASS on the authorized Mac Mini RDC host** (14 November 2026,
  about 03:39 EET, Node v26.13.0): bounded localhost server `PORT=4191`,
  exact GET `/`, `/app.mjs`, `/matcher.mjs`, `/styles.css` and `/sw.js`
  each returned HTTP 200 with expected media types; a path traversal attempt
  `/../../.git/config` returned HTTP 404 when sent without URL normalization.
  The task's server was stopped by its EXIT trap. In contrast, the separate
  Codex sandbox returned `listen EPERM` for port 4173 and could not test HTTP
  from inside that restricted executor. Browser rendering, device accessibility,
  service-worker offline reload and real participants remain **unverified**.
- JS syntax checks passed for `app.mjs`, `sw.js` and `serve.mjs`. Server listen
  failures now produce a concise error rather than an unhandled exception.
- Local commit **BLOCKED**: staging only the owned folder returned
  `Unable to create .../.git/index.lock: Operation not permitted`. The runtime
  exposes `.git` read-only. No new commit exists; HEAD remains the exact base
  above. All 14 product files remain in the assigned checkout, untracked.
  No permissions workaround, push or rescue upload was attempted.
- No live source, live city data, real participants, real consent, external
  verification, deployed runtime, production result or partner endorsement.
- Next owner/task: coordinator reviews the product files, runs the documented
  HTTP/browser smoke in an executor with loopback access, and stages/commits only
  this folder on the existing task branch in an executor with Git write access;
  coordinator handles remote integration. Any later live trial needs authorized participants,
  source rights and authenticated consent/scheduling boundaries.
- Deliberately local-only: no push, PR, merge, publish or deployment. No iCloud
  report is created; these files are product source in the assigned checkout.
