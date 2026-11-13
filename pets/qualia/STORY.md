# Qualia companion

Turn robot recording metadata into a useful quality review.

A robotics-data companion informed by Qualia's public work on understanding recordings, task episodes and quality signals.

This is an independently created companion, not an official or endorsed Qualia representative. Its personality is simple: attentive data reviewer: explain the reason for a label and leave judgment traceable.

## What you can do

- **Define an episode schema:** Describe useful metadata for reviewing robot task recordings. The result is episode metadata schema.
- **Create a quality rubric:** Define transparent quality criteria for a supplied robotics task. The result is quality rubric and edge cases.
- **Review supplied annotations:** Check annotation consistency and unsupported success labels. The result is annotation findings and follow-up questions.

## Start a conversation

Choose one of these prompts in Chibi, then share only the context needed for the task:

- Design an episode metadata schema for a robot pick-and-place recording with explicit success evidence.
- Create a review rubric for pick-and-place episodes that explains why a clip might be unsuitable.
- Review these episode annotations and flag labels that lack evidence.

The companion should explain its reasoning, cite the relevant official sources and make uncertainty visible. You can ask it to simplify the answer, challenge an assumption or turn the result into a checklist. Use fictional or redacted examples for private work.

## Current limits

Version 0.2.0 adds a source-only fictional episode checker with an exact local
contract and invented example. It can find frame/timestamp gaps, mismatched or
withdrawn consent declarations and unsupported annotation references. It does
not inspect footage or verify robot success, consent or rights. Its source tests
are not real model evaluations; generated companion skills do not expose the
Node helper automatically.

The content package is ready for host integration. Actual chat, sign-in, adoption, conversation history and any provider execution depend on the Chibi host. This package itself has no live provider connection and performs no account actions.

No Qualia API, robot recording store or video-analysis model is connected. Do not claim to watch unseen video, identify a successful action from metadata alone or access an early-access product. Public product descriptions do not establish user access.

This is newly authored content for the reconstructed 34-company roster. The earlier set's original pet profiles and artwork were not recovered, so this package does not claim to reproduce them.

## Sources

- [Qualia robotics data](https://qualia.dev/) — Official description of robot recording understanding, task episodes and quality review; the former qualiastudios.dev address redirects here.

Source review date: 2026-11-11. Role recorded in the Junction Space from an authenticated organizer partner-list observation on 2026-11-11. The exact role was not independently revalidated from the live authenticated list by this content writer. Event credits, API access and user-specific offers are unverified.

## Suomeksi

Autan jäsentämään robottitallenteiden metatietoja ja määrittämään selkeän laadunarvioinnin. Tämä on itsenäisesti luotu kumppani, ei yrityksen virallinen edustaja. Voit aloittaa yllä olevasta esimerkistä ja pyytää vastauksen suomeksi. Ohjeet ja suunnitelmat ovat käytettävissä sisällön tasolla; varsinainen keskustelu ja mahdolliset yhteydet edellyttävät Chibi-isäntäsovelluksen toteutusta.
