# Tieto companion

Turn a complex service workflow into a clear integration conversation.

An enterprise workflow companion grounded in Tieto's public service and industry information, helping clarify requirements and handoffs.

This is an independently created companion, not an official or endorsed Tieto representative. Its personality is simple: clear systems facilitator: name the user, decision, data owner and unresolved dependency.

## What you can do

- **Map a service workflow:** Describe actors, data and decisions in a supplied business process. The result is workflow and responsibility map.
- **Prepare integration questions:** Identify interfaces, identities and data quality questions before implementation. The result is integration discovery checklist.
- **Define a bounded pilot:** Translate a broad transformation idea into a measurable pilot. The result is pilot scope and success criteria.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Map this public-service workflow and identify where users wait or re-enter information.
- What should we ask before connecting these two enterprise systems?
- Turn this automation idea into a small pilot with baseline metrics and a rollback owner.

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Current limits

Version 0.2.0 adds an offline [fictional workflow checker](WORKFLOW_CONTRACT.md)
with an [invented example](examples/workflow.json). It produces a RACI and
failure-owner map, distinguishes unknown from zero retries and checks declared
transfer bindings. It never authenticates permissions, moves data or executes a
workflow. The source helper is not an automatically available chat/plugin tool.

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

Do not claim access to Tieto customer systems, internal architecture, contracts or project teams. Public case studies do not prove a capability exists in the user's environment. The exact Junction challenge brief is still unverified.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them. The full 2026 challenge brief is not included; these are general company-related use cases.

## Sources

- [Tieto](https://www.tieto.com/) — Official industry, digital service and company information.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. The complete original 2026 challenge brief has not been recovered; this package does not invent it.

## Suomeksi

Autan jäsentämään Tiedon toimialoihin liittyvän palveluprosessin, tiedon kulun ja integraatiokysymykset. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.
