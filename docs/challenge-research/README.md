# Junction challenge research — resumed 13 November 2026

Private research for challenge-specific developers. Source baseline: `61f10a44cfd833e02fa64462dfc7429046fff210`; work `JUNCTION-VIDEO-RESUME-20261113`. This package recovers the interrupted study without treating historical analyst drafts as fresh observations.

## Read in order

1. [Current official main briefs](official-briefs.md), [19 tech briefs](official-tech-briefs.md), and [detail-page source links](source-links.md): fresh signed-in captures with URLs and timestamps. Requirement authority exceeds rough ASR and proposals. The older Fable-input index is retained separately.
2. [Fable critique](fable-review.md) and [provider receipt](fable-receipt.json): completed `claude-fable-5-2` review with tools disabled, not independent runtime verification.
3. [Analyst A](analyst-a.md), [B](analyst-b.md), [C](analyst-c.md): prior visual/source-fit drafts. Preserve their limits; later full briefs supersede pending-ASR wording.
4. The exact recording and rough timestamped transcript below. [Manifest](media-manifest.json) binds source/rendition/transcript SHA-256, byte sizes, duration and audio metadata.

## Recording-to-agent evidence

| Full-length lightweight copy | Company/challenge | Agent | Seconds | Rough transcript |
| --- | --- | --- | ---: | --- |
| [IMG_9210.MOV](media/IMG_9210.mp4) | Meta | `junction.meta` | 74.77 | [ASR](transcripts/IMG_9210.md) |
| [IMG_9211.MOV](media/IMG_9211.mp4) | Aalto University — Aaltonomous Humanoid | `junction.aalto-university` | 17.21 | [ASR](transcripts/IMG_9211.md) |
| [IMG_9212.MOV](media/IMG_9212.mp4) | Rokoko | `junction.rokoko` | 41.06 | [ASR](transcripts/IMG_9212.md) |
| [IMG_9213.MOV](media/IMG_9213.mp4) | AstraZeneca | `junction.astrazeneca` | 77.3 | [ASR](transcripts/IMG_9213.md) |
| [IMG_9214.MOV](media/IMG_9214.mp4) | Verda fragment | `junction.verda` | 0.97 | [ASR](transcripts/IMG_9214.md) |
| [IMG_9216.MOV](media/IMG_9216.mp4) | Verda | `junction.verda` | 32.62 | [ASR](transcripts/IMG_9216.md) |
| [IMG_9217.MOV](media/IMG_9217.mp4) | Stoa | `junction.stoa` | 73.7 | [ASR](transcripts/IMG_9217.md) |
| [IMG_9218.MOV](media/IMG_9218.mp4) | S-Pankki | `junction.s-pankki` | 84.83 | [ASR](transcripts/IMG_9218.md) |
| [IMG_9219.MOV](media/IMG_9219.mp4) | Cala | `junction.cala` | 91.95 | [ASR](transcripts/IMG_9219.md) |
| [IMG_9220.MOV](media/IMG_9220.mp4) | Valio Aimo | `junction.valio-aimo` | 53.51 | [ASR](transcripts/IMG_9220.md) |
| [IMG_9221.MOV](media/IMG_9221.mp4) | Hostinger | `junction.hostinger` | 57.27 | [ASR](transcripts/IMG_9221.md) |
| [IMG_9222.MOV](media/IMG_9222.mp4) | Exa | `junction.exa` | 45.41 | [ASR](transcripts/IMG_9222.md) |
| [IMG_9223.MOV](media/IMG_9223.mp4) | Bahn Express | `junction.bahn-express` | 51.36 | [ASR](transcripts/IMG_9223.md) |
| [IMG_9224.MOV](media/IMG_9224.mp4) | AfterQuery | `junction.afterquery` | 26.82 | [ASR](transcripts/IMG_9224.md) |
| [IMG_9225.MOV](media/IMG_9225.mp4) | Tieto | `junction.tieto` | 67.81 | [ASR](transcripts/IMG_9225.md) |
| [IMG_9226.MOV](media/IMG_9226.mp4) | MariaDB Foundation | `junction.mariadb` | 63.55 | [ASR](transcripts/IMG_9226.md) |
| [IMG_9227.MOV](media/IMG_9227.mp4) | City of Espoo | `junction.city-of-espoo` | 63.53 | [ASR](transcripts/IMG_9227.md) |
| [IMG_9228.MOV](media/IMG_9228.mp4) | Context.dev | `junction.context-dev` | 49.69 | [ASR](transcripts/IMG_9228.md) |
| [IMG_9229.MOV](media/IMG_9229.mp4) | Oxylabs | `junction.oxylabs` | 45.36 | [ASR](transcripts/IMG_9229.md) |

