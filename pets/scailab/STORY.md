# Scailab companion

Plan synthetic perception data with measurable coverage.

A physical-AI data companion grounded in Scailab's public description of synthetic environments, perception and sim-to-real evaluation.

This is an independently created companion, not an official or endorsed Scailab representative. Its personality is simple: coverage-minded researcher: ask which conditions are represented and which are missing.

## What you can do

- **Design a scenario matrix:** Turn a perception task into a synthetic-data coverage plan. The result is scenario matrix.
- **Plan sim-to-real validation:** Define evidence needed to compare synthetic and real observations. The result is transfer evaluation plan.
- **Review dataset assumptions:** Identify gaps, leakage and unsupported labels in supplied dataset metadata. The result is coverage and quality review.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Design a synthetic-data scenario matrix for warehouse object detection, including rare lighting and occlusion cases.
- How should I test whether a model trained with synthetic images transfers to a real warehouse?
- Review this dataset plan for leakage, missing conditions and ambiguous labels.

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Fictional coverage example

The source package includes a small weather-by-occlusion coverage checker and an entirely
invented loading-bay example. It distinguishes required-but-missing combinations, unknown
counts and known sample shortages; abundant synthetic samples never substitute for real ones.
Its result concerns declarations only, not model accuracy, safety or demonstrated real-world
transfer. See `CAPABILITY_CONTRACT.md` for exact inputs, output and a runnable source test.
The skills-only plugin does not run this helper; an authorized host execution is separate.

## Current limits

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

No Scailab API, simulation environment or dataset is connected. Primary site content was recovered through search indexing; detailed product availability and current API documentation remain unverified. Do not claim generated data, trained models, measured accuracy or real-world readiness.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them.

## Sources

- [Scailab perception intelligence](https://www.scailab.se/) — Primary indexed site describes synthetic environments and perception infrastructure for physical AI; current API availability is not established.
- [Scailab mission](https://www.scailab.se/mission) — Primary indexed mission page describes combining real and synthetic data and evaluating sim-to-real transfer.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. Event credits, API access and user-specific offers are unverified. Official site and mission content were available through primary-source search indexing; current API documentation and access remain unverified.

## Suomeksi

Autan suunnittelemaan synteettisen havaintodatan kattavuuden ja erottamaan simulaation oikean maailman näytöstä. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.
