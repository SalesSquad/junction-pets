# aiven-decision-bridge

Typed companion answers mapped to human decisions in Chibi.

An offline prototype, registered as source through `services/aiven-platform` and
`config/special-capabilities.json`; it is not a live Chibi integration.

`toPendingActions(response, context, { trustedUserIntents })` requires the host to
provide a list of exact `{ operation, target, parameters }` intents from the user's
own explicit request. A matching intent is required for every proposal; it must not
be inferred from model output, retrieved pages, files or other untrusted content.
The intent identifies what was requested; it is not approval or permission to
execute. The host must independently authenticate the user, check its policy and
record a bound human decision. Without a matching intent the conversion fails.

The bridge is not a complete prompt-injection defense. The cascade's model-based
injection evaluation has not met its documented target and its new changes have
not been re-evaluated with a model. Keep live host execution disabled until the
appropriate host and model evaluations are complete.
