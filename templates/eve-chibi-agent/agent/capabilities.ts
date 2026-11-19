// Source-only declarations, not runtime grants or Marketplace entitlements.
export const capabilities = [
  {
    id: "clarify-goal",
    title: "Clarify a goal",
    kind: "guidance",
    prerequisites: [],
    effect: "proposal-only",
  },
  {
    id: "plan-next-step",
    title: "Plan a small next step",
    kind: "planning",
    prerequisites: ["clarify-goal"],
    effect: "proposal-only",
  },
  {
    id: "reflect-on-progress",
    title: "Reflect on progress",
    kind: "guidance",
    prerequisites: ["plan-next-step"],
    effect: "proposal-only",
  },
] as const;
