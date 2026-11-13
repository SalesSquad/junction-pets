# Cala companion

Make agent data traceable, typed and time-aware.

A companion for planning structured data questions with Cala, focusing on provenance, data types and what a fact actually establishes.

This is an independently created companion, not an official or endorsed Cala representative. Its personality is simple: careful data librarian: ask where a fact came from and when it was true.

## What you can do

- **Frame a structured data question:** Translate a research goal into fields, scope and freshness requirements. The result is field requirements and evidence plan.
- **Review provenance:** Compare exact supplied fields and values with source artifacts, digests and distinct source/observation times. The result separates consistent bindings, failed checks and missing evidence; a citation never establishes truth by itself.
- **Plan a verifiable query:** Describe a query and validation path without executing a service call. The result is query outline and validation cases.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- I want an agent to compare company facts. Help me define typed fields, source provenance and freshness requirements for Cala.
- Review this sample company record and flag missing source, validity and historical-change information.
- Using this supplied Cala schema, outline a query plan and tests for stale or contradictory facts.

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Fictional offline source proof

This source package includes a small [field-provenance checker](PROVENANCE.md)
and a [fictional Paper Finch record](examples/field-provenance.json). It checks
exact values, content digests, source time, observation time and an explicit
freshness deadline. Missing, null, zero and false are not interchangeable. A
recent observation does not make an old source fresh, and mismatched values or
timestamps cannot be repaired by attaching an unrelated citation.

The checker only establishes consistency of the supplied example. Its artifact
metadata is unauthenticated; neither the fiction nor a passing source test proves
real Cala data, source authenticity, model quality or a live connector. Its tests
are separate from the six unchanged authored behavioral eval cases. The generated
skills-only plugin carries instructions, not this executable helper.

## Current limits

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

No live Cala queries, private datasets or account access are included. Do not invent dataset coverage, field names, provenance, freshness or financial conclusions. Validate concrete API syntax against current official documentation.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them. The full 2026 challenge brief is not included; these are general company-related use cases.

## Sources

- [Cala structured data platform](https://www.cala.ai/) — Official description of structured data for agents, with types, provenance and history.
- [Cala documentation](https://docs.cala.ai/) — Official documentation entry point linked from Cala's website.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. The complete original 2026 challenge brief has not been recovered; this package does not invent it.

## Suomeksi

Autan suunnittelemaan Calan tiedon käyttöä niin, että lähde, tyyppi ja ajantasaisuus pysyvät näkyvissä. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.

Fiktiivinen offline-esimerkki tarkistaa kenttäkohtaisen arvon, lähdeaineiston
tiivisteen sekä lähde- ja havaintoajan vastaavuuden. Johdonmukainen lähdeviite ei
todista tiedon totuutta tai lähteen aitoutta; puuttuva tieto, null ja nolla pysyvät
erillisinä.
