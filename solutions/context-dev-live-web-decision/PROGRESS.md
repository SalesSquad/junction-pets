# SupplyPulse — current state (15 November 2026)

Stage: building, submission-ready pending one live news run.

- Live comparison (scrape, 2 pinned retailers): working; live run recorded in
  [LIVE_EVIDENCE.md](LIVE_EVIDENCE.md).
- Product watches (search, map, scrape, answers): working; live run recorded in
  [watch/EVIDENCE.md](watch/EVIDENCE.md).
- New: retailer news via Context.dev `POST /v1/news/search` (`live/news-client.mjs`),
  shown per retailer card and as a verdict note; advisory, ranking unchanged,
  15-minute news TTL, same server-side key handling. Fixture-tested only
  (`live/news.test.mjs`); **no live run yet**.
- Submission note: [SUBMISSION.md](SUBMISSION.md).
- Focused checks: `node --test engine.test.mjs live/live.test.mjs live/news.test.mjs provider/provider.test.mjs watch/watch.test.mjs`
  → 66/66 pass (synthetic transports only).

Next action: owner runs one refresh with `CONTEXT_DEV_API_KEY` set and records
the two news request IDs in LIVE_EVIDENCE.md before submitting.
