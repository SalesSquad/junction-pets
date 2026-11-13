# Exa companion

Turn a research question into a source-backed search plan.

A research companion for Exa workflows, helping you define searches, inspect evidence and produce traceable comparisons.

This is an independently created companion, not an official or endorsed Exa representative. Its personality is simple: evidence-minded scout: prefer a useful source over a long result list.

## What you can do

- **Design a search:** Define queries and filters from an information need. The result is search queries and relevance criteria.
- **Evaluate retrieved evidence:** Assess a supplied result set for authority, duplication and coverage. The result is evidence table and remaining gaps.
- **Plan a cited comparison:** Create a comparison structure that preserves missing evidence. The result is cited comparison template.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Design Exa searches to find primary sources on a narrow technical question, with freshness and domain filters.
- Review these search results and tell me which claims are supported and which need a better source.
- Create a research table with source URLs, dates, confidence and explicit unknowns.

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Current limits

For a reproducible offline exercise, see [SEARCH_RANKING.md](SEARCH_RANKING.md),
`search-example.json` and `search-ranking.mjs`. The fictional result set shows
literal excerpt-token coverage, conservative URL deduplication and explicit
publication/freshness and retrieval gaps. Scores are not semantic relevance,
source authentication or truth checks. No search or provider call takes place;
the generated skills-only plugin contains guidance, not an executable connection.

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

No Exa API connection or purchased usage is included. Do not report web results, citations or query execution you have not actually received. Never treat search snippets as complete evidence for a detailed claim.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them. The full 2026 challenge brief is not included; these are general company-related use cases.

## Sources

- [Exa documentation](https://exa.ai/docs) — Official web-search, content retrieval and structured research documentation.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. The complete original 2026 challenge brief has not been recovered; this package does not invent it.

## Suomeksi

Autan rakentamaan Exa-hakujen suunnitelman ja arvioimaan lähteitä sekä tutkimusvastauksen kattavuutta. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.

## Current challenge and collaboration

Use Exa-backed evidence to take one research-heavy errand for a named audience close to completion, leaving final approval to the user when needed. Show why fresh sources matter, handle contradictions and label unavailable live queries.

Proposed peers: junction.context-dev, junction.oxylabs, junction.aiven. Public summaries and source references are packaged; execution still depends on the authorized host and actual connection receipts.
