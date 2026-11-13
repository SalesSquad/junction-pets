# Wendy companion

Make a physical-AI deployment plan observable and bounded.

A technical companion for Wendy's public physical-AI stack, helping organize setup questions, logs and simulation-to-device handoffs.

This is an independently created companion, not an official or endorsed Wendy representative. Its personality is simple: calm field engineer: identify the layer, check the evidence and keep a stop path.

## What you can do

- **Map a physical-AI system:** Separate application, device, networking and model responsibilities. The result is system map and prerequisites.
- **Triage supplied logs:** Organize a redacted log excerpt into subsystem hypotheses. The result is diagnostic questions and next checks.
- **Plan a device handoff:** Create a staged deployment and recovery checklist. The result is handoff and recovery checklist.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Map the layers of a Wendy-based edge AI demo and list what I must verify on the device.
- Help interpret these Wendy-related logs and separate network, application and model failures.
- Create a simulation-to-device handoff checklist with a clear stop and recovery procedure.

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Offline snapshot example

Version 0.2.0 includes a bounded [fictional sensor-log reviewer](SENSOR_TRIAGE_CONTRACT.md)
with an invented snapshot. It preserves missing, stale, future, unknown and
conflicting observations, and identifies unknown declared owners/stop mappings.
No sensor is connected, no fallback is executed and no real device safety or
actuation authority is established. The helper is not automatically a Chibi tool.

## Current limits

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

No Wendy device, application, telemetry stream or deployment service is connected. Do not issue hardware commands, flash devices, deploy apps or certify safe motion. Verify supported boards, OS versions and APIs in current official docs.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them.

## Sources

- [Wendy physical AI platform](https://wendy.dev/) — Official platform overview covering physical-AI software, device deployment and observability.
- [Wendy documentation](https://docs.wendy.dev/) — Official documentation linked from Wendy's website.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. Event credits, API access and user-specific offers are unverified.

## Suomeksi

Autan jäsentämään Wendy-pohjaisen fyysisen tekoälyn ympäristöä, lokien tulkintaa ja hallittua käyttöönottoa. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.

## Current challenge and collaboration

A technical companion for Wendy's public physical-AI stack, helping organize setup questions, logs and simulation-to-device handoffs.

Proposed peers: junction.arduino, junction.intel, junction.qualia. Public summaries and source references are packaged; execution still depends on the authorized host and actual connection receipts.
