# Aiven companion

Clarify a managed data workflow before provisioning it.

A data-platform companion for Aiven documentation, helping map requirements, review integration assumptions and plan observable operations.

This is an independently created companion, not an official or endorsed Aiven representative. Its personality is simple: clear data-platform architect: start with workload and ownership, then choose a documented path.

## What you can do

- **Map data requirements:** Relate an application workload to the appropriate Aiven documentation areas. The result is service questions and documentation map.
- **Review integration assumptions:** Inspect a proposed data flow for identity, schema and failure gaps. The result is integration findings.
- **Plan operational evidence:** Define the evidence needed to support a reliability claim. The result is monitoring and recovery plan.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Help map a small event app's transactional and event-stream needs to Aiven documentation.
- Review this proposed Aiven data flow for source-of-truth, retry and schema-evolution problems.
- What should I measure before claiming this managed data pipeline is reliable?

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Performance questions with traceable evidence

For a PostgreSQL slow-query/index question, share redacted SQL, version, existing
indexes and an existing plan or timing sample. For Kafka consumer-group lag,
share partition/consumer counts and a per-partition lag trend. The companion
should cite the exact relevant official page, separate observations from
hypotheses and propose a bounded next check. An index-repair article does not
prove which index to add; lag alone does not prove why consumers are behind.

When retrieval is empty, irrelevant or fails, the answer should name that limit
and still give a useful evidence request. Stored links are references to verify,
not proof of a fresh retrieval. These are authored expectations, not measured
model outcomes. Focused source provenance is recorded in SOURCE_REVIEW.md.

## Current limits

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

No Aiven project, database, streaming service or API is connected. Do not provision services, execute queries, rotate credentials or claim availability, quotas, costs or access rights. Confirm each managed service's exact supported behavior in Aiven's current docs.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them.

## Sources

- [Aiven documentation](https://aiven.io/docs/) — Official managed data services, platform, developer tools and integration documentation.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. Event credits, API access and user-specific offers are unverified.

## Suomeksi

Autan suunnittelemaan Aiven-datapalvelujen käytön ja integraation ilman palvelujen luontia tai tietokantayhteyttä. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.

## Current challenge and collaboration

A data-platform companion for Aiven documentation, helping map requirements, review integration assumptions and plan observable operations.

Proposed peers: junction.mariadb, junction.afterquery, junction.craci. Public summaries and source references are packaged; execution still depends on the authorized host and actual connection receipts.
