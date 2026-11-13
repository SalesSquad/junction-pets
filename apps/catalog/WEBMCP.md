# Catalog WebMCP contract

The existing React catalog feature-detects `document.modelContext.registerTool`
after loading its public catalog. Unsupported browsers retain the ordinary UI.
One page lifecycle registers three tools; unmount aborts registration. A failed
registration aborts the whole set and leaves catalog navigation usable.

| Tool | Completed behavior |
| --- | --- |
| `list_junction_companions` | Reads up to 34 public profile summaries, with optional bounded query and role filter. |
| `read_junction_companion` | Reads one profile's authored capabilities and public source citations. |
| `select_junction_companion` | Clears filters, selects the profile, updates the URL and React detail, waits for a frame, then focuses the detail title before returning success. |

Every tool validates its inputs at execution time, rejects unknown fields, and
returns bounded JSON. Profile text and cited sources are untrusted content.
Selection changes local navigation only. It never signs in, adopts, activates,
connects a provider, or executes a companion task.

The Node capability registry is deliberately not bundled into this browser:
its analyzers have Node dependencies and there is no authorized task backend
route here. Public capability descriptions explicitly return
`unavailable_in_catalog`; there is no pretend execution action. Private `ops/`,
worker receipts and credentials are outside this surface.

Run `node --test apps/catalog/src/webmcp.test.mjs` on Node 22+,
then `npm run build`. Tests exercise lifecycle, unsupported environments,
strict inputs, bounded public results and awaited navigation. Actual browser
WebMCP support remains feature dependent; synthetic registration tests do not
prove the browser has the proposed API.
