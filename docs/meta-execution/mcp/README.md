# Meta public documentation MCP bootstrap

Work ID: META-MCP-20261114. This folder is an execution aid for the existing authorized worker, not a daemon, scheduler, credential store, or glasses runtime.

## Verified source

Official repository: https://github.com/meta/meta-wearables-dat-ios
README commit: bbae597cd1c748cd29b9375a1624a8d75b1c9e14
README blob: 98547c399efd5c4ec0b3654716ffa37173d09919

The README documents anonymous Streamable HTTP documentation access at:
https://mcp.developer.meta.com/wearables

No Authorization header, token, OAuth setup, or account grant is needed for the two public search tools. Account-specific Developer Center tools are outside this bootstrap.

## Use in a cloud worker

The Python helper uses only the standard library and makes bounded read-only calls:

~~~sh
python meta_docs_mcp.py \
  --query 'iOS DeviceSession camera stream permission and cancellation lifecycle' \
  --max-results 2 \
  --receipt meta_docs_query.json
~~~

Choose --tool search_webapps_docs for Display web guidance. The helper performs initialize, initialized notification, tools/list, and tools/call. It accepts only search_dat_docs and search_webapps_docs and writes a bounded public excerpt plus source URLs and response hashes. It does not use private images or task history.

## Add the MCP to an existing Codex worker invocation

~~~sh
python codex_with_meta_docs.py mcp get meta_wearables_docs --json
python codex_with_meta_docs.py exec -C /absolute/verified/task/worktree '<the existing scoped work order>'
~~~

The wrapper adds the URL and a two-tool allowlist through -c flags only for that invocation. It leaves the current account, default model, rules, sandbox, other connectors, credentials and user configuration in their existing state. Run the actual worker only under its existing work assignment and quota.

The equivalent TOML fragment is in codex-mcp.fragment.toml. It is supplied for a coordinator to merge into a trusted project configuration if that worker supports it; it was not installed globally. CLI parsing and readback were verified with codex-cli 0.167.0-alpha.4.

The official mwdat-ios plugin is also available under the upstream repository's plugins/mwdat-ios directory. This bootstrap did not install or execute upstream plugin scripts.

## Limits

Documentation access does not establish glasses pairing, a Developer Center account, native SDK runtime, Display hardware, a Chibi host route, or a production integration. Do not mark those qualified from this receipt.

The general Meta FAQ and pinned SDK may disagree. Use exact versioned APIs and actual relevant runtime evidence when resolving a capability question. Native Display mock, Display web simulator and physical Display remain separate.

The initial broad iOS session query returned an Android API result as well as shared guidance. That response establishes live search access, not exact iOS API compatibility. Inspect returned platform/version references and use the pinned Swift interfaces for iOS API decisions. The WebApps response contains relative documentation links, which resolve under https://wearables.developer.meta.com.

These helpers and a source-bound publication copy of the receipt are persisted with the execution plan in Junction PR104. The publication copy omits reproduced documentation excerpts and retains source URLs, response hashes, outcomes and the original receipt hash. This is developer documentation, not a public catalog or product runtime registration.
