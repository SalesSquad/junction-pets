# Companion browser apps

This catalog maps Junction pets to runnable, browser-only slices of their
existing solution workspaces. It is the source of truth for the app names,
entry points and files that Chibi packages; a catalog entry is not itself a
public deployment, provider connection or claim of competition readiness.
One pet may have more than one app; each has its own directory and entry point.

To make a bundle for Chibi, check out an exact Junction commit and run:

```sh
node apps/companion-browser-apps/export.mjs /tmp/new-junction-app-bundle
```

The output directory must not exist and must be outside this repository. It
contains `catalog.json`, an `index.html` that links every app, and `apps/`; the consumer records the exact Junction
commit and publishes the bundle under its own access policy. Only the listed
browser files and synthetic fixtures are copied. Adaptations make the original
apps' absolute paths work under an app directory. ProofMatch's localhost status
text is adjusted; Spread can load its existing synthetic example; Meta's
optional observation endpoints stay scoped to the app and remain unavailable
without its service. Recovery Compass and Traffic Forensics have a no-network
content policy in the embedded page. Adaptations fail if their source anchors
change. ProofMatch's service worker is scoped to its own app directory. The
original localhost servers and their response headers are not included.

RoundLens's embedded client has changed paths, so its downloaded artifact uses
`roundlens.shortlist.embedded.v1`: `upstreamProductSourceDigest` names the
original package, and `embeddedClientDigest` identifies the adapted client.
The latter hashes a UTF-8 manifest of sorted paths `core.mjs`, `fixture.mjs`,
`public/app.mjs`, `public/index.html`, `public/style.css`; each entry is path,
NUL, lowercase SHA-256 of file bytes, then LF. `source-meta.mjs` contains the
result but is excluded from the digest to avoid recursion.

When adding a pet, first verify a browser-only entry point and include every
required local asset, with no secrets or private data. Server-backed solutions
need their actual runtime and deployment before they can be listed as runnable
here. Never infer an app URL from a repository, company website or localhost
port. Keep synthetic/demo boundaries visible and retain upstream provenance.
