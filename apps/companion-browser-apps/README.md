# Companion browser apps

This catalog maps Junction pets to runnable, browser-only slices of their
existing solution workspaces. It is the source of truth for the app names,
entry points and files that Chibi packages; a catalog entry is not itself a
public deployment, provider connection or claim of competition readiness.

To make a bundle for Chibi, check out an exact Junction commit and run:

```sh
node apps/companion-browser-apps/export.mjs /tmp/new-junction-app-bundle
```

The output directory must not exist and must be outside this repository. It
contains `catalog.json` and `apps/`; the consumer records the exact Junction
commit and publishes the bundle under its own access policy. Only the listed
browser files and synthetic fixtures are copied. ProofMatch has local-server
status text adjusted for the embedded copy; Spread gets a button to load its
existing synthetic example. Adaptations fail if their source anchors change.
Other source bytes are copied unchanged. ProofMatch's service worker is scoped
to its own app directory. The original localhost servers and their response
headers are not included in the bundle.

When adding a pet, first verify a browser-only entry point and include every
required local asset, with no secrets or private data. Server-backed solutions
need their actual runtime and deployment before they can be listed as runnable
here. Never infer an app URL from a repository, company website or localhost
port. Keep synthetic/demo boundaries visible and retain upstream provenance.
