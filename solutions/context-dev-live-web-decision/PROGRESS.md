# SupplyPulse — current state (15 November 2026)

Stage: building, submission-ready pending one live news run.

- Live comparison (scrape, 2 pinned retailers): working; live run recorded in
  [LIVE_EVIDENCE.md](LIVE_EVIDENCE.md).
- Product watches (search, map, scrape, answers): working; live run recorded in
  [watch/EVIDENCE.md](watch/EVIDENCE.md).
- New: retailer news via Context.dev `POST /v1/news/search` (`live/news-client.mjs`),
  shown per retailer card and as a verdict note; advisory, ranking unchanged,
  15-minute news TTL, same server-side key handling. Live run 15 Nov 2026 recorded in
  LIVE_EVIDENCE.md (works; little provider coverage for these retailers). The
  live run found a concurrency bug (key limited to 2 in-flight requests), now fixed and tested.
- Optional MongoDB store for watches: verified against a real MongoDB 8.3 server with a live run (MONGODB.md).
- Submission note: [SUBMISSION.md](SUBMISSION.md).
- Focused checks: `node --test engine.test.mjs live/live.test.mjs live/news.test.mjs provider/provider.test.mjs watch/watch.test.mjs`
  plus `watch/store-mongo.test.mjs` → 74/74 pass (synthetic transports only).

Next action: a live MongoDB Atlas run needs the owner's Atlas account; otherwise ready to demo.
