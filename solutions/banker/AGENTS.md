# banker developer scope

Root [AGENTS.md](../../AGENTS.md) applies. This is developer guidance, not a runtime agent profile.

Default owned path: `solutions/banker/`. Put solution-specific code, assets, fixtures and docs here. Reuse existing `apps/`, `services/` and `pets/` through their contracts; get explicit integrator ownership before changing those paths. Do not duplicate pending PR implementations.

Before editing: fill the next task in PROGRESS.md with exact source SHA, owner, paths and acceptance command; inspect current PRs and surviving work. Separate cloud worktrees do not share the local pet lease.

Before handoff: commit, push a task branch, open/update a draft PR, bind checks and independent review to its final HEAD, and update PROGRESS.md. Deployment, merging and runtime calls follow existing authority.
