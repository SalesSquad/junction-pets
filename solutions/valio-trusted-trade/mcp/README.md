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

Sponsor lookup accepts only numeric catalog IDs (1–12 digits); never submit personal identifiers. Browser recovery omits free-text form inputs. Local bearer/key storage and host-mediated approval are suitable only for this synthetic prototype, not production identity or trusted human-presence evidence.

## Optional host-owned identity

`createTradeClient` accepts executor-owned callbacks `hostAccessToken()` and
`hostDecisionProof(context)`. These are not MCP tool arguments. Enabling the
access callback disables demo-session minting; each workflow request obtains a
fresh credential, checks that exact credential through `/api/identity/me`, and
only then sends the workflow operation with the same credential. The persisted
buyer is pinned to the opaque `profileId` and `ownerRef`, rather than the rotating
JWT. A changed profile/owner or a nonempty demo checkpoint is refused without
replacing its workflow. A host checkpoint cannot silently return to demo mode.

The proof callback receives the exact action (`QUOTE_DECISION` or
`PAYMENT_DECISION`), requested decision, buyer, profile/owner references, run,
quote, source snapshot, total and canonical quote-body digest; a payment also
includes its order and payment-proposal digest. A trusted host must independently
obtain the human decision and sign the server's required short-lived proof.
A role, access token or synthetic MCP form is not that proof. If the callback is
missing or refuses, the tool returns `HOST_DECISION_REQUIRED`; it does not approve
anything. `review_purchase` asks the host for an approval proof; the host may
refuse that request, and rejection can be recorded through the host's exact
HTTP decision flow. This adapter does not invent a host login or human-presence
claim.

Only decision/payment-approval requests carry `X-Buyer-Decision-Proof`. The
server verifies issuer, audience, signature, scope, human grant, expiry and nonce
atomically with the domain decision. The MCP client continues independently
checking its original need, quote/body and budget exception. It records its
accepted caller scope only after the server accepts the decision. A lost-ACK
retry uses the same command; its proof is cached only in process memory for the
short retry window, never in SQLite. After restart the trusted host must provide
its original still-valid keyed proof or direct the caller to inspect status;
there is no generic approval token.

For an already approved local host integration, the CLI also accepts
`VALIO_HOST_ACCESS_TOKEN_FILE` and optional `VALIO_HOST_DECISION_PROOF_FILE`.
These paths belong to the executor configuration and must name existing,
owner-held, private (0600), regular non-symlink files of at most 16 KiB. Files are
read afresh; a missing/unsafe file or malformed credential fails closed. A proof
file must contain the host-signed proof for the current exact decision, including
all server-required scope and reviewer-grant claims. Do not pass these paths,
JWTs or proofs through model arguments, commit them, or use the proof file as a
standing consent grant. No real issuer, principal mapping or provider permission
is established by setting an environment variable.

Focused check (after `npm --prefix mcp ci --ignore-scripts`):

```sh
node mcp/checks/host-identity.mjs
```

This uses an injected fake host transport plus an official SDK stdio call. It
checks no demo minting, credential refresh, owner/profile pinning, lost-decision
ACK recovery, strict model-input refusal and absence of host credentials in
persisted state/tool output. Cryptographic issuer qualification and server
consent policy are separate checks; this test makes no real identity claim.
