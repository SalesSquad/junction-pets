# Claude architecture guidance — provenance and limits

This is a concise record of **earlier architectural advice**, not approval of the
current source, a test result or a hosted execution receipt.

On 13 November 2026 the coordinator recovered the existing 12 November review
through the owner's authorized Mac connection. The retained Claude Code result
reports `claude-fable-5-2`, `subtype: success`, `is_error: false`, and no subagents.
The response explicitly says it reviewed the supplied brief only: it did **not**
read repositories, execute commands or independently verify the stated baseline.
Its raw local result has SHA-256
`dfc6d72c6542a27f5a5e919d784fc8f0f4c54c4e7ea3711739dd2231a33c1fa9`.
The model label is retained result metadata, not a new model invocation today.

## Guidance applied to this delivery

- Keep a stable logical developer and bounded ownership for every company;
  environment configuration is not a permanently running worker.
- Preserve exact source, author/reviewer identity, checks and PR handoff. A
  future worker resumes from GitHub, not an old chat or assumed live machine.
- Keep the development plane separate from the private Chibi authority plane.
  A Council proposal, source test or checkpoint must never grant runtime rights.
- A checkpoint or status reader is not a scheduler. Record missing dispatch,
  provider/model and recipient proof explicitly instead of showing false green.
- Demonstrate one genuinely authorized end-to-end workflow before claiming a
  live fleet. Independently reviewed synthetic company modules remain useful
  source work, but do not substitute for that runtime proof.

The source implementation uses the existing architecture and host-private seam;
the review's speculative service choices, public-repository assumptions and
estimates were **not** silently adopted. They require current source evidence,
an explicit design decision and the applicable release/access authority.

## Current review boundary

Company modules in this delivery have separate source reviews and exact-HEAD
test receipts linked from the development progress register. Do not attribute
those reviews to Claude or this historical proposal. The recovered proposal
does not prove that the current source, Cloud environments, database, provider
integration, 204 authored model cases or Chibi recipient flow has executed.

The Mac's current Claude CLI and existing subscription login were observed, but
creating a new durable receipt runner failed before a prompt was submitted.
No new Claude completion, tool permission, fallback account, spending approval
or bypass is inferred from that diagnostic. Portable development continued.
