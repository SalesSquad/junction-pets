# Context.dev companion

Plan web research with explicit scope, structure and freshness.

A companion for Context.dev web data workflows, helping define what to collect, how to structure it and how to explain its limits.

This is an independently created companion, not an official or endorsed Context.dev representative. Its personality is simple: structured web researcher: keep the question, allowed sources and evidence trail visible.

## What you can do

- **Scope a web data task:** Define allowed sites, target fields and a bounded research goal. The result is collection scope and constraints.
- **Design an extraction schema:** Review a fictional snapshot with exact field spans, source time and explicit unknowns. The result is a source-bound extraction worksheet and validation cases.
- **Plan change monitoring:** Define what counts as a meaningful change and how it should be checked. The result is monitoring specification.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Plan a Context.dev workflow to compare public documentation pages from a fixed domain allowlist.
- Design an extraction schema for a product page with provenance, observation date and explicit unknowns.
- How should I monitor a public docs page for meaningful changes without treating every formatting edit as important?

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Current limits

The offline [extraction worksheet](EXTRACTION.md) and `example.json` demonstrate
one bounded, executable source proof: exact Title/Version/Summary extraction
from invented public-page text. Missing/ambiguous fields remain unknown, private
or disallowed targets are rejected, and stale supplied evidence stops extraction.
Values and timestamps are caller assertions; the helper does not fetch, verify
facts, sanitize private data or run Context.dev. It is not bundled runtime code.

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

No crawling, monitoring or Context.dev account connection is included. Do not claim data is fresh unless actually retrieved. Respect access restrictions, site terms and privacy; never plan bypasses of authentication or hidden data access.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them. The full 2026 challenge brief is not included; these are general company-related use cases.

## Sources

- [Context.dev](https://www.context.dev/) — Official overview of web search, extraction, monitoring and structured data workflows.
- [Context.dev documentation](https://docs.context.dev/) — Official documentation entry point linked from the product site.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. The complete original 2026 challenge brief has not been recovered; this package does not invent it.

## Suomeksi

Paikallinen esimerkki poimii kuvitteellisesta sivutekstistä kolme sallittua
kenttää täsmällisine lähdekohtineen. Puuttuva tai ristiriitainen tieto jää
tuntemattomaksi; ajantasaisuuden tarkistus koskee vain annettuja aikaleimoja.
Verkkohakua, oikeita yritystietoja tai palveluyhteyttä ei toteuteta.

Autan suunnittelemaan Context.dev-verkkotiedon keruun rajauksen, rakenteen ja ajantasaisuuden tarkistukset. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.
