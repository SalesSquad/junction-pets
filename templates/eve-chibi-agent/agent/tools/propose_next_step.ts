import { defineTool } from "eve/tools";
import { z } from "zod";

export default defineTool({
  description:
    "Return a generic time-box for a user's next step, without receiving " +
    "their goal, saving data or calling a service. This is only a proposal.",
  inputSchema: z.strictObject({
    minutes: z.number().int().min(5).max(120).default(20),
  }),
  execute({ minutes }) {
    const reflectMinutes = Math.min(5, Math.max(1, Math.floor(minutes / 5)));

    return {
      status: "draft-not-saved",
      externalEffect: false,
      suggestedSteps: [
        {
          title: "Choose one observable outcome",
          minutes: 2,
          detail: "Describe what a small success would look like.",
        },
        {
          title: "Try one bounded experiment",
          minutes: Math.max(1, minutes - 2 - reflectMinutes),
          detail: "Practice or make one small thing related to the goal.",
        },
        {
          title: "Reflect and adjust",
          minutes: reflectMinutes,
          detail: "Note what worked, what did not, and one possible next step.",
        },
      ],
    };
  },
});
