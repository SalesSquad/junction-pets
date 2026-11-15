# SupplyPulse in the Junction App collection

This is the browser entry for Context.dev's SupplyPulse app. The companion app
catalog lists it **before** the older synthetic replay, so a pet's first App
button opens SupplyPulse rather than just the historical lamp simulation.

It shows a deterministic public projection of actual Context.dev observations
and opens the complete live comparison or product-watch application on the
owner's Mac at `http://127.0.0.1:4188/` and `/watches/`. It makes no automatic
loopback probes, provider calls, credential request, schedule or purchase.
Historical capture prices and stock are explicitly historical. Provider keys,
SQLite state and server modules are never included in the static app bundle.

The common Chibi Site serves browser assets, not SupplyPulse's Node/SQLite
service. Like the existing Internet Butler/Rahasää entries, the live application
opens in a new tab on the Mac where its server runs. A different device cannot
reach that Mac through its own loopback address. No public backend deployment
or always-on scheduler is established by this entry.

Start the already implemented runtime on the Mac with its host-side key store:

```sh
PORT=4188 node --env-file=/absolute/private/path/supplypulse.env \
  solutions/context-dev-live-web-decision/server.mjs
```

See [the product README](../../solutions/context-dev-live-web-decision/README.md)
for schedule/storage limits and live evidence. To update the browser projection
from an actual newly imported public capture, use its producer:

```sh
node apps/supplypulse/evidence.mjs
```

The producer reuses the existing exact-identity/price admission, preserves
retrieval dates, exports a fixed public field allowlist and never declares a
current winner. Do not hand-edit generated `evidence.json` or relabel old data.
The shared [browser-app exporter](../companion-browser-apps/README.md) creates the
bundle. Chibi consumes a clean immutable Junction commit through its existing
sync producer; deployed availability is separate from catalog registration.
