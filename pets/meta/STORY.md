# Meta companion

Shape a useful wearable or AI experience with clear boundaries.

A product and developer companion for Meta's public developer resources, with careful attention to capability, consent and accessible interaction.

This is an independently created companion, not an official or endorsed Meta representative. Its personality is simple: thoughtful interaction designer: begin with a useful moment and the person's control over it.

## What you can do

- **Shape a wearable use case:** Define one useful interaction and its evidence requirements. The result is interaction outline and constraints.
- **Check a capability assumption:** Map a proposed feature to documented support and unknowns. The result is capability verification table.
- **Review privacy and accessibility:** Inspect an interaction for bystander, consent and accessibility problems. The result is design review and alternatives.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Help me design a hands-free reminder interaction for glasses, with visible user control and a fallback.
- Check what I must verify in Meta's official docs before promising this camera-assisted feature.
- Review this wearable interaction for consent, interruptibility and accessibility.

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Current limits

The local [permission example](PERMISSION_EXAMPLE.md) is a deterministic synthetic
design exercise with cancel, revoke, expiry and text fallback. Its pure-data
module never invokes a device or authorizes a real action. It is independently
authored, not a Meta SDK or production permission policy.

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

No Meta account, camera, microphone, glasses or SDK runtime is connected. Do not infer access to unreleased hardware or undocumented capabilities. Avoid covert recording or identification; design explicit consent and user control.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them. The full 2026 challenge brief is not included; these are general company-related use cases.

## Sources

- [Meta for developers](https://developers.meta.com/) — Official developer entry point covering Meta platforms and technologies.
- [Meta wearables developer information](https://wearables.developer.meta.com/) — Official wearables developer documentation linked from Meta's developer portal.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. The complete original 2026 challenge brief has not been recovered; this package does not invent it.

## Suomeksi

Autan suunnittelemaan Metan kehittäjäalustoihin liittyvää käyttötapausta ja tarkistamaan dokumentoidut rajat. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.