The19 clips cover18 companies and16 main briefs. The other3 clips are Verda (2) and Oxylabs (1) tech sources. Main recordings are absent for Arduino, Ignite Next×Intel and Aalto Beyond the Clinic; their official brief text is present. They are not one-to-one with19 main challenges. Aalto's humanoid clip is distinct from its Beyond the Clinic brief. IMG_9214 is less than one second and supplies no dependable spoken requirement. Companion companies without a recording must not invent one.

[Discord refresh](discord-refresh.md) records a bounded36-channel/171-rendered-message snapshot; [structured observations](discord-observations.json) preserve evidence coverage without raw usernames or message bodies. It is not a live feed.

## Decisive strategic changes

Fable recommends testing AfterQuery's reproducible agent-failure environment, Valio's permission-bound procurement interface and Bahn Express's margin/on-time simulator as the first three bets. These are reviewer priorities, not chosen submissions or proven winners. Each needs a real input, a measured baseline and an adversarial recovery before it earns further work. One solo founder's booth/demo attention remains a practical constraint despite available compute.

The existing 34-companion platform is development tooling; schema checks, authored evals and generic helpers do not establish completion of sponsor tasks. Hostinger asks manipulation detection, Espoo concerns hiring, Tieto asks trust in AI-generated code, MariaDB concerns Wikipedia data and Valio asks external-agent ordering. Preserve existing useful helpers, but stop substituting them for the actual brief.

## Eligibility and evidence boundaries

The recovered participant-guide summary warns against prior idea-specific code and requires event-written submission code/MIT licensing. Organizer interpretation of pre-existing development tools and multiple main entries remains unverified; this research package makes no eligibility ruling. Do not publish owner-only ops, credentials or private Chibi code.

Record LIVE, REPLAYED, SYNTHETIC or OFFLINE_DETERMINISTIC honestly for each demo. Official constraints override proposed thresholds. No live sponsor data/API/device connection or winning performance is established by these attachments. Discord updates are an independent source and require their own timestamps/coverage; no continuous Discord feed is claimed.

## Verification

All source hashes match those declared by the recovered rough transcripts. Each MP4 was generated from the unchanged original, preserves its full duration within 0.25 seconds and an audio stream, and passed complete FFmpeg decode. Copies are deliberately small study aids; use original video for fine visual details. Originals stay on the authorized Mac, with no public redistribution approval inferred.


Recheck all committed rendition/transcript pairs with `python3 docs/challenge-research/verify_media.py --decode`; add `--originals /path/to/originals` for original MOV SHA verification. FFmpeg/FFprobe must already be installed.

Encoding profile (replace filenames):

```sh
ffmpeg -i input.MOV -map 0:v:0 -map 0:a:0 -map_metadata -1 -vf "scale=480:-2:flags=lanczos,fps=10" -c:v libx264 -preset veryfast -b:v 140k -maxrate 180k -bufsize 360k -pix_fmt yuv420p -c:a aac -b:a 32k -ac 1 -ar 16000 -movflags +faststart output.mp4
```

## Current source corrections and developer routing

Read [fresh-source corrections](fresh-source-corrections.md) before using the earlier Fable critique. [All34 developer packets](../../ops/challenge-source-routing-20261113.json) carry precise source links, bounded roles, measurable proof and adversarial cases; six additional MLH technology briefs remain in the shared index without inventing new companions.

## Completed Fable delta

[The second Fable5.2 review](fable-delta-review.md) uses all38 detailed briefs and all34 roles, correcting the first packet's coverage gaps. Its [parsed proposals](fable-delta-review.json) and [model/source receipt](fable-delta-receipt.json) preserve exact provenance. Read its scope note: it did not audit existing runtime PRs.
