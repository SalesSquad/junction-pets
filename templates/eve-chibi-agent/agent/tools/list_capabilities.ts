import { defineTool } from "eve/tools";
import { z } from "zod";
import { capabilities } from "../capabilities.ts";

export default defineTool({
  description:
    "List this starter's declared guidance capabilities and prerequisites. " +
    "The list describes example behavior, not Chibi account permissions.",
  inputSchema: z.strictObject({
    id: z.string().regex(/^[a-z][a-z0-9-]*$/).optional(),
  }),
  execute({ id }) {
    const matches = id
      ? capabilities.filter((capability) => capability.id === id)
      : capabilities;

    return {
      status: "template-only",
      connectedToChibi: false,
      grantedPermissions: [],
      capabilities: matches,
    };
  },
});
