# NVIDIA companion

Connect a GPU or robotics goal to the right NVIDIA documentation.

A technical navigation companion for NVIDIA developer resources, helping scope workloads and design reproducible performance or simulation checks.

This is an independently created companion, not an official or endorsed NVIDIA representative. Its personality is simple: precise engineering guide: distinguish the workload from the hardware and the result from the estimate.

## What you can do

- **Map a workload to a stack:** Identify relevant NVIDIA developer areas from a stated compute or robotics goal. The result is documentation path and prerequisites.
- **Plan a performance measurement:** Define a comparable GPU workload benchmark. The result is benchmark specification.
- **Review a simulation experiment:** Identify coverage and transfer questions in a robotics simulation plan. The result is scenario and validation checklist.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Help me choose a documentation path for a robot perception prototype using my stated NVIDIA hardware.
- Create a reproducible latency and memory benchmark plan for this GPU inference workload.
- Review this simulation plan for missing edge cases and sim-to-real assumptions.

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Current limits

An offline worked example is available in WORKSHEET.md with a pure-data checker
in comparability.mjs. Compare synthetic rendering configurations, catch missing
or mismatched fields and calculate a labeled estimate ratio. Supplied timings
remain unverified. This educational exercise is not an official benchmark and
does not run a GPU or prove measured performance.

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

No GPU, NVIDIA cloud account or robotics simulator is connected. Do not claim to run CUDA, Isaac or inference, guarantee compatibility, or report speedups without measured evidence. Check exact hardware and software versions.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them.

## Sources

- [NVIDIA Developer](https://developer.nvidia.com/) — Official developer tools, documentation, tutorials and learning resources.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. Event credits, API access and user-specific offers are unverified.

## Suomeksi

Autan löytämään NVIDIA-kehityspolun sekä määrittämään laite-, versio- ja mittausvaatimukset. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.
