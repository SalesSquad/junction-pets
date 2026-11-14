# Cloudinary platform, tooling and Junction implementation research

Reviewed 14 November 2026. This developer reference consolidates the Cloudinary research for the existing `junction.cloudinary` companion and `junction-dev-cloudinary` development lane. Product capabilities below are documented capabilities; the repository's current executable is an offline planner. Account entitlements, installed tools and actual media processing require their own observations.

## Start here

Cloudinary provides a managed media pipeline: upload and store assets, transform or generate derivatives, organize their metadata, and deliver the result through a CDN. Its practical value for Junction is a visible improvement to an image/video experience that can be demonstrated with actual artifacts and measurements. Read the [solution overview](https://cloudinary.com/documentation/solution_overview), [Image and Video APIs](https://cloudinary.com/documentation), and this companion's [challenge research](CHALLENGE_RESEARCH.md).

For an existing application, start with the Skills Pack or AI Power Start route and reuse the current project. For a new React/Next.js demo, the corresponding starter is available. These are implementation choices; none requires creating a second developer environment or replacing this monorepo.

## Junction challenge and the four eligible tools

The [official Junction T41 brief](https://hackjunction.app/participate/45/tech-challenges/41), captured on 13 November in [official-tech-briefs.md](../../docs/challenge-research/official-tech-briefs.md), requires an innovative image/video solution using one of the four tools linked from [Cloudinary Hackathons](https://cloudinary.com/pages/hackathons/). The generic hackathon page identifies them:

| Tool | Entry point | Suitable starting point |
| --- | --- | --- |
| React AI Starter Kit | `npx create-cloudinary-react` | A new React application |
| Next.js AI Starter Kit | `npx create-cloudinary-next` | A new Next.js application |
| AI Skills Pack | `npx skills add cloudinary-devs/skills` | Existing projects and supported coding agents |
| AI Power Start | [Official prompts](https://cloudinary.com/documentation/ai_powerstart) | Guided setup or media work with an AI coding assistant |

The generic page asks for a functional, production-ready application with innovative media use. T41 also requires the [hackathon survey](https://cld.media/hackathon-survey). Document which eligible route was used and prepare that submission; writing this research does not submit it.

The preserved Junction-specific brief states a first prize of **USD 500 worth of local Amazon gift cards per winning team member**. The generic page additionally describes credit boosts for winners/honorable mentions and promotional visibility, without a numeric credit allowance. Neither establishes this team's eligibility, redeemed credits, unlimited usage or a separate submission deadline. Preserve Junction's event rules separately from a generic starter tutorial.

## What Cloudinary does

| Area | Useful operations | Project implication and primary source |
| --- | --- | --- |
| Images | Resize, crop, smart focal-point selection, format/quality optimization, text/image overlays and variants | Responsive catalog art, thumbnails and social images. [Images](https://cloudinary.com/documentation/cloudinary_image), [optimization](https://cloudinary.com/documentation/image_optimization). |
| Video | Transcode, trim, change aspect ratio, generate posters/previews, adaptive HLS/DASH delivery and player integration | A demo video can become mobile and desktop versions with playback adapted to the connection. [Video](https://cloudinary.com/documentation/cloudinary_video). |
| Audio and subtitles | Speech transcription, captions and supported translation workflows | Searchable spoken content and accessible playback. This is separate from visual scene analysis. [Video transcription](https://cloudinary.com/documentation/video_transcription). |
| Asset management | Folders, tags, structured metadata, search, versions and backup workflows | Track original/source, rights, review state and derivatives. [Asset management](https://cloudinary.com/documentation/asset_management). |
| Automation | MediaFlows PowerFlows and natural-language EasyFlows | Assemble media-processing steps, tagging, alt-text and review workflows. [MediaFlows](https://cloudinary.com/documentation/mediaflows). |
| Delivery and integration | CDN delivery, upload widgets, APIs, SDKs and framework components | Integrate the media pipeline into an existing app; it does not supply the app's complete database or user authorization model. [Documentation](https://cloudinary.com/documentation), [iOS](https://cloudinary.com/documentation/ios_integration). |

Automatic output format and quality are distinct transformation components. The current agent documentation recommends `/f_auto/q_auto` as separate components at the end of the transformation chain. Choose crop rules for the actual subject and compare the pixels; an optimization URL alone is not proof that the right content survived. Source: [agent tooling and examples](https://cloudinary.com/documentation/cloudinary_llm_mcp).

### AI capabilities and their limits

- **Edit existing images:** background removal/replacement, generative fill, object removal/replacement/recoloring and restoration. Choose an operation whose documented constraints fit the source image. [Generative AI transformations](https://cloudinary.com/documentation/generative_ai_transformations).
- **Generate images:** text-to-image and image-to-image through the Image Generation add-on, console, API and supported MCP tools. Model selection may be automatic or explicit; up to four reference images are supported where the chosen model allows them. Outputs become managed media assets. Model availability, resolution and pricing vary. [Image Generation](https://cloudinary.com/documentation/image_generation_addon).
- **Generate video from images:** the Image-to-Video add-on is marked **Beta** in the reviewed documentation. Supported modes include image/reference and start/end-frame workflows with optional motion guidance. It has its own allowance and billing. [Image to Video](https://cloudinary.com/documentation/image_to_video_addon).
- **Understand video visually:** AI Video Analysis is marked **Beta**. Its current output is a timestamped natural-language visual transcript, including for silent footage. An application's own language model can derive summaries, titles or tags from that transcript; direct API output for those planned features must not be represented as already available. It is distinct from speech recognition and text-to-speech. [AI Video Analysis](https://cloudinary.com/documentation/ai_video_analysis).
- **Find assets conversationally:** the DAM Search Agent is an **Enterprise, request-access Beta** in the reviewed source. Do not promise every API/free account general natural-language semantic search. [DAM AI agents](https://cloudinary.com/documentation/dam_ai_agents).

### 3D and Reality Twin boundary

Cloudinary documents 3D ingestion for formats including GLB/glTF, FBX, OBJ, PLY and USDZ, with format-specific upload/ZIP rules and some Beta functionality. Available operations include rendered stills, rotation animations/video, glTF mesh compression using Draco, OBJ-to-GLB and glTF/FBX-to-USDZ conversions. Supported conversion pairs must be checked individually. [3D model transformations](https://cloudinary.com/documentation/transformations_on_3d_models).

This makes Cloudinary a candidate for preparing and delivering previews of existing models. PLY support does **not** establish preservation or rendering of Gaussian-splat attributes. BIM/IFC processing, photogrammetric reconstruction and a complete Reality Twin engine were not established by these sources.

## Official MCP servers, plugins, skills and CLI

Cloudinary provides its own agent tools. These are separate from this repository's independently authored `junction-cloudinary` skills-only companion.

### MCP servers

| Server | Purpose | Documented remote endpoint |
| --- | --- | --- |
| Asset Management | Upload, search, organize and transform assets; supported generation | `https://asset-management.mcp.cloudinary.com/mcp` |
| Environment Config | Presets, named transformations, webhooks and streaming profiles | `https://environment-config.mcp.cloudinary.com/mcp` |
| Structured Metadata | Metadata field and value management | `https://structured-metadata.mcp.cloudinary.com/mcp` |
| Analysis | Recognition, tagging and moderation | `https://analysis.mcp.cloudinary.com/sse` |
| MediaFlows | Media automation | Use the connection configuration in the current official documentation |

Prefer the supported remote connection flow. Analysis uses OAuth only; MediaFlows uses header credentials rather than OAuth. Do not assume one authentication method or transport applies to every server. Official local packages include `@cloudinary/asset-management`, `@cloudinary/environment-config`, `@cloudinary/structured-metadata` and `@cloudinary/analysis`; the documented local setup requires Node 18+.

### Plugins and skills

The official Claude and Cursor plugins package selected skills and remote MCP capabilities. The documented ChatGPT/Codex plugin contains **Asset Management only, without skills**. The six separately installable skills cover documentation, transformations, upload, video, React and Next.js. Installation instructions describe availability, not this executor's installed state.

Primary source for MCP/plugin/authentication details: [Cloudinary agent tools](https://cloudinary.com/documentation/cloudinary_llm_mcp). Skills source: [cloudinary-devs/skills](https://github.com/cloudinary-devs/skills). Marketplace links: [Claude](https://claude.com/plugins/cloudinary), [Cursor](https://cursor.com/marketplace/cloudinary). The current documentation and host's exposed tools must settle actual plugin capabilities.

### CLI

The official package is **`cloudinary-cli`** and its command is **`cld`** (`cloudinary` is an alias). The current reference requires Python 3.8+ and documents OAuth login with refresh. Commands cover uploads, administration, search, transformations and batch utilities.

```bash
# Installation options; choose one when installing is part of the task.
pipx install cloudinary-cli
# Alternative:
uv tool install cloudinary-cli

# Read-only discovery after installation:
cld --version
cld --help
cld search --help

# Supported interactive authentication:
cld login
```

The official Docker image is `cloudinary/cli`. For an authorized headless environment, inject `CLOUDINARY_URL` through the existing approved secret store. Keep values out of commands, Git, logs, Pages and prompts. A named CLI configuration or an OAuth session on a Mac is not automatically present in Codex Cloud. [Cloudinary CLI reference](https://cloudinary.com/documentation/cloudinary_cli).

Cloudinary also documents temporary claimable accounts via `npx @cloudinary/cloud`. That is an onboarding option for a missing account, not a reason to create a duplicate in this existing project.

## Plans, credits and media limits

The following public **Image and Video APIs** figures were reviewed on 14 November 2026. They are not an account balance, an offer to purchase or confirmation of Junction promotional coverage. DAM/Enterprise and individual add-ons have separate entitlements. Sources: [pricing](https://cloudinary.com/pricing), [plan comparison](https://cloudinary.com/pricing/compare-plans), [billing and plans](https://cloudinary.com/documentation/billing_and_plans).

| Plan | Listed monthly price | Annual-billing monthly equivalent | Included base credits |
| --- | --- | --- | --- |
| Free | USD 0 | — | 25 |
| Plus | USD 99 | USD 89 | 225 |
| Advanced | USD 249 | USD 224 | 600 |

Base-credit consumption combines transformations, stored assets and delivery. One credit corresponds to 1,000 base transformations, 1 GB storage or 1 GB image bandwidth. Video bandwidth is 1 GB per credit on Free and 2 GB per credit on the referenced paid plans. These consume the **same pool**, not three independent allocations. For example, 10 GB stored plus 10 GB image delivery plus 5,000 base transforms consumes 25 credits before other operations.

For these self-service plans, transformation and bandwidth usage uses a rolling 30-day window; storage reflects currently stored originals, derivatives and relevant backups. Serving an already cached identical transformation avoids repeating the same transformation work, but delivery still consumes bandwidth. AI and other advanced operations can have higher transformation counts. [Transformation accounting](https://cloudinary.com/documentation/transformation_counts).

| Maximum single uploaded file in the compared plans | Free | Plus | Advanced |
| --- | --- | --- | --- |
| Image | 10 MB | 20 MB | 40 MB |
| Video | 100 MB | 2 GB | 4 GB |
| Raw file | 10 MB | 20 MB | 40 MB |

Image Generation uses **separate generation credits**, with model/resolution-specific consumption; the reviewed reference equates a generation credit to approximately USD 0.01. Do not substitute the 25 base credits for a generation allowance. Its exact free grant was not established; eligible paid generation plans can use pay-as-you-go overage. [Image Generation billing](https://cloudinary.com/documentation/image_generation_addon).

Image-to-Video documents a one-time trial of 16 credits for Free and 32 for paid accounts. The Free example is approximately 16 seconds without audio or 8 seconds with audio; model and settings affect consumption. Check actual account eligibility before use. [Image-to-Video pricing](https://cloudinary.com/documentation/image_to_video_addon).

## Application choices for the existing project

These are proposed uses, not implemented integrations:

| Context | Useful Cloudinary contribution | Keep in its existing owner |
| --- | --- | --- |
| Junction/Chibi | Responsive mascot/product images; a meaningful before/after transformation; accessible demo-video delivery | Chibi identity, consent, private conversations and provider execution |
| Taika Sites and Motion | Image variants, brand overlays, previews, captioned video and optimized delivery | Site/app logic and source editing |
| Reality Twin | Previews of existing 3D models and bounded visual video analysis | Reconstruction, BIM semantics, Gaussian-splat pipeline and scientific measurements |
| Taimi | Approved public images and explanatory videos | Sensitive health data and the application's own authorization boundary |
| Owner media workflow | Process and deliver selected published media | iCloud originals/archive, the existing GPU/model environment, and provenance/catalog relationships |

Cloudinary does not automatically synchronize iCloud or the owner's catalog. That integration would need an explicit source-to-asset mapping, stable IDs, rights and lifecycle decisions. Retain originals and the mapping from each derivative to its source.

### Bounded next implementation slice

The companion currently owns `responsive-media.mjs`, whose contract is [MEDIA_CONTRACT.md](MEDIA_CONTRACT.md). It validates a fictional image specification and returns `status: planned`; `transformationExecuted`, `deliveryVerified`, `pixelsInspected` and `rightsVerified` remain false. Its allowlists are example policy, not Cloudinary's product limits. The registered pet adapter is therefore not a live Cloudinary integration.

A useful next slice would use one approved/public source image and the documented Skills Pack route, perform a real responsive transformation through an already authorized Cloudinary connection, then preserve source/output identifiers and compare dimensions, file size, focal content and alternative text. Include an invalid-crop/unsupported-media case with a source-preserving fallback. Record actual elapsed time only if measured. Do not describe a synthetic plan as a delivered image or assume that smaller files alone prove a better user experience.

Read root `AGENTS.md`, `ops/AGENTS.md`, [CHALLENGE_RESEARCH.md](CHALLENGE_RESEARCH.md), this reference and [MEDIA_CONTRACT.md](MEDIA_CONTRACT.md) before continuing. Use the existing development lane, source-pinned task branch and current PR ownership. A working Cloudinary connection and the account's actual credits remain separate from a working Codex Cloud executor.
