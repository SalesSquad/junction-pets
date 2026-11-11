# Junction company catalogue

This is the event discovery surface. Accounts, profile data, adoption, permissions
and conversations stay in the existing Chibi host. This application never
simulates an account or model response.

From the repository root, install once with `npm install`, generate the catalogue
using the root build command, and run the workspace through the managed preview.
The workspace name is `@chibi/junction-catalog`. `npm run build --workspace
@chibi/junction-catalog` type-checks the source and writes `dist/site`. For mounting
inside Chibi, use `npm run build --workspace @chibi/junction-catalog --
--base=/junction/`. All catalogue, configuration, downloads and image paths derive
from Vite's `import.meta.env.BASE_URL`; canonical pet links remain on the Chibi host.

## Required public content

- `/catalog.json`: `Catalogue` envelope documented in `src/types.ts`.
- `/host-config.json`: validated canonical HTTPS Chibi origin, locale,
  runtimeStatus, publishedSlugs and verifiedAt. These are presentation metadata,
  never an authentication or authorization grant.
- `/packages/<company>/profile.json`, `AGENTS.md`, `STORY.md`: generated downloads.
- `/assets/company-mascots.png`: newly generated 6×6 original mascot atlas.

With an unverified host or an unpublished pet, the adoption action is disabled
and the QR dialog is explicitly a preview. A shared QR contains only the public
Chibi product URL, with no invitation bearer or access token. The Chibi host must
still enforce authentication, immutable offer consent and runtime authorization.

## Functionality

Company search and role filtering, a desktop company list and accessible native
mobile selector, direct pet URLs via `?pet=junction-company`, tailored capability
and prompt display, prompt copy, official source links, package downloads, and
real QR generation/copy/download. Dialog focus is contained by native `dialog`;
Escape and close restore the originating control.

Illustrations are new artwork rather than the inaccessible previous 34-pet set.
The stable atlas mapping follows package `artIndex`; rows have six equal cells.
Company logos and existing mascots were not used.

Visual reference, original generation prompts and QA comparison are in `design/`.
