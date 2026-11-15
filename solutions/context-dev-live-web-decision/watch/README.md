# SupplyPulse product watches

Open `/watches/` from the existing Node server. Node 22.13+ is required for
built-in SQLite; no npm dependencies or hosted infrastructure are added.

## Configure a watch

- Product name/search, optional detailed wishes and exact EAN/GTIN.
- Optional EUR unit-price ceiling, quantity, new/any condition, in-stock filter
  and explicit opt-in to member prices for which you are eligible.
- Gigantti, Proshop and/or Verkkokauppa.com. Only approved HTTPS product paths
  are fetched. General web URLs and arbitrary domains are not accepted.
- Manual, once at a local date/time, daily, selected weekdays, or an interval
  from 15 minutes to seven days. Choose an IANA time zone and 1–30 total runs.

Saving schedules future work without an immediate provider call. Run now and
Research alternatives are explicit one-off actions and both count toward the
watch's limit. Editing cancels the running result and applies the new criteria;
product changes start a new comparison baseline. Pause/resume retains history,
and archived watches can be restored. Raise an exhausted run limit before
resuming. In-app notifications, history and a text memo show the outcome.

## Context.dev in the core flow

| Capability | Use |
| --- | --- |
| Web Search `/web/search` | Discover product URLs within selected retailers. |
| Map `/web/urls` | Optional catalogue expansion on one retailer per run. |
| Scrape `/web/scrape` | Fresh Markdown, structured product and schema-guided JSON extraction in one call per page. Product AI fallback is disabled. |
| Answers `/web/answers` | Explicit fast-mode research with sources and structured advisory output. |

Search results are discovery hints; prices come from retrieved product pages.
Each successful endpoint records its request ID. Public typed retailer product
data takes precedence; quoted text extraction, detailed wishes and unconfirmed
quantity require human review. An exact identifier distinguishes model variants.
Member prices stay separate, missing costs stay unknown, and item subtotal is
never presented as delivered total. Research does not silently change filters
or activate additional watches. Its claims remain advisory.

These capabilities serve product discovery and comparison. Context's company,
people, brand and news datasets are not queried without a relevant product need.
Provider-hosted monitors are not created: documented interval scheduling does
not supply this feature's local calendar/time-zone controls, and the app does
not request new monitor-management permissions.

## Scheduling, limits and recovery

The host and server must remain running. There is no OS wake-up, background
installation or cloud executor. Restart/wake-up consumes one overdue slot,
then schedules the next future slot; it never replays a backlog. A paused watch
resumes at the next future time. Nonexistent daylight-saving local times are
skipped; an ambiguous local time runs once. Weekly scheduling spans DST gaps.

Each search reserves at most six HTTP requests: one search, optionally one map,
and up to four page retrievals. Research reserves one Answers request (which
has a different provider credit cost). There are at most 30 watches, 30 runs
per watch and 40 watch-provider HTTP submissions per UTC day. These are request
limits, not a credit/currency guarantee. Original comparison refresh limits
remain separate. Provider-reported credits are shown only when supplied; no
estimated balance or zero-cost claim is made.

SQLite transactions reserve capacity before a run and consume it immediately
before each submission, including failed requests. No implicit retries occur.
Cancelled work cannot publish a late result or submit another request. Work
crossing UTC midnight stops rather than charging the wrong day's cap. Provider
authentication/credit failures pause schedules until explicit recovery.
After a hard process crash, a running row remains visible and fenced; use
Pause then Resume to recover it. Other due watches can still run. History is
retained; API reads return the latest 30 runs and 100 events per watch.

## Local state and trust boundaries

The server binds to loopback. Mutations require same-origin JSON and the
application request header. API credentials stay in the host environment and
are sent only to Context.dev's fixed HTTPS endpoint; redirects are refused.
Provider responses have size/time limits and errors exposed to the UI use
fixed codes. See [API.md](API.md).

On macOS, state is under `~/Library/Application Support/SupplyPulse/`; on other
hosts it uses the XDG state directory. `SUPPLYPULSE_STATE_DIR` can select a
trusted host-side directory. Keep this database, its journal and secrets out of
Git and cloud-synced source folders. New state folders are private and the DB
file uses mode 0600. Product wishes and public source extracts remain local;
queries/requirements are transmitted to Context.dev when a run is submitted.
Do not include personal or confidential information in product descriptions.

No purchase, reservation, supplier message, webhook or external notification
is sent. This single-owner local app is not a multi-tenant hosted service.
