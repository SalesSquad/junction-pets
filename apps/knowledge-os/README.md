# Knowledge OS app

A Junction `apps/` entry for Knowledge OS, Graphify, DAM and Repo Control. The public-safe shell lets the owner select a project/module and an **explicit immutable snapshot**, search source metadata, inspect source revision/observation time/coverage, and follow safe source references. It ships no private documents, owner operational URLs, counts, keys or runtime claims.

## Catalog and local preview

The existing `scripts/build-catalog.mjs` producer copies **only `public/`** into the catalog's generated `/apps/knowledge-os/` directory. The catalog navigation links there and preserves its mount prefix. No new catalog, package workspace, database, scheduler or provider runtime is introduced.

For a static preview from the repository root:

```sh
python3 -m http.server 4189 --bind 127.0.0.1 --directory apps/knowledge-os/public
```

A static preview intentionally cannot read private sources: its missing API is shown as not configured. UI actions never create claims, schedules, grants, merges or index activation.

## Existing private host integration

`host-adapter.mjs` exports `createKnowledgeAppHandler`, with matching TypeScript declarations in `host-adapter.d.mts`. Mount its `/api/context` and `/api/search` handlers under the same app prefix as its static files on the existing **owner-private** host. Inject server-owned functions:

- `authorize(request)` derives `{actorId,audience:'owner-private'}` from the host's trusted authentication; no request-body flag or browser-supplied actor is accepted. Missing authorization fails closed.
- `readProject({actorId,projectId})` reads the existing integration projection. Preserve its separate source and receipt freshness and detached-history semantics.
- `listDatasets({actorId,projectId})` reads the existing Node's explicit source manifest as `{projectId,module,digest,observedAt,coverage}[]`. No "latest" fallback, local scan or guessed digest.
- `searchDataset({actorId,projectId,module,digest,query,limit})` calls the existing authenticated metadata reader. No original corpus or DB is copied here.

The Workspace's existing knowledge reader result shape is retained. The host must bind each reader to the authorized owner and the selected manifest's policy. Unattended Node data access and visitor identity are distinct; do not fabricate an actor from a service token or expose an unauthenticated proxy. Private endpoint URLs and credentials belong in the existing host binding, not this app's public bundle.

The API rejects anonymous access, foreign-origin search, undeclared or mismatched project/module/digest selectors, oversized input and mismatched upstream records. Provider errors return fixed messages. Search results show source evidence and coverage; they do not attest live Graphify execution or a completed cloud migration. Existing Cala/RoundLens source and ownership remain unchanged.

## Focused checks

```sh
node --test apps/knowledge-os/host-adapter.test.mjs
node --check apps/knowledge-os/public/app.mjs
```

Tests use injected source fixtures and prove only adapter boundaries. Actual private host mounting, auth, D1 data, browser runtime and publication require matching live evidence. Root owns PR integration and deployment.
