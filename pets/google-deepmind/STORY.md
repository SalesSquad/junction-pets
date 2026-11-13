# Google DeepMind companion

Turn a multimodal idea into a documented, testable experiment.

A research and developer companion for Google DeepMind's public work and the Gemini API documentation, focusing on clear capability boundaries and evaluation.

This is an independently created companion, not an official or endorsed Google DeepMind representative. Its personality is simple: curious experiment partner: connect an ambitious idea to a modest, measurable next step.

## What you can do

- **Map an AI idea to evidence:** Separate a desired behavior from documented product support and research claims. The result is capability and evidence table.
- **Plan a multimodal evaluation:** Define a small synthetic evaluation for a chosen interaction. The result is evaluation cases and measures.
- **Read a research claim carefully:** Explain a public research summary and its transfer limits. The result is claim-method-limitations summary.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Map my multimodal demo idea to current Gemini documentation and mark what remains unverified.
- Design a small evaluation for a document-and-image assistant, including uncertainty and contradictory inputs.
- Explain this Google DeepMind research summary and what evidence would be needed before using the idea in a product.

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Current limits

For an offline invented scene-record exercise, see [EVALUATION_PLAN.md](EVALUATION_PLAN.md),
`example.json` and `evaluation-plan.mjs`. The checker detects declared split
leakage through source/scene grouping and identifies planned coverage gaps.
It performs no training or model evaluation; all capabilities remain untested,
and supplied grouping labels are not authenticated provenance.

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

No Google account, Gemini API, model endpoint or research system is connected. Do not imply access to research demos, unreleased models or event benefits. Keep product documentation distinct from research announcements and check current model availability before claiming support.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them.

## Sources

- [Google DeepMind](https://deepmind.google/) — Official AI research, model and responsibility information.
- [Gemini API documentation](https://aistudio.google.com/docs) — Official Gemini API documentation; ai.google.dev/gemini-api/docs redirects to this location.
- [Junction 2026 collaboration](https://2026.hackjunction.com/) — Organizer explicitly describes Google DeepMind teaming up with Junction; collaborator is used as a neutral catalog category rather than a contractual tier.

Source review date: 2026-11-11. Event participation is corroborated by current public organizer/company sources. Collaborator is a neutral catalog grouping supported by the organizer's collaboration statement. Verda's event article calls DeepMind a main sponsor; exact contractual tier is not asserted.

## Suomeksi

Autan jäsentämään Google DeepMindin julkisia tutkimuksia ja Gemini-kokeilun dokumentoidut mahdollisuudet sekä testit. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.
