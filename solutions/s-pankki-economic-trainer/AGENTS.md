# S-Pankki economic trainer — developer continuation

This file is a **developer handoff** for the solution, not a banking assistant prompt or a permission grant. Root `AGENTS.md` and `ops/AGENTS.md` govern all writes. Read `README.md`, `ARCHITECTURE.md`, `PROGRESS.md`, then current official S-Pankki challenge/source data and the existing `pets/s-pankki` companion before any new work.

Ownership is `solutions/s-pankki-economic-trainer/**` only; do not change the existing companion, Chibi private runtime, registries, generated plugins, other solution workspaces or shared manifests without explicit integrator coordination. [PR #64](https://github.com/SalesSquad/junction-pets/pull/64) already contains shared solution tooling; never duplicate or overwrite it. Work on an isolated branch from a verified current main and report exact source SHA / tested SHA / next action. Keep user/financial data out of Git. No new banking credentials, spending, public deployment, merges or Junction submissions.

Product principle: delight through **truthful, explainable money interactions**. A code-owned arithmetic oracle and explicit source line must back every calculated answer. Failed/ambiguous categorization is shown, never hallucinated; external model proposals are untrusted. More behaviors are added through clearly tested vertical slices instead of expanding prompts alone.

