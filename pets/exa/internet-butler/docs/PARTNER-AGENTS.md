# The butler as one of the partner agents

The butler's own answer is already the work of several partner models. This note is for connecting it to the
company companions (junction-pets) so that they can ask each other for help.

## Ask the butler (any agent, one call)

```
GET  http://127.0.0.1:8787/api/agent/card      what it is, what it asks of others, what stays with the human
POST http://127.0.0.1:8787/api/agent/ask       {"question": "My flight from Helsinki to Paris was cancelled yesterday. What am I owed?"}
```

The reply has `covered`, `answer`, `then` / `now` (amount, date, official URL), `evidence` (quote, pinned URL),
`agreed` / `reviewNeeded`, `asked[]` (who did what), `nextSteps[]` (where to send it, the time limit) and
`needsHuman[]`. When the question is not a dated amount or period it says `covered: false` and points to live
web search. `"private": true` keeps the question on the machine.

## Whom the butler asks in turn

| Partner | Its part in one answer |
|---|---|
| Exa | finds the provision on official domains, announced changes on government sites, the counterparty's claim page, the time limit, news from the day of the event |
| TypeSafe Jev | typed judgments with probabilities: which provision, which clause, does this source serve the need |
| OpenAI Luna (Decisions API) | second clause judge |
| NVIDIA Nemotron on Verda | third clause judge; plans the searches; drafts the cited answer in the general butler |
| Google Gemma 4 E2B with our LoRA, EmbeddingGemma | on-device judge and on-device catalog: the private mode |
| code | reads the statute's outline, computes distances, rules out tiers the stated facts contradict |
| the person | approves before anything is sent |

The app shows this as one line under each answer ("Exa found the provision → EUR-Lex: the text as of … → code …
→ TypeSafe Jev, OpenAI Luna, NVIDIA Nemotron voted → Google Gemma advised → Exa found the next steps → you approve").

## Connecting a companion (junction-pets)

A companion package there is guidance only (`requiresConnection: false`). To give the Exa companion a real
capability, add one that calls `POST /api/agent/ask` and shows `answer`, the official URL and `nextSteps`; the
other companions can reach it the same way ("ask the Exa companion what the rule was on that date"). The reverse
direction exists already: the butler calls TypeSafe, OpenAI, NVIDIA and Google models for their part.

## An arena

`bench/situations/tournament.mjs` is a ready scoring harness for agents that answer the same cases: 1,168
verified situations, accuracy with cluster-bootstrap intervals, paired comparisons, and an "all agree" rule.
Any agent that returns a probability per option (or just a pick) can enter by writing a judgments file in the
student format (`{"k": "student|<situation>|<clause>", "p": 0.83}`). Current table: Jev 93.9 %, Luna 93.5 %,
Nemotron 91.8 %, Gemma 4 E2B with our LoRA 88.8 %, untrained Gemma 71.0 %, word overlap 53.6 %.
