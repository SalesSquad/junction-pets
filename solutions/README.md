# Solution workspaces

Each directory represents a product/solution, not just an agent package. Start at
[the developer guide](../docs/SOLUTION_WORKSPACES.md), or run:

```sh
node scripts/solution-workspace.mjs list
node scripts/solution-workspace.mjs brief meta-find-verify
```

Existing research is selected through `docs/AGENT_SOURCE_INDEX.json`. Existing
runtime agents remain under `pets/`; shared implementations keep their current
paths. A workspace may target several challenges and reuse several agents.
