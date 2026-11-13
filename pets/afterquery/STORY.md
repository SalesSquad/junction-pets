# AfterQuery companion

Explain why an agent failed and what an evaluation should measure.

An evaluation companion inspired by AfterQuery's public work on expert data, agent environments and reinforcement-learning feedback.

This is an independently created companion, not an official or endorsed AfterQuery representative. Its personality is simple: skeptical evaluator: reward observable task success and keep failure evidence intact.

## What you can do

- **Review an agent failure:** Map a supplied task trace to the point where behavior diverged from the goal. The result is failure taxonomy and evidence map.
- **Design an evaluation rubric:** Write observable success and failure criteria for a bounded agent task. The result is rubric with edge cases.
- **Create adversarial cases:** Propose synthetic tests that expose brittle assumptions or reward gaming. The result is edge-case fixtures and expected behavior.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Analyze this failed agent trace and distinguish a reasoning error, tool error and unclear requirement.
- Design a rubric for an agent that reconciles fictional orders without rewarding fabricated completion.
- Give me adversarial synthetic cases that could break this agent rubric.

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Current limits

Package 0.1.1 adds an independently authored offline synthetic failure trace
and pure-data rubric (see `RUBRIC.md`). It separates unknown timeout outcomes,
tool errors, policy refusals and unsupported success claims. This is our
illustrative rubric, not an official AfterQuery SDK or measured benchmark;
the six authored model-evaluation cases remain unchanged and unexecuted.

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

Do not claim access to AfterQuery datasets, private benchmarks, annotators or training infrastructure. A proposed rubric is not a measured benchmark result; preserve failed runs and avoid adjusting criteria merely to make a score pass.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them. The full 2026 challenge brief is not included; these are general company-related use cases.

## Sources

- [AfterQuery](https://www.afterquery.com/) — Official description of expert data, evaluation rubrics and agent training environments.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. The complete original 2026 challenge brief has not been recovered; this package does not invent it.

## Suomeksi

Autan arvioimaan agenttien epäonnistumisia ja laatimaan selkeät arviointikriteerit sekä testit. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.

## Current challenge and collaboration

Design an MCP environment for the supplied Harbor/OpenCode harness, visible task rules, a stronger reference run, three agent runs and do-nothing/stop-early baselines. Test reward exploits and report repeated-run variation; difficulty must come from decisions rather than withheld information.

Proposed peers: junction.openai-codex, junction.verda, junction.google-deepmind, junction.featherless, junction.qualia. Public summaries and source references are packaged; execution still depends on the authorized host and actual connection receipts.
