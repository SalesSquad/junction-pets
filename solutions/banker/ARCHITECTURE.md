# Banker architecture

The portable browser demo consists of `index.html`, `styles.css` and `app.mjs`. Its invoice fixtures and zero balance are fictional and remain in browser memory. There are no network calls or credentials. Payment proposals and approvals have no external effect. The shared companion browser app exporter copies these files and publishes their path in its generated catalog.

Private Chibi owns identity, consent, policy, private memory, model calls, connections and any actual payment authorization. A catalog record does not grant access or establish a live gateway. The existing Chibi Banker demo and its source remain in the private Chibi repository; this portable artifact is a separately runnable Junction demo, not an exported copy of private source.
