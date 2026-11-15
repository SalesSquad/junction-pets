# Bounded provider pilot

Design record: `JUNCTION-TOKENS-20261113`, admitted from Junction source
`61f10a44cfd833e02fa64462dfc7429046fff210` into the independently owned
`services/provider-pilot/` subtree. This developer experiment observes one
public/synthetic grounding task. It does not activate Chibi, execute companion
tools, qualify an eval, issue grants or change the Council/host contract.

One fixed manifest-only fixture asks: **Is the Aiven companion live?** OpenAI,
Anthropic and Gemini return strictly validated JSON `{route,response}`. TypeSafe
Jev supplies typed `route` choice and `evidence_supports_live` probability only;
it generates no prose. Routes are `needs_evidence`, `respond`, `review`. A
schema-valid answer can still be wrong: preserve the observation for independent
grounding review. No score or passing quality verdict is invented.

Intended roles to evaluate: Jev for bounded typed decisions/ranking, Luna for
routine decisions/responses, Gemini for decision proposals/large context when
connected, and Anthropic for focused implementation/review. This pilot installs
no production routing policy, proves no universal model ranking and makes no
automatic spending or credential changes.

## Reproduce without provider use

Python 3.10+ standard library only; no package installation:

```sh
python3 -m unittest discover -s services/provider-pilot -p 'test_*.py' -v
python3 services/provider-pilot/pilot.py --provider typesafe --model EXPLICIT_MODEL_ID --source-commit FULL_40_HEX_SHA
```

The default is plan-only. It reads neither provider environment variables nor
credentials and performs no network requests or Git checks. The output binds
the requested source SHA, this script's SHA-256, fixed fixture digest and exact
request-body digest; `localCheckoutVerified:false` remains explicit.

## One explicitly enabled observation

Use an existing authorized provider account and available credits. Supply the
selected provider's conventional environment variable through its approved
executor: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` or
`TYPESAFE_API_KEY`. This script never reads key files, clipboard, login sessions
or other accounts and never buys credits. No credential belongs in a command
argument, receipt or Git file.

```sh
python3 services/provider-pilot/pilot.py --provider openai --model EXPLICIT_MODEL_ID --source-commit FULL_40_HEX_SHA --execute
```

`--execute` requires a clean checkout of the exact supplied commit with origin
`SalesSquad/junction-pets`; source is checked before and after the one call.
Choose the exact model string discovered from the authorized provider. No model
is hardcoded, inferred from a subscription alias or silently substituted. An
alias may return another model/version; the receipt records both and sets
`exactModelVerified` only when the returned string equals the requested string.
This equality is provider-reported metadata, not independent model attestation.

The transport uses fixed first-party HTTPS endpoints, ignores proxy environment
variables, refuses redirects, sets a 20-second socket timeout, bounds request and
response bodies to 100 KiB, and performs one attempt with no retries or fallback.
Generation requests cap output at 512 tokens. TypeSafe's current System One
schema exposes **no request-level output-token cap**: this pilot asks only two
small typed questions and rejects reported output over 512 afterward. That
post-response check cannot prevent already-billed provider output. No invented
TypeSafe request parameter is sent. Token limits are not dollar-spend limits.

Successful receipts contain requested/returned model, provider-reported IDs and
usage, elapsed time, source/fixture/request/response digests and bounded public
output. Request IDs may be absent when a provider does not return them. Typed
answers, output schema, usage, completion status and absence of tool-call output
are checked. Raw HTTP bodies, headers and error details never appear in CLI
errors; credential echoes are refused. An unsuccessful call may already have
consumed tokens and its usage may be unknown; no automatic retry occurs. Receipts remain unqualified local
observations without Chibi host identity, signed receipts or recipient acceptance.
Keep output outside source or in an already ignored private evidence destination.

## Provider contracts checked 13 November 2026

- [OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create): `POST https://api.openai.com/v1/responses`, bearer authorization, strict JSON schema and `max_output_tokens`.
- [Anthropic Messages](https://platform.claude.com/docs/en/api/messages): `POST https://api.anthropic.com/v1/messages`, `x-api-key`, the executor's verified compatible API version `2023-06-01`, `max_tokens`; JSON instruction plus strict local validation.
- [Gemini generateContent](https://aistudio.google.com/api-reference/generate-content): `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, `x-goog-api-key`, JSON response schema and `maxOutputTokens`.
- [TypeSafe System One](https://docs.typesafe.ai/api/system-one.md): `POST https://api.typesafe.ai/v1/systemone`, bearer authorization, named `choice`/`noul` questions, returned model and input/output usage.

No live provider verification or credential access is required by the unit suite.
