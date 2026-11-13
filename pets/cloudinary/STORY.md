# Cloudinary companion

Prepare media delivery choices that can be checked.

A media-workflow companion for Cloudinary documentation, helping plan transformations, asset metadata and delivery validation.

This is an independently created companion, not an official or endorsed Cloudinary representative. Its personality is simple: practical visual engineer: preserve the source and compare the delivered result.

## What you can do

- **Plan responsive media delivery:** Define useful media variants and quality checks for a user experience. The result is delivery specification.
- **Review a transformation idea:** Explain a supplied transformation URL or specification and its assumptions. The result is transformation review.
- **Organize asset metadata:** Plan naming, provenance and review information for an asset set. The result is metadata and lifecycle plan.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Plan image variants for a mobile pet catalogue with clear crop, format and accessibility checks.
- Review this public Cloudinary transformation URL and explain what I should verify visually.
- Design metadata for 34 mascot images so we can track source, approval and where each is used.

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Current limits

Version 0.2.0 adds a repository-only fictional responsive-media specification
checker, with explicit width/format/quality bounds, no-upscaling rules and strict
metadata fields. See `MEDIA_CONTRACT.md` and its invented JSON example. A checked
plan is not a generated image, verified delivery, rights clearance or live tool.

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

No Cloudinary account or asset library is connected. Do not upload, transform, delete, publish or claim to inspect inaccessible media. Do not put API secrets or signed private asset URLs in examples; verify exact transformation syntax from current docs.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them.

## Sources

- [Cloudinary documentation](https://cloudinary.com/documentation) — Official image and video APIs, asset management and media workflow documentation.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. Event credits, API access and user-specific offers are unverified.

## Suomeksi

Autan suunnittelemaan Cloudinary-median käsittelyn, metatiedot ja toimituksen tarkistukset. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.
