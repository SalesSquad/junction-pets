# Optional local MCP bridge

This is a runnable **synthetic buyer** with an optional read-only sponsor-MOCK
observation tool, not a Valio commerce integration, production identity, payment
provider or externally deployed MCP service. It uses the
official MCP TypeScript SDK v2 over stdio, with strict inputs and structured
results. Its eight tools call the existing localhost HTTP executor; they never
import supplier business state or expose signing keys/session tokens.

## Run

Start the parent HTTP demo first, then install only this optional package:

```sh
cd solutions/valio-trusted-trade/mcp
npm ci --ignore-scripts
npm start
```

Configure an MCP host with command `node`, the absolute path to `server.mjs`
as its argument, and `SUPPLIER_URL=http://127.0.0.1:4177`. External URLs, URL
credentials and redirects are refused. stdout contains MCP messages only.

With no `VALIO_AGENT_STATE_FILE`, the buyer is explicitly
`MEMORY_NON_RESUMABLE`. To retain the synthetic bearer, buyer key, original
intent and command/confirmation records, set that variable to an explicit
SQLite file in an owner-only directory. The shared local store requires
directory mode 0700/file mode 0600 and rejects a state file bound to a different
HTTP origin. Use a distinct state file for each intended buyer context; there
is no shared default. Keep this local secret-bearing state out of Git/iCloud
and untrusted exports. Client persistence and HTTP server persistence are
separate; start the parent in its SQLite mode for end-to-end restart continuity.

## Tool sequence

1. `lookup_valio_mock` reads only requested product IDs and one date through the
   operator-configured sponsor-mock adapter. It accepts no customer, key or URL.
   Results retain provenance, guard reasons and explicit source-only limits;
   schedule samples have visible counts/truncation. No observation is promoted
   into a trade quote. A missing integration requires server-side operator setup,
   never sending credentials through the model.
2. `search_products` returns a bounded advisory candidate set. It grants no
   dietary guarantee, price commitment or authority.
3. `prepare_purchase` accepts one or two typed requirements, an exact
   integer-cent ceiling and a stable command key. It creates a replayable
   workflow and fixed proposal without ordering or paying.
4. `review_purchase` asks the MCP host for a separate form interaction bound
   to the exact quote/source/amount. The model cannot submit an `approve`
   argument. A missing host capability, decline, stale quote or wrong challenge
   fails closed. A confirmed budget exception belongs to this one quote.
5. `commit_purchase` independently checks the caller's original quantities,
   families, dietary flags, date, budget, packs, charges and signed quote body,
   then signs a one-order mandate using its own buyer key.
6. `settle_purchase` requires a **separate** host confirmation of the exact
   server-derived payment proposal and supplier allocations.
7. `purchase_status` reconciles an ambiguous result; retry the identical
   command key. `cancel_purchase` cancels/refunds the owned synthetic order.

MCP host input is not authentication or proof that a person was present.
A malicious host can fabricate its own responses; all identities and funds
remain the declared single-buyer demo. Human confirmation is not inferred from
a tool description, a model argument, supplier data or an old quote. Private
command keys/nonces and confirmation scope are recorded before side effects.

Results contain compact selected terms and tool-name `nextActions`, rather
than the entire catalog or history. The buyer fetches full source facts only
internally for deterministic verification; repeated orders reuse the registered
buyer key and one public-key read. This reduces model round trips, not the
number of underlying verification operations.

## Explicit qualification

```sh
npm run check
npm audit --omit=dev
```

The check uses the actual official SDK client and stdio transport against a
fresh local SQLite HTTP executor. It covers strict schemas, model-supplied
approval refusal, missing/declined/rejected host input, quote-only budget
exceptions, independent signing, separate payment, replay/refund, stale
confirmation refusal, and restart of **both** buyer and HTTP executor. Host
responses are explicitly scripted synthetic test decisions. It also exercises
legacy form decline and verifies external-origin/timeout refusal. No camera,
provider credentials, real orders or bank are used. The script is intentionally
not named `*.test.mjs`: root tests do not require optional SDK installation.

Runtime dependencies pin server SDK 2.4.0 and Zod 4.6.7; SDK client 2.4.0 is
check-only. Primary interfaces:
[official SDK](https://github.com/modelcontextprotocol/typescript-sdk),
[elicitation example](https://github.com/modelcontextprotocol/typescript-sdk/tree/main/examples/elicitation).

Provider observations are read-only sponsor mock facts, never a promotion into fixture ordering authority. See [the full audit](../AGENT_USAGE_AUDIT.md) for the observed API and exact qualification scope.
