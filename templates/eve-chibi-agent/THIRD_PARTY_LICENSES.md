# Direct dependency license inventory

This directory is MIT-licensed **only for its original example code and
documentation**. The following dependencies are obtained separately by `npm
ci` at the versions pinned in `package.json` and `package-lock.json`; their
upstream licenses are **not** replaced by the starter's MIT license.

| Direct package | Pinned version | Upstream license | Primary source |
| --- | --- | --- | --- |
| `eve` | `1.1.0` | Apache-2.0 | [Vercel Eve LICENSE](https://github.com/vercel/eve/blob/main/LICENSE), [NOTICE](https://github.com/vercel/eve/blob/main/NOTICE) |
| `ai` | `7.0.177` | Apache-2.0 | [Vercel AI SDK LICENSE](https://github.com/vercel/ai/blob/main/LICENSE) |
| `@vercel/otel` | `2.3.0` | MIT | [Vercel OTEL package](https://www.npmjs.com/package/@vercel/otel) |
| `@opentelemetry/core` | `2.12.1` | Apache-2.0 | [OpenTelemetry JS LICENSE](https://github.com/open-telemetry/opentelemetry-js/blob/main/LICENSE) |
| `@opentelemetry/resources` | `2.12.1` | Apache-2.0 | [OpenTelemetry JS LICENSE](https://github.com/open-telemetry/opentelemetry-js/blob/main/LICENSE) |
| `@opentelemetry/sdk-trace` | `2.12.1` | Apache-2.0 | [OpenTelemetry JS LICENSE](https://github.com/open-telemetry/opentelemetry-js/blob/main/LICENSE) |
| `zod` | `4.6.7` | MIT | [Zod LICENSE](https://github.com/colinhacks/zod/blob/main/LICENSE) |
| `@types/node` (development only) | `26.6.6` | MIT | [DefinitelyTyped LICENSE](https://github.com/DefinitelyTyped/DefinitelyTyped/blob/master/LICENSE) |
| `typescript` (development only) | `7.0.2` | Apache-2.0 | [TypeScript LICENSE](https://github.com/microsoft/TypeScript/blob/main/LICENSE.txt) |

The list covers **direct dependencies only**; transitive dependencies retain
their respective licenses too. Links point to upstream license sources and
are not a substitute for the license texts shipped with the exact installed
packages. When preparing a redistributed bundle or production artifact:

1. Review licenses and notices in the **resolved lockfile dependency tree**,
   including transitive dependencies and any changed versions.
2. Include the applicable license texts, attribution and Apache `NOTICE`
   information with copies of third-party code as required by those licenses.
3. Do not copy third-party source into the MIT example and present it as
   exclusively Sales Squad Oy copyright.
4. Review commercial or enterprise licensing separately before adding an
   observability server. For example, Langfuse's enterprise modules have
   separate terms, and Arize Phoenix's Elastic License 2.0 restricts offering
   its substantial features as a hosted or managed service.

Langfuse, Phoenix, OpenLIT, OpenLLMetry and Helicone are **not installed** as
dependencies of this starter. Their listing as possible observability options
in the README is not a permission grant, license sublicense or endorsement.
