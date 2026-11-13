# Behavioral evaluation evidence for the 34 Junction companions

The repository contains **204 authored evaluation cases** (six per companion). Their descriptions are natural-language behavioral and safety criteria, not executable substring tests. The existence of a rubric does **not** mean the companion has generated any output, used a real model, connected to a provider or passed a behavioral gate.

## Prepare a source-bound case manifest

From the repository root, with Node.js 22 or newer and installed dependencies:

```sh
node scripts/behavior-eval.mjs prepare
```

This creates `dist/evals/cases.json` with all 204 prompts, positive criteria, safety criteria, per-case SHA-256 and complete company-package hashes. With no commit supplied, the manifest's `source.commit` is **null** and no subsequent submitted response can qualify as source-bound.

When an actual canonical GitHub commit has been checked independently, pin **that exact full SHA**, not the SHA of a reconstructed checkout, an unpushed worktree or an earlier branch:

```sh
node scripts/behavior-eval.mjs prepare --source-commit 0123456789012345678901234567890123456789
```

The example SHA is a placeholder. The command accepts a structurally valid SHA but cannot by itself prove that the commit exists in GitHub. Record the verified commit URL externally. Regenerate after any pet package, instruction or evaluation change.

## Capture and review model output

An authorized runner may call a model or capture a deterministic synthetic response. Supply one response per case in JSON or JSONL. The record contract is:

```json
{
  "schemaVersion": 1,
  "caseId": "junction.mariadb/no-provider-connection",
  "caseSha256": "<SHA-256 from exact manifest>",
  "sourceCommit": "<verified full GitHub commit SHA>",
  "runId": "mariadb-no-provider-connection-001",
  "execution": {
    "kind": "model-response",
    "provider": "<actual provider>",
    "model": "<actual model/version>",
    "invocationId": "<actual external invocation ID>",
    "completedAt": "2026-11-12T18:00:00Z"
  },
  "response": {"text": "<exact response text>", "sha256": "<SHA-256 of response text>"},
  "adjudication": {
    "reviewerId": "<actual reviewer identifier>",
    "method": "human",
    "reviewedAt": "2026-11-12T18:05:00Z",
    "responseSha256": "<same exact response digest>",
    "mustInclude": [
      {"criterion": "<exact first manifest mustInclude item>", "met": true, "evidence": "<specific rationale grounded in response>"}
    ],
    "mustNotClaim": [
      {"criterion": "<exact first manifest mustNotClaim item>", "violated": false, "evidence": "<specific rationale grounded in response>"}
    ]
  }
}
```

Include **every** positive and negative item, in exact manifest order. The one-element arrays above illustrate the schema; real cases have multiple criteria. An actual evaluator makes semantic judgments about intended meaning, provenance, missing context and unsafe claims. A boolean without a specific rationale is not acceptable. If a forbidden claim was made, set `violated: true` and document the offending text even when all positive criteria were met.

For a controlled fixture, set `execution.kind: "synthetic"`, `provider: "synthetic"` and an explicit fixture invocation ID. Such a run cannot count as a hosted model execution.

## Check a transcript

```sh
node scripts/behavior-eval.mjs check \
  --manifest dist/evals/cases.json \
  --submissions path/to/model-responses.jsonl \
  --expected-source 0123456789012345678901234567890123456789
```

This rejects stale source/case hashes, changed response bytes, missing/reordered criteria, unsupported execution provenance, empty reviewer evidence and duplicate case records. A safety violation returns a failing process status. The command prints counts and identifiers, not raw model responses. Store potentially private transcripts only in the appropriate authorized evidence system, not in the published Junction source.

**Important trust distinction:** a JSONL file can self-assert a model invocation ID and reviewer identity. The offline checker verifies structure and exact bytes, **not the provider's or reviewer's signature**. An all-positive record is labeled `candidate-pass` with `qualified: false`, `evidenceLevel: supplied-unverified`, `providerInvocationVerified: false`. The aggregate always reports **zero provider-verified executions and zero qualified passes** until a separate authenticated attestation verifier is integrated. Never report `candidate-pass` as deployed, certified, or complete.

## Production-quality next gate

Implement an adapter for the actual authorized Chibi host or Codex Cloud agent endpoint that returns immutable invocation receipts, pinned model version, execution context and principal. Bind a separate reviewer/evaluation authority to the exact request/response hashes; retain failures and disagreements. Only then can a coordinator create an authenticated `ops/receipts/<company>.json` entry with a gate-specific status. Running against a provider incurs its own authorization/cost policy; the portable harness intentionally performs **no external model call**.
