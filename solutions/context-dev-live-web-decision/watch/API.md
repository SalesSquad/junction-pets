# Product watch interface (implementation contract)

Single-user loopback application, same theme as existing SupplyPulse. New UI
at `/watches/`; existing live comparator remains `/`. Preferences stay in local
SQLite outside Git. Only the wish/query and selected public retailer targets
go to Context.dev. No customer address, browser profile or private account data.

`GET /api/watches` returns `{watches:[watch],runner:{connected,scheduledExecution:"while-server-running",timeZone:"Europe/Helsinki",dailyRequestLimit,dailyRequestsUsed,dailyRequestsReserved}}`.

Definition shape:
```
{name,query,requirements,gtin:"",maxPriceCents:null,quantity:1,
 condition:"new",inStockOnly:true,includeMemberPrices:false,
 merchantIds:["gigantti","proshop","verkkokauppa"],
 schedule:{kind:"manual",timeZone:"Europe/Helsinki"},
 maxRuns:10,expandCatalog:false}
```
`maxPriceCents` is an optional **per-unit item-price** target, never delivered
cost. query max300, requirements max1500, name max100, quantity1–100,
maxRuns1–30. `condition` new/any. `gtin` optional 8/12/13/14 digit exact ID.
Schedules: manual; once `{kind,at:"YYYY-MM-DDTHH:mm",timeZone}`;
daily `{kind,time:"HH:mm",timeZone}`; weekly adds `weekdays:[1,2,3,4,5]`
(ISO Mon1–Sun7); interval adds `minutes:120` (15–10080). No arbitrary cron.

Watch: `{id,revision,definition,status:"active"|"paused"|"archived",
nextRunAt,lastRunAt,lastRunStatus,runCount,lastSummary,createdAt,updatedAt}`.

`POST /api/watches` body `{definition,idempotencyKey:<client UUID>}` →201
`{watch}`. Saving does not execute an immediate search. A schedule takes effect
only after this explicit Save. Manual schedule waits for Run now.

`GET /api/watches/:id` → `{watch,runs:[run],events:[event]}`.
`PATCH /api/watches/:id` body `{revision,definition}` → `{watch}`.
`POST /api/watches/:id/{pause,resume,archive}` body `{revision}` → `{watch}`.
`POST /api/watches/:id/run` body `{}` →202 `{runId}`; long provider work runs
asynchronously. While a run is active UI may poll GET detail every2seconds.
`POST /api/watches/:id/research` body `{}` →202 `{runId}`: explicit one-off
Context Answers research, not run on each schedule. It consumes the same run
and daily-request limits and is an advisory research result.

Run: `{id,status:"running"|"completed"|"failed"|"cancelled",trigger,
startedAt,finishedAt,summary,errorCode,requestsUsed,creditsConsumed}`.
Summary: `{offers:[offer],changes:[change],research:null|{answer,sources},
headline,endpointUsage:[{operation,requestId}],warnings:[]}`.
Offer: `{id,title,url,merchantId,merchantName,gtin,priceCents,memberPriceCents,
selectedPriceCents,itemSubtotalCents,shippingFromCents,stockStatus,matchStatus,
meetsTarget:boolean,needsReview:boolean,evidence:[{field,quote}],warnings:[]}`.
Unknown values are null. Changes: `{type:"new"|"price_drop"|"price_rise"|
"availability"|"target_reached",offerId,title,before,after,url}`.
Event: `{id,runId,createdAt,type,title,detail}`; in-app inbox only, no email or
external message. Research sources and offer links must pass retailer allowlist.

Every mutating browser call requires same-origin Origin, JSON Content-Type and
`X-SupplyPulse-Refresh: 1`. Error response `{error:<fixed code>}`. 409 for
revision conflicts/busy, 429 for quotas, 503 for missing server connection.
No provider credentials or raw exception text in a response. New state routes
never expose the SQLite file or allow browser-selected filesystem paths.

Scheduled requests execute only while server/Mac is running. Overdue schedules
run at most once after wake, then move to the next future slot; no catch-up
burst. DST nonexistent local times are skipped, ambiguous fall-back slots run
once. Pausing fences subsequent calls; an already submitted call may cost
credits. No recurring real watch is created during development qualification.
