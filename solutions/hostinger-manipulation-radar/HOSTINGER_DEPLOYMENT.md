# Signal Desk — Hostinger demo operations

The current product has three workspaces: observable-coordination v2, local-only Nginx Traffic Forensics, and an explicitly consented AI Router text review. The original v1 lab and its 512-case intent audit remain available at /legacy/index.html. V2 contract checks are not comparable to that historical harm-intent audit and do not establish field accuracy.

## Current task authority and boundary

Owner's 15 November request explicitly authorizes improving detection, integrating PR193, and publishing a Signal Desk demo on Hostinger using the team's services. This supersedes this solution's earlier no-activation task boundary, without authorizing new cash spending or unrelated service changes. Use the team coupon from the Hostinger booth; do not substitute a generic coupon or create a paid order. Existing portfolios and traffic remain untouched. Public demo claims require a provider-bound receipt and URL verification.

## Start and qualify locally

Use Node 22 or later. No dependencies are required.

    node server.mjs
    node --test tests/*.test.mjs traffic/*.test.mjs
    node evaluation-v2.mjs

The server binds loopback by default. Production containers explicitly set HOST=0.0.0.0 behind Caddy. Raw traffic logs are parsed entirely in the visitor's browser and are never sent to either server or model. Text review is a separate optional action with an explicit provider-transfer checkbox. Its exact quotes are checked locally against submitted text; model explanations and intent remain unverified.

## Hostinger activation

1. Obtain the team's dedicated Decode the Noise coupon at the Hostinger booth.
2. In the official Hermes VPS setup choose KVM 2 for one month, 5000 Hostinger AI Credits and Instant web scraping. Check that the team's coupon makes the authorized initial order free; stop if a payable amount or unapproved renewal commitment remains.
3. Verify hPanel account, active server, actual remaining credits and provider access separately. Retain the existing Hermes container and its data. Do not reinstall the VPS or replace an occupied ingress.
4. Use the VPS's existing Docker Manager or verified SSH connection. Place only this solution directory in a new Signal Desk project; never deploy the private monorepo, ops, other products, Git metadata or keys.
5. Create the environment file on the VPS, restricted to its owner; use .env.example as a field list. Do not paste keys into chat, command output, Git, screenshots or the browser application.
6. Set HOSTINGER_AI_ROUTER_KEY and the exact HOSTINGER_AI_MODEL from hPanel's Models catalog. Set a project-key daily/monthly credit limit in hPanel where available. The local persistent allowance is a request-count guard, not a currency budget.
7. Use a verified, unused hostname provided by Hostinger. Set SIGNAL_DOMAIN, SIGNAL_PUBLIC_ORIGIN=https://that-hostname, and SIGNAL_SOURCE_REVISION to the exact deployed commit. Check existing ports/Traefik/Docker ingress first: the optional Caddy example owns 80/443 and must not replace an existing proxy.
8. For a new server without existing ingress, create .env with chmod 600 and run node deploy.mjs to validate; run node deploy.mjs --apply for the authorized deployment. For a Hermes/Traefik server, attach Signal Desk to its existing routing using the provider's documented labels; do not start a competing Caddy on occupied ports. The app itself publishes loopback 4173 only.
9. Open the actual HTTPS URL externally, exercise all three journeys, perform one bounded AI request using invented material, and record revision, image digest, provider/model/request outcome and time. Configuration alone is not proof.

Node and Caddy images are pinned by registry digest; record the actual running image digests at deployment. No image, server or Hostinger key is asserted available before activation.

## AI request admission

Default: 12 attempts per UTC day and one in-process request at a time; configuration accepts 0 to disable and is bounded at 100. Every attempt reserves before contacting the model, including unknown failures. A shared persistent quota file is locked across processes and atomically replaced; preserve its Docker volume across releases. Corrupt state, a stored counter from a future UTC day or a surviving lock refuse provider work. After a crash, inspect a lock against live processes before manual recovery. Do not delete quota state to obtain more requests.

Only an exact configured same-origin JSON POST can use the hosted AI route. Missing origin, consent, invalid text, oversized bodies and unsupported methods are rejected. Keys remain server-side; fixed HTTPS endpoint, no redirects, 20-second timeout and 128 KiB response cap. The public demo endpoint is intentionally shared and can exhaust its small allowance; it does not promise authenticated customer service.

## Other Hostinger services

- **Instant web scraping / Oxylabs:** use the provisioned Hermes built-in web tools to fetch a named public source on demand. Do not invent an API schema or treat returned claims as verified labels. The included Hermes task describes the permitted workflow. No private logs, cookies, paywalled or authenticated sources.
- **Hermes Agent:** one on-demand evidence collection/research task, with no automatic publication, server changes or recurring tasks. Public excerpts are untrusted content and require analyst review.
- **AI Builder / Unlimited hosting:** an optional showcase may link to the same verified VPS demo, method, and historical error ledger once the team's plan is active. Publishing a second unconnected dashboard is unnecessary.
- **Connector / API / CLI:** use the existing verified operator connection for inventory and the task's deployment. Do not expose account-level provider tokens to the public app, create broad new grants, or record a configuration manifest as a working connection.

## Provider references checked 15 November 2026

- https://www.hostinger.com/support/what-is-hostinger-ai-router-and-how-to-get-started/
- https://www.hostinger.com/support/how-to-get-started-with-hermes-agent-on-hostinger-vps/
- https://www.hostinger.com/support/hostinger-vps-how-to-manage-your-docker-projects/
- https://www.hostinger.com/support/what-are-oxylabs-credits-and-how-they-work/
- https://docs.hostinger.com/api-reference/overview

No provider calls, coupon redemption, external data acquisition or public URL are established by this document.

The public AI route is intentionally unauthenticated: Origin prevents browser cross-origin use, not scripted clients. The persistent shared allowance is the primary abuse/spend boundary. It limits request attempts, not currency or per-user entitlement; a host clock and volume integrity are trusted. Never refund unknown executions or automatically retry them.

## Health, existing ingress and rollback

The deployment helper waits up to 90 seconds for the app's Docker health check; it does not report a public URL as live. /api/ready checks state-directory writability when AI is configured, without contacting a model or consuming a quota reservation. A separate public URL and bounded real AI request remain necessary. A failed health gate may leave a failed candidate container for operator diagnosis; this is not an automatic rollback promise.

The helper refuses a new Caddy when loopback 80/443 are occupied by another service. Existing Signal Desk Caddy can be updated in place; --app-only starts only the app and preserves a separately managed Hermes/Traefik ingress. Verify the latter's actual routing separately.

Each built image is tagged signal-desk:<source revision> and the previous image is retained. For an operator-authorized rollback, use the previously verified source/environment revision and run node deploy.mjs --apply --no-build (add --app-only for existing ingress); the helper refuses an absent local image and waits for health. Preserve the quota volume across forward and rollback deployments. No rollback or image build was executed on the owner Mac because its disk reserve was insufficient.
