# SupplyPulse / Live Web Decision Room

Compare **one Logitech MX Master 3S Bluetooth Edition (910-007501,
EAN 5099206129382)** at Gigantti and Proshop using Context.dev's live scrape
endpoint. The default page shows ordinary listed EUR item prices, a separate
member price, availability, retrieval time, provider request ID, evidence hash
and meaningful changes since the previous refresh. Unknown shipping and arrival
stay unknown. The result is a human-review shortlist, **not a delivered-cost
quote, stock reservation or purchase**.

## Run (Node 22.13+, no dependencies)

```sh
node solutions/context-dev-live-web-decision/server.mjs
# http://127.0.0.1:4173/ — real-source comparison
# http://127.0.0.1:4173/watches/ — configurable product watches
# http://127.0.0.1:4173/replay — original fictional lamp controls
```

For independent refresh, supply `CONTEXT_DEV_API_KEY` to the **server process**
through your existing host secret store or an ignored local environment file;
never paste it into the web page, source or a command that prints it. Example:

```sh
node --env-file=/absolute/private/path/supplypulse.env \
  solutions/context-dev-live-web-decision/server.mjs
```

The file contains `CONTEXT_DEV_API_KEY=<your key>`; keep it outside this repo,
mode 0600. `PORT` selects a different loopback port. Nothing is deployed.
The server binds only 127.0.0.1, never sends a key to the browser, accepts no
caller-provided source URL and sends credentials only to Context.dev's fixed
HTTPS endpoint. Click **Refresh both sources** to make exactly two fresh
scrape requests (`maxAgeMs: 0` at the request root). No retries or polling.
Concurrent refreshes and refreshes within ten seconds are refused; a process
allows ten refreshes maximum. Credit exhaustion stops further refreshes until
restart; check provider balance first. Existing Context.dev credits/identity
are separate from a source build or an installed chat connector.

## Retailer news (second Context.dev endpoint)

Each refresh also calls Context.dev **News Search**
(`POST https://api.context.dev/v1/news/search`, documented at
<https://docs.context.dev/api-reference/news/search.md> and
<https://docs.context.dev/news/overview.md>) once per retailer, using an
`entity`/`domain` search for the pinned domains `gigantti.fi` and `proshop.fi`,
newest first, last 30 days, at most 5 articles. Headlines are scanned for
retailer-risk terms (insolvency/konkurssi, layoffs/muutosneuvottelut, recall,
data breach/tietomurto, strike, store closure, delivery problems, regulator
action). Flagged headlines appear on the retailer card and as a verdict note
("read before ordering"); they **never change the ordinary-price ranking**.
News has its own 15-minute TTL, so price refreshes inside that window do not
re-buy headlines (1 credit per 10 results; unknown company 404 costs 1 and is
shown as "no coverage"). Same key handling as scrape: server-side
`CONTEXT_DEV_API_KEY` only, fixed host, no caller-supplied domain or query.
Without a key the page shows the saved capture and "news not retrieved".
Only reduced headline metadata is kept (no authors, images or key metadata).
News Search has a recorded live run (LIVE_EVIDENCE.md, 15 Nov 2026); Context.dev has little news coverage for these two retailers.

## Product watches

At **Product watches**, describe the product and your requirements, optionally
pin an EAN/GTIN and item-price target, and select retailers. Choose a one-off
local date/time, daily time, weekdays, interval or manual searches, with your
time zone and maximum run count. Save activates the chosen schedule; **Run now**
starts a separate immediate search. Pause, edit, resume and recoverable archive
controls stop subsequent calls from cancelled runs.

Context.dev searches the selected retailers, optionally maps one retailer's
catalogue, then retrieves fresh product pages with structured product and JSON
extraction. **Research alternatives** explicitly runs a separate Context Answers
request. Results include source evidence, changes, an in-app update inbox and a
downloadable memo. Unknown stock, delivery, identity and detailed requirements
remain review items. A first observation is not a price drop.

Schedules run **only while the server and its host are running**. SQLite keeps
definitions, history and request limits across restarts; wake-up runs at most
one missed slot before moving to future times. No hosted monitor, system daemon,
email/push notification or purchase is provisioned. See [watch/README.md](watch/README.md)
and [watch/API.md](watch/API.md) for limits, storage and API contracts.

## Real-source evidence and capture mode

`live/capture.json` is generated from two actual Context.dev MCP responses,
not invented offers. It contains only selected public product/offer data and
retrieval provenance, without reviews, customer data, credentials or account
credit details. It is labelled **saved MCP capture**, not a current server
connection. Once five minutes old it is historical and no winner is emitted.
Fresh server responses use the same `capturePublic → normalize → compare`
path. A successful API envelope alone is insufficient: each requested format
must succeed, cache age must be zero, the exact source/GTIN/MPN must match and
both ordinary EUR prices must be unambiguous. A failed source withholds the
comparison. Hashes bind local content; they are not provider signatures.

An already authorized agent may import new MCP response envelopes locally
without transferring its connector credential. Each envelope is
`{sourceId,startedAt,receivedAt,transport:"CONTEXT_MCP_CAPTURE",body:<provider response>}`:

```sh
node solutions/context-dev-live-web-decision/live/import-capture.mjs \
  /private/path/gigantti.json /private/path/proshop.json /private/path/new-capture.json
SUPPLYPULSE_CAPTURE_FILE=/private/path/new-capture.json \
  node solutions/context-dev-live-web-decision/server.mjs
```

Import refuses an existing output file. Do not relabel a fixture as an actual
provider response. Imports are host assertions, not authenticated proof of
provider execution. Source URLs are pinned in `live/sources.mjs`; this is not
a general-purpose URL proxy or an automated shopping agent. See [LIVE.md](LIVE.md)
for boundaries and [LIVE_EVIDENCE.md](LIVE_EVIDENCE.md) for executed evidence.

## Meaningful change and failure behavior

- Compare the exact manufacturer part and EAN, not a similar product name.
- Rank ordinary item price; member-only discounts do not silently win.
- Keep shipping starting rates separate; no unknown value becomes zero.
- Refresh both sources and compare price, membership, stock state and shipping.
- Expired, missing, mismatched, failed or conflicting evidence withholds a winner.
- Never claim a live market change if two real observations are unchanged.

The original 40-lamp synthetic engine, adversarial scenarios, memo and dormant
SDK seam remain available at `/replay` and their original CLI paths. The older
[VERIFICATION.md](VERIFICATION.md) describes that historical milestone, not the
new live transport. PR204's separate host-injected confidence/40-lamp contract
remains on its original branch; its useful boundaries informed this provider-
verified root-response adapter without inventing unavailable fields.

## Focused checks

```sh
node --test solutions/context-dev-live-web-decision/live/live.test.mjs \
  solutions/context-dev-live-web-decision/live/news.test.mjs \
  solutions/context-dev-live-web-decision/engine.test.mjs \
  solutions/context-dev-live-web-decision/watch/watch.test.mjs
```

These cover price/identity/freshness, source failure, credential isolation,
request size/timeout, concurrency and same-origin HTTP. They require loopback
permission. Real provider and rendered-browser evidence are recorded separately.
M332 expects reactions to live web data; T44 requires a real Context.dev endpoint
in the core flow and a GitHub repository/demo plus endpoint explanation.
Source integration, local live execution, public release and official submission
remain separate outcomes. Product watches use the local application scheduler;
no provider-hosted monitor or supplier action is included.
