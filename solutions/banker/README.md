# Banker — Junction companion app

Banker is a fictional banking companion demo for the Junction app collection. Open `index.html` using a static web server, or export it with `node apps/companion-browser-apps/export.mjs /tmp/junction-banker-bundle`. It presents a fictional Cayman Island Bank account with a €0 balance, unpaid AI-service invoices and a payment approval dialog. Approval is a simulation; no money moves.

The private Chibi host provides the companion card and a separate richer Banker demo at `/fi/banker-demo`. This portable app has no account connection, server, saved memory, model, conversational voice agent, payment provider or integration with other agents. Permission controls are local visual demonstration controls, not grants. An optional approval prompt uses the browser’s speech synthesis if available. No sponsor endorsement or competition submission is claimed.

Run `node --test apps/companion-browser-apps/export.test.mjs` from the repository root to verify the exported entry and assets.
