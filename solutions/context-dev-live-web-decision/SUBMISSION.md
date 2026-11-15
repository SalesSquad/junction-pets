# SupplyPulse — submission note (Context.dev)

**Problem.** Buyers still check supplier pages by hand and read the news to
catch supplier risk. SupplyPulse turns the live web into a buying decision for
one exact product (Logitech MX Master 3S, EAN 5099206129382) at two Finnish
retailers: fresh prices with identity checks, a shortlist that refuses on
stale or conflicting evidence, and retailer news to read before ordering.
Product watches extend this to any product on a schedule. Human review only;
nothing is purchased.

**Demo.**
1. `node --env-file=/private/supplypulse.env solutions/context-dev-live-web-decision/server.mjs`
   (env file holds `CONTEXT_DEV_API_KEY`; without it the page replays the saved capture).
2. Open `http://127.0.0.1:4173/`, click **Refresh both sources**: two fresh
   scrapes + two news searches. Cards show price, member price, stock,
   request IDs and a **Retailer news** block; the verdict adds a "read before
   ordering" note when a headline matches a risk term.
3. Refresh again after 10 s: changes since the last refresh are listed; news is
   not re-bought within 15 min.
4. **Download sourcing memo** for the evidence trail.
5. `/watches/`: create a watch, **Run now**, optionally **Research alternatives**.

**Context.dev endpoints used and why.**

| Endpoint | Why | Live run? |
|---|---|---|
| `POST /v1/web/scrape` (markdown + JSON-LD, `maxAgeMs:0`) | Core flow: fresh retailer product pages; price/identity come from publisher JSON-LD | **Yes**, recorded in [LIVE_EVIDENCE.md](LIVE_EVIDENCE.md) and [watch/EVIDENCE.md](watch/EVIDENCE.md) |
| `POST /v1/news/search` (entity by domain, newest, 30 days, limit 5) | Retailer-risk signal next to each offer (insolvency, layoffs, recall, breach, strike, closure, delivery, regulator action). Advisory: never changes the price ranking | **Yes**, 15 Nov 2026 08:29 EET, see [LIVE_EVIDENCE.md](LIVE_EVIDENCE.md#retailer-news-live-run-15-november-2026): Gigantti returned no articles in the 30-day window, Proshop is not a known company (404 → "no news coverage") |
| `POST /v1/web/search` | Watches: find candidate product pages at selected retailers | Yes, [watch/EVIDENCE.md](watch/EVIDENCE.md) |
| `GET /v1/web/urls` (map) | Watches: optional catalogue expansion for one retailer | Yes, [watch/EVIDENCE.md](watch/EVIDENCE.md) |
| `POST /v1/web/answers` | Watches: explicit "Research alternatives" (advisory) | Yes, [watch/EVIDENCE.md](watch/EVIDENCE.md) |

News contract source: <https://docs.context.dev/api-reference/news/search.md>,
<https://docs.context.dev/news/overview.md>,
<https://docs.context.dev/news/filter-and-sort.md>, costs at
<https://docs.context.dev/account/credits.md>.

**What the live run showed.** News Search works end to end, but Context.dev has
almost no coverage for these two Finnish retailers, so in the demo the news
blocks will say "no recent news" (Gigantti) and "no news coverage" (Proshop).
Present it as the risk check that stays quiet when there is nothing to read,
or pin a retailer with coverage if you want a flagged headline on stage.
The live key is limited to **2 concurrent requests** (`x-ratelimit-mode:
concurrency`) and had about 900 credits left, so SupplyPulse now runs the two
scrapes first and the news calls after them; keep demo refreshes few.

**Boundaries.** Key is server-side only (`CONTEXT_DEV_API_KEY`), fixed HTTPS
host, pinned sources/domains, no caller URLs, single-flight refresh, 10 s
cooldown, 10 refreshes per process, credit exhaustion stops refreshes.
