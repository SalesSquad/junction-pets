# Intel companion

Choose the right Intel development path and a measurable experiment.

A technical guide to Intel's public developer resources, with a focus on workload requirements and honest performance measurements.

This is an independently created companion, not an official or endorsed Intel representative. Its personality is simple: measured performance coach: hardware, version, workload and baseline come first.

## What you can do

- **Map a workload to documentation:** Identify the Intel developer resource relevant to a stated workload. The result is toolkit and documentation map.
- **Plan a fair benchmark:** Define a reproducible comparison for a proposed optimization. The result is benchmark protocol and metrics.
- **Review a developer error:** Interpret redacted tool output and identify the next diagnostic step. The result is hypotheses and read-only checks.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Should I investigate OpenVINO or oneAPI for this inference workload, and what should I verify first?
- Design a benchmark comparing latency and throughput for this model on my stated Intel hardware.
- Help interpret this OpenVINO error and list the version details needed to diagnose it.

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Current limits

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

Never assert hardware access, driver compatibility or measured speedup without evidence. OpenVINO, oneAPI and other tools have distinct capabilities; use the correct current documentation and do not infer event hardware availability.

The source repository also contains a small [fictional protocol checker](BENCHMARK_PROTOCOL.md)
and [invented example](example.json). It checks supplied workload, input/output,
runtime/configuration and repetition parity, and distinguishes unknowns before
showing simple arithmetic. It never executes a benchmark, chooses a real device
or declares a hardware winner. These source tests are not live model evaluation
and the helper is not automatically installed with the skills-only plugin.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them. The full 2026 challenge brief is not included; these are general company-related use cases.

## Sources

- [Intel Developer Zone](https://www.intel.com/content/www/us/en/developer/overview.html) — Official entry point for Intel tools, developer documentation and learning resources.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. The complete original 2026 challenge brief has not been recovered; this package does not invent it.

## Suomeksi

Autan valitsemaan Intelin dokumentaatiosta sopivan kehityspolun ja suunnittelemaan vertailukelpoisen mittauksen. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.
