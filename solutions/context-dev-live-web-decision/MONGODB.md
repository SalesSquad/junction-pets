# SupplyPulse on MongoDB Atlas (optional store)

`watch/store-mongo.mjs` gives SupplyPulse product watches an optional MongoDB Atlas persistence layer.
Without `MONGODB_URI` nothing changes: the local SQLite store stays the default and the solution
remains zero-dependency (the `mongodb` driver is imported dynamically only when it is needed).

## Why Atlas here
- A watch is a natural document: nested schedule and criteria, a latest-evidence summary, and a
  run history that grows over time. Runs and events are stored as documents, queried by watch.
- Watches survive redeploys and move off one laptop, so scheduled watches resume after a restart.
- Indexes: `{status,nextAt}` for due watches, a unique idempotency `token`, `{watchId,startedAt}`
  for history, and a TTL index (`expireAt`) on events (default 90 days; opt-in for runs).
- The Atlas free tier (M0) is enough for the watch and history volume.

## Setup
1. Create a free Atlas cluster, a database user, and allow your server's IP in Network Access.
2. `cd solutions/context-dev-live-web-decision && npm i --no-save mongodb` (installs the driver locally;
   the repo itself keeps zero dependencies)
3. Export `MONGODB_URI` (server env only; never logged, never sent to the browser). Optional:
   `MONGODB_DB` (default `supplypulse`).
4. Start the server as usual (`node server.mjs`). With `MONGODB_URI` set, `server.mjs` opens the Atlas
   store and hands it to the watch service; without it, the local SQLite store is used.

## How it works
`MongoWatchStore extends WatchStore`. The existing interface is synchronous, so the store keeps the
tested in-memory working copy and treats Atlas as the system of record: it hydrates from Atlas on
`openMongoWatchStore()`, and every mutation queues an ordered write-behind upsert flush.
`close()` flushes and then closes the client. Runs left `running` by a dead process are cancelled
on open so budget reservations are released. One server process should own a database at a time;
there is no cross-process locking. Run TTL is off by default because `maxRuns` counts history.

## Tested (no network, no mongod)
`node --test watch/watch.test.mjs watch/store-mongo.test.mjs` runs the store against an in-memory fake
of the collection subset used: documents and indexes written, reopen/rehydrate, crash recovery,
idempotency and revision rules, `WatchService` on the store, error handling that never leaks the
URI, and a missing-driver message. The `mongodb` import shape (`{MongoClient}`) was checked in a temp dir.

## Not yet verified
No live Atlas run has been done. That needs the owner's Atlas account and connection string.
