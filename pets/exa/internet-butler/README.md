# Internet Butler

**A local-first personal agent that takes errands off people's hands, with sources you can check and permissions you can revoke.**

Built for Junction 2026: Exa's *Internet Butler* challenge. The same project can also be submitted to Google DeepMind's *Best Use of Gemma* tech challenge (on-device Gemma 4) and the CRACI tech challenge (CI on CRACI).

- **Exa** finds current, citable information from the live web (`/search` with highlights).
- **TypeSafe Jev** makes the small, calibrated judgments code needs: route the errand, keep or drop each source, catch prompt injection, check each citation, explain an action's stakes.
- **Gemma 4 E2B on the device** (LiteRT-LM on WebGPU) reads the user's own documents and drafts the reply. Documents never leave the browser. Chrome's built-in Prompt API is the alternative backend.
- **The permission council** is the single choke point for everything that leaves the device or acts for the user. Grants are revocable. Every decision is written to a hash-chained receipt log, so a revoked grant provably blocks the next call.

## Then · Now · Next: the time-aware rights butler

Every assistant answers with today's internet, but a person's rights depend on **the law on the day it happened**. The panel at the top of the app answers with the official text as it stood on that date, shows today's text, names the instrument that changed it and lists changes already published but not yet in force. It then prepares a claim and a signed Warrant that you approve on this device.

- **Measured basis (TimeLaw, `bench/timelaw/`).** 620 claims from 10 official provisions; the gold label is the official text on each date.
  - Checking against today's text accepts **9 %** of claims that were true on their date.
  - Checking against the text on that date: **620/620**.
- **Sources.**
  - Provisions: eCFR versioner (US), legislation.gov.uk point-in-time (UK), EUR-Lex consolidated versions via CELLAR (EU).
  - Amendments: Federal Register rules, the legislation.gov.uk effects feed, and EU consolidated version dates.
  - Discovery: Exa search restricted to official domains, then a registry of known rights, then eCFR search.
- **Code.**
  - `src/timetravel/timetravel.ts`
  - `src/warrant/pointInTime.ts`
  - `src/ui/thenNow.ts`
  - relay routes `/api/timetravel`, `/api/official` (only official point-in-time URLs, cached), `/api/radar/check` and `/api/radar/monitor` (creates an Exa Monitor; its webhook secret stays in memory).
- **How it chooses.**
  - Provision: candidates come from the built-in registry, Exa search on official domains and the on-device semantic catalog; Jev judges each candidate's description against the situation, so Finnish, German and slang questions work. eCFR's own search runs only when no candidate convinces the judge.
  - Clause: a statutory outline parser splits (a)/(1)/(i)/(A) and UK lists. Code then rules out tiers that the stated facts contradict: durations, distances, ages, negated conditions, and residual clauses ("not falling under (a) or (b)").
  - A panel picks among what remains: Jev, Luna (OpenAI Decisions API) and NVIDIA Nemotron each answer **one choice question with all the tiers as options**, so the tiers are read against each other. The probabilities are averaged and every judgment is receipted.
  - The answer is marked **agreed** only when at least two judges voted, none abstained, each judge has a strict first choice (a tie is not a vote) and all of them pick the clause that code allows. Otherwise the app asks the person to read the quoted clause before a claim is prepared. A judge that does not answer in time, refuses or returns no usable probabilities abstains, and then nothing counts as agreed.
- **Gemma on the device, as a judge (`gemma/serve_mlx_decide.py`).** Our own Decisions API: Gemma 4 E2B with a clause-judge LoRA trained here (`gemma/train_mlx_choice.py`, two epochs on 10,500 verified items, 147 minutes on an M5 Pro), served by MLX on 127.0.0.1 behind the same typed contract as the hosted judges; one decision takes about 0.2 s.
  - **Measured** on the verified set below: untrained 71.0 %, with the LoRA 84.3 %, and with the LoRA averaged over three rotations of the option order (what the server does, about 0.2 s) **88.8 %** [84.4, 92.1]. The rotation was chosen on validation (84.0 → 86.1 %); the same averaging lifts the untrained model only to 75.5 %. The hosted judges score 92 to 94 %: it is now 3.0 points [0.0, 6.6] behind Nemotron and about 5 behind Jev and Luna.
  - **Advisor, not a voter.** Next to the hosted panel its vote is shown ("on-device Gemma agrees / differs") but not counted. As a fourth voter it would raise the mean from 95.2 to 96.2 % and cut unanimous answers from 86.3 % to 80.1 % of cases for 98.6 → 98.8 % right: more reviews for the person, hardly fewer errors. `LOCAL_JUDGE_ROLE=panel` makes it vote.
  - **Private mode** ("Keep my situation on this device"). The question goes to no hosted service: the provision is matched on the device (the built-in rights by meaning and by keywords, then the semantic catalog), code rules out tiers, Gemma picks among the rest, and only the public law is fetched. The answer is always marked for review, because it rests on one small model. Tests assert that no search, judge or network call receives the question in this mode.
- **Semantic catalog on the device (`bench/catalog/`).** EmbeddingGemma (300M, MLX) embeds 5,924 amount-bearing CFR provisions once (9 MB of vectors); a local service embeds the person's message as written, in any language, and returns the nearest provisions that existed in the event's year, in about 10 to 25 ms.
  - **Measured** on the 1,200 discovery situations (`bench/catalog/eval_discovery.py`): the right section is in the top 5 for **66.3 %** (English 75.9, German 64.3, Finnish 44.9) and first for 43.8 %; Exa on official domains for the same items: 25.9 % (39.1, 15.1, 4.0) and 16.5 %. A word-overlap baseline (BM25) over the same catalog reaches 45 % (Finnish 9.5 %). Catalog or Exa: 69.2 %.
  - **What this does and does not show.** The catalog is closed: about 5,900 provisions of six CFR titles, one of which is always the answer, and the test situations were written from clauses of those provisions. Exa searches the open web. So the catalog adds recall where it has coverage, above all across languages; it does not replace search. In the app it is one more source of candidates for the judge, and the only search in private mode (its first hit is taken as it is: Gemma asked to choose among the top five did worse, 39.5 % against 43.8 %).
  - **Built-in rights by meaning.** The fourteen built-in rights (EU flight, rail and ferry delay compensation, online withdrawal and the two-year guarantee, GDPR; UK wages and statutory pay; US bumping, card fees, child labour) are embedded by their descriptions too, so private mode recognises them in any language without keyword lists. Calibrated on the simulation questions and 300 benchmark situations: the right built-in right for 16 of 17, none of the 300 other situations misrouted.
  - **Rights search in the app.** "Find a right by meaning" searches the catalog on the device ("työnantaja maksoi alle minimipalkan Englannissa" returns the UK minimum wage regulations first); **Use** runs Then · Now · Next on the provision the person picked.
  - The same model exists as an ONNX export for transformers.js (checked: its query vectors match the MLX index), so a browser could embed the query itself.
- **Am I still in time? (`src/timetravel/verdict.ts`).** For a right that is a time limit (14 days to withdraw from an online purchase, two years of legal guarantee), the butler reads how long ago the person says it happened ("10 päivää sitten", "nach 26 Monaten", "after 18 months"), compares it with the period in the official text and says *still in time* with the last day, or *probably out of time*. Plain code, no model; it says nothing when no elapsed time is stated. **Add to calendar** downloads an all-day `.ics` event with a reminder the day before; months and years never overflow into the next month (31 Jan + 1 month is 28 Feb, the safer day). `/api/agent/ask` returns the same `verdict`.
- **Claim packet (`src/ui/packet.ts`).** One printable, self-contained page (Print → Save as PDF): the situation, the official text then and now with links to the exact versions, whether the judges agreed, the time limit, where to send it (Exa's finds), the claim letter and the Warrant's signature. No script and nothing that loads from the network; every value is escaped.
- **Guards found by probing (15 Nov).** Twelve realistic questions in English, Finnish and German showed three defects, now fixed and tested: a German train delay was answered with the flight regulation (a rail right, Regulation (EU) 2021/782 Art. 19, was added and the flight right no longer matches rail words); a question naming the "federal" tipped wage got the UK minimum wage (a jurisdiction named in the question, such as federal, `$`, `£`, `€`, UK or EU, rules out built-in rights of another jurisdiction; international trips name several and are not gated); and "in March 2024" was read as today (`monthDate`: the middle of the month, only where there is no date field to leave to the person). Also checked and left out: the Montreal Convention baggage limit, because the UK text of the convention on legislation.gov.uk still shows the original 1,000 SDR and the 2019 and 2024 revisions are not in the point-in-time text, so the butler would give a wrong "then".
- **Voice (`src/ui/voice.ts`).** Dictate the situation in English, Finnish or German (the browser's speech service; the panel says where the audio goes), and a full date said aloud fills the date field ("10. kesäkuuta 2019", "June 10th, 2021", "10. Juni 2021"). **Read aloud** speaks the answer with the device's own voices, including the caveat when the judges did not agree.
- **Deep link.** `/?q=<situation>&date=YYYY-MM-DD&run=1&say=1&private=1` starts a question from outside the app: a Siri Shortcut ("Dictate text" then "Open URL"), a launcher or a browser search keyword. This is the hook a native App Intent or Spotlight action would call.
- **Next steps on the live web, with Exa (`src/timetravel/nextSteps.ts`, relay `/api/next-steps`).** Once the amount is known the butler finds what is still missing to act: **where to send the claim** (the counterparty's own page; it becomes the claim's recipient), **the time limit**, and for a disrupted journey **what was reported that day** (a news search bounded to the days around the event). A writer model plans the three searches in the language of the country's official sites, Exa runs them with highlights, and a typed judge keeps only documents that serve the need. Each step shows its title, link, publication date and the sentence that says it. Live example (15 November 2026), from the plain sentence "My Finnair flight from Helsinki to Paris was cancelled yesterday": Finnair's own claim page, and a September 2026 page explaining that the time limit for such claims is unsettled in Finland.
- **One front door.** A question the dated-law engine does not cover (a rent increase in Helsinki, a late train, a restaurant) is handed to the general butler below, which answers from the live web with Exa: search, typed source checks, a drafted answer whose every claim cites a quote, and a message to approve. Without an on-device model the draft comes from a hosted writer (NVIDIA Nemotron) that receives the question and the public sources only, behind its own permission in the council. The engine never answers from a web result its judge rejected.
- **Flights without kilometres.** "From Helsinki to Paris" is enough: the distance is computed between the two cities' main airports (the method Regulation 261/2004 prescribes), with whether both are in the EU/EEA; a route close to a tier boundary is left to the judges. A date in the message ("yesterday", "viime viikolla", "10 June 2021") fills the date field.
- **For other agents (`GET /api/agent/card`, `POST /api/agent/ask`).** One call with a question in plain words returns the dated answer with its official source, who was asked for what (Exa, TypeSafe Jev, OpenAI Luna, NVIDIA Nemotron, Google Gemma on the device, code), the next steps, and what still needs a human. This is how a partner companion can ask the butler for help, and the butler's own answer is already the work of several partner models.
- **Next, beyond the official feeds (`src/timetravel/announced.ts`, relay `/api/announced`).** Changes are often public before any official feed lists them. Exa searches government domains for the last 15 months; code keeps only documents that themselves state a date after today; a judge confirms the document is about this provision. The result is shown apart from the law, with its source, and a Warrant never cites it. Live on 14 November 2026: the UK minimum wage search returns gov.uk's "Minimum wage rates announced for April 2027" (published 28 October 2026).
- **Simulations (`bench/thennow_sim.mjs`, independent oracles from the official text of each date; last run 15 November with the corrected panel rules and the catalog as a candidate source, which found two of the provisions).**

  | Set | Result |
  |---|---|
  | core, 24 scenarios | then 22/22, provision 23/24 (the 24th asks about a date before the law existed and is refused, as it should be); judges unanimous in 20/22, and all 20 are right |
  | held-out, 13 written after the fixes | provision, then and now 13/13; unanimous 10/13, all 10 right (the 3 split answers are also right) |
  | date sweep, 28 dates (US 2017–2026, UK 2016–2026, EU 2006–2024) | 28/28 on every measure, all unanimous |
  | Warrant receivers, all 63 scenarios that build a Warrant (re-run 15 November on the current code) | honest 63/63 accepted; forged amounts 63/63 and date-blind 43/43 rejected |
  | Exa `/answer` on 1,126 dated fill-in questions from the CFR (`bench/exa_study/`) | 45.5 % give the amount in force on the date; 20.2 % give the latest amount instead and 9.1 % the next edition's. The point-in-time lookup, with the clause given: 92.6 %, never the latest or the next edition's amount (9 answers, 0.8 %, gave another amount, 4 of them the previous annual edition's) |

- **Finding the provision, measured (`bench/exa_study/`, `bench/catalog/`; $25.73 of a $30 Exa budget).** One situation per provision, written in English, Finnish or German; the provisions are US ones. "Right section" means the section the situation was written from; in many misses the returned section is as reasonable (for example "Table of wage rates and effective dates" against the expected "Summary" of the same part).

  | Arm | Right section | Right CFR part |
  |---|---|---|
  | Exa, raw situation as the query, top 5, 1,200 provisions | 25.9 % (English 39.1, German 15.1, Finnish 4.0); 16.5 % as the first result | 43.0 % |
  | On-device semantic catalog, same 1,200, top 5 | 66.3 % (75.9, 64.3, 44.9); 43.8 % as the first result | 74.6 % |
  | Catalog or Exa (ten candidates) | 69.2 % | 77.9 % |
  | Paired 300: Exa, raw situation, top 5 | 20.7 % | 33.3 % |
  | Paired 300: Exa Agent with an output schema, told it is a US CFR section and given the event date; one answer | 31.3 % (Finnish 27 %) | 47.0 % |
  | Paired 300: a model rewrites the message into one English legal query with the jurisdiction stated; Exa top 5 | 25.7 % (14.7 % as the first result) | 53.0 % |
  | Paired 300: any of the three Exa arms | 49.7 % | |
  | Paired 300: two stages. Exa (rewritten query) finds the part; Jev and Nemotron pick one of its amount-bearing sections by heading and one sample clause (`two_stage.mjs`, no extra Exa calls) | 24.7 % as a single pick; 46.5 % when the part was found | 53.0 % |
  | Paired 300: two stages or the Exa Agent | 42.3 % | |

  - The sources find different provisions, so the app pools them: registry, Exa and the catalog give candidates, a judge chooses, and eCFR's own search is the last resort.
  - Finding the part is much easier than finding the section. As a single pick the two stages beat search order (24.7 % against 14.7 %) but not the Exa Agent, and a pick with probability 0.8 or more is right only 44 % of the time: not good enough to ship.
  - Limits of the two-stage number: section tables exist for six CFR titles only, so 44 of the 300 items had no candidates; where all returned parts are covered (218 items) it is 28.9 % against 18.8 % for the first search result.
  - An earlier version of the rewrite arm was fed adversarial variants of the messages for 275 of the 300 items (a lookup bug found in review); those rows were re-run on the base messages and the old ones are kept as `rewrite_discovery_given.attacked.jsonl`.

- **Datasets.** Built only from official point-in-time sources. Each table is zstd Parquet with the pinned official URL; a copy is in iCloud under `Events/Junction-2026/Datasets`.

  | Dataset | Contents |
  |---|---|
  | CFR-Annual focused (`gpu/cfr_annual/`) | GovInfo annual CFR editions 1996–2026 for titles 12, 14, 16, 20, 29 and 49: 107,383 section-years, 346,588 amount clauses, 37,714 series, 3,029 changes (2,941 plausible) |
  | CFR-Annual civil penalties | All titles, 2014–2026: 1,501 section-years, 6,905 clauses, 2,253 changes |
  | UK-EU-Rates (`bench/datasets/uk_eu_rates.mjs`) | 27 provisions read twice a year, 2004–2026: wages, statutory pay, caps, deposit and late-payment tiers, UK261 (EUR → GBP), EU rail, sea and bus delay tiers, roaming, de minimis: 4,188 rows, 292 changes |
  | AmountAtlas (`bench/atlas/build_atlas.mjs`) | The eCFR versioner, section versions with exact dates since 2017 |
  | TimeLaw-Situations (`bench/situations/`, `gpu/generate_situations.py`) | 26,019 situations whose correct clause is known by construction, in English, Finnish and German, with seven adversarial rewrites. Written by Qwen3-30B-A3B (Verda A100; one prompt that lists the clauses and tells the writer not to copy their wording or state the amount) and Claude Haiku 5.5 (Batch API; a fact sheet and the message in one call that also lists the clauses, with the same instruction). The writers saw the clauses, so messages can echo clause wording: word overlap alone picks the right clause for 54 % of the verified set against 32 % by chance. Each item is then answered blind by other model families (Nemotron, Haiku); 13,809 are recovered by the writer and by every other family asked (tier `clean`). Split by clause-template cluster (628 clusters): train 20,075, valid 1,996, test 3,948; test and validation items that share any clause wording with training, boilerplate included, are dropped (351 items) |

- **Judges, measured (`bench/situations/tournament.mjs`).** Intervals are 95 % bootstraps over clause-template clusters.

  *Verified set (dataset v3):* 1,168 situations from 65 clusters, chance 32 %. Each label is known by construction and was recovered blind by two model families that are not judges here (Qwen3-30B, which wrote every item of this set, and Claude Haiku 5.5). That selection makes the set easier than arbitrary messages, so read these as "when the situation is clear to two other models". Results: `bench/results/tournament-v3-indep-all.json`.

  | Judge, one choice question over all tiers | Right clause |
  |---|---|
  | Word overlap (no model) | 53.6 % |
  | Gemma 4 E2B on the device, untrained | 71.0 % [65.8, 75.1] (75.5 % with three option orders) |
  | Gemma 4 E2B on the device, with our LoRA | 84.3 % [79.3, 87.8] |
  | Gemma 4 E2B on the device, with our LoRA, three option orders averaged | 88.8 % [84.4, 92.1] |
  | Nemotron 3.5, zero-shot, token log-probabilities | 91.8 % [89.3, 93.8] |
  | Luna | 93.5 % [90.6, 95.6] |
  | Jev | 93.9 % [90.9, 96.0] |
  | Mean of the three hosted judges | 95.2 % [92.4, 97.2] |
  | **Signing rule: all three hosted judges agree, each with a strict first choice, and code allows the clause** | **86.3 % of cases, 98.6 % right [97.4, 99.5]** |

  The three hosted judges are statistically indistinguishable here (Jev − Luna 0.4 [−1.5, 2.1]; Nemotron − Jev −2.1 [−3.9, 0.2]). Where word overlap picks the wrong clause (725 items) they still reach 90 to 91 %. Finnish and German score like English (92 to 95 %).

  *Older, harder set:* 906 situations, 127 clusters. On a blind re-read the writer (Qwen3-30B) did not recover its own label for 40 % of them (363), and the set predates the cluster split.

  | Judge | All 906 | 543 the writer itself recovered |
  |---|---|---|
  | Word overlap | 45.4 % | |
  | Jev, one yes/no per clause | 62.2 % | 77.3 % |
  | Luna, one yes/no per clause | 59.6 % | 70.9 % |
  | Jev, one choice question | 73.9 % | 87.8 % |
  | Luna, one choice question | 74.2 % | 87.8 % |
  | Nemotron, one choice question | 73.1 % | 89.4 % |
  | Mean of the three choice judges | 75.8 % | 89.9 % |

  - **The question form matters more than the model.** Asking once over all tiers instead of once per clause: Jev +11.7 points [7.3, 19.7], Luna +14.6 [8.7, 22.6], paired on the same items (Luna answered 630 of the 906 yes/no items and gets chance credit on the rest; on the items it answered its gain is +4.9 [0.4, 12.2]).
  - **Signing rule on the older set** (scored before ties were excluded): 76.6 % of cases, 82.6 % right [75.0, 87.7], 94.9 % [89.9, 97.6] on the 543 self-consistent items. Unclear cases go to the person.
  - **Trained small judges.** Qwen3-1.7B with LoRA (one yes/no per clause, Verda A100) reached 64.3 % on the older set: not significantly better than Jev asked the same way (+2.1 [−3.4, 12.3]); its adapters were lost with the VM. Gemma 4 E2B with LoRA on the choice question, trained locally with MLX, is the on-device judge above (88.8 % on the verified set with three option orders averaged); details in `gemma/TRAINING.md`.
  - Students are trained only on labels known by construction. No Jev or Luna output is used as a training label (TypeSafe's terms do not allow training on Jev output).
- **Red team (`docs/ATTACKS.md`).** Seven breaks are fixed with regression tests:
  - two that let a false claim pass the Warrant receiver: date substitution, and a sibling tier's amount;
  - five in parsing and code facts.
- **Why pinning matters.** The receiver re-fetches the pinned official version and verifies the quote by code, so the claim is ACCEPTED. Reading today's page instead, the same Warrant is REJECTED because the amount has changed. The panel demonstrates both.
- **Live examples:**

  | Case | Then | Now | Changed by |
  |---|---|---|---|
  | US bumped domestic flight, 2021-06-10, 3 h late (14 CFR 250.5) | cap $1,550 | $2,150 | Federal Register rule effective 2025-01-22 |
  | UK national living wage on 2023-06-15 | £10.42 | £12.71 | the 2024, 2025 and 2026 amending SIs |
  | EU261 Art. 7, flight of 1,500 km or less | EUR 250 | EUR 250 | unchanged |
  | UK national living wage, what comes next | | | gov.uk announcement of 28 October 2026: new rates from April 2027 (announced, not law yet) |

**Demo (2 minutes).**
1. Pick an example and press **Find the law on that date**. Then, Now, Why and Next appear, each linked to an official version, with a chip that says whether all judges agree. Press **Search announced changes (Exa)** on the UK example to see what is coming.
2. Press **Prepare claim and Warrant**, then **Approve with this device and send**. The simulated receiver re-fetches the pinned version and accepts; the ledger reads proposed → approved → executed.
3. Press **What if the receiver read today's page instead?** The receiver rejects.
4. Press **Watch this rule**, then **Changes in the last year**. The radar lists amendments in force and any upcoming ones. With `EXA_API_KEY` and a public `EXA_WEBHOOK_URL`, **Create Exa Monitor** subscribes to official change sources, and signed deliveries appear live.

## Why this shape fits the judging

Exa's five criteria (from the challenge page), and where each is met:

| Exa criterion | How the butler answers it |
| --- | --- |
| Exa for information that could not come from training data | Announced, not-yet-in-force changes found on government sites (gov.uk, 28 October 2026: the April 2027 wage); next steps (the counterparty's claim page, the time limit, news from the day of the event); provisions found on official domains; the general butler's sources, with a typed `needs_fresh_web` check per errand. Measured in three studies of Exa on dated and multilingual questions. |
| Useful to a specific group of real people | People who are owed money under the rule that applied on a given day: passengers whose flight was cancelled, delayed or overbooked first, underpaid workers second. |
| Shows its sources clearly | The official text as of the date, pinned and quoted; every Exa source with its link, publication date and the sentence used; every drafted claim checked against its quote. |
| Originality | Time-aware answers (then, now, next); a signed Warrant the receiver can re-check; three judges that must agree; a private mode where Gemma decides on the device; an on-device catalog. |
| Works on live queries the judges try | A plain sentence is enough (date and distance are worked out); what the dated-law engine does not cover goes to the general butler, which answers from the live web. Checked on flight questions in English, Finnish and German and on rent, train, return and restaurant questions. |
| Gets the task as close to done as possible | The claim is drafted, the recipient is the counterparty's real page, the time limit is shown; after approval: open the claim page, copy the claim, download the Warrant. Nothing is sent without the person. |

## Pipeline

```
browser (local-first)                                         relay (holds keys, stores nothing)
──────────────────────────────────────────────────            ─────────────────────────────────
1 read errand + document on device (Gemma 4 / rules)
2 route errand ───────────── council ── redact ─────────────▶ TypeSafe Jev  choice + noul
3 search live web ────────── council ── redact ─────────────▶ Exa /search   highlights
4 judge each result ──────── council ── redact ─────────────▶ Jev: usable · authoritative · injection · new info
5 draft answer + message on device (Gemma 4 / extractive)
6 citations: exact quote match on device, then ──────────────▶ Jev: supports / contradicts / says nothing
7 explain stakes ─────────── council ── redact ─────────────▶ Jev: side effect · hard to undo
8 user clicks Approve ─────── council (action.send) ──▶ opens the user's mail app; the user sends
```

Every value in the UI carries how it was produced: `LIVE`, `REPLAYED`, `SYNTHETIC` or `OFFLINE_DETERMINISTIC`. Without a model or keys, each step falls back to deterministic code and says so.

Two ideas from our Exa analysis are built in at small scale:

- **Information-gain ranking.** The `r*_novel` question asks whether a source adds a fact not already in `known_facts`, and the answer feeds the ranking.
- **Outcome learning.** The domains cited in approved or rejected messages adjust future rankings on this device only.

## Run it

```bash
npm install
npm run dev          # relay on 127.0.0.1:8787 + Vite on http://localhost:5173
```

**Live search works without any key.** Without `EXA_API_KEY`, the relay uses Exa's keyless MCP tier (`web_search_exa` on `https://mcp.exa.ai/mcp`). That tier is rate-limited and returns highlights only, so the UI labels it "keyless MCP". It needs a direct IPv4 connection; behind an HTTPS proxy the dev script sets `NODE_USE_ENV_PROXY=1`. Set `EXA_MCP_FALLBACK=0` to disable it.

Full live mode adds keys on the relay. The keys are never sent to the browser. Load them from the Keychain at launch:

```bash
EXA_API_KEY="$(security find-generic-password -s salesquad.junction2026.exa -w)" \
TYPESAFE_API_KEY="$(security find-generic-password -s salesquad.junction2026.typesafe -w)" npm run dev
```

For Then · Now · Next with every part running, start the two on-device services first; the dev script picks them up when they answer on their ports:

```bash
npm run judge:local      # Gemma 4 E2B + our clause-judge LoRA (MLX) on 127.0.0.1:8790; needs adapters/gemma4-e2b-choice
npm run catalog:local    # EmbeddingGemma semantic catalog (MLX) on 127.0.0.1:8791; needs bench/catalog/out (build_catalog.py)
npm run dev:live         # relay + app; Exa and Nemotron keys are read from the Keychain for this process only
```

Alternatively, put them in `.env.local`, which is gitignored (see `.env.example`). Exa's workshop code `EXACHALLENGE50` applies challenge credits via the QR code on their slides.

On-device model: click **Load Gemma 4 E2B**. The first load downloads about 2.3 GB, which the browser then caches; LiteRT's WebAssembly comes from jsDelivr by default. This needs WebGPU (recent Chrome or Edge on a laptop with a GPU). **Use Chrome built-in model** uses Gemini Nano through the Prompt API. That needs 22 GB of free disk and a capable GPU, and it does not count as Gemma.

```bash
npm test             # 97 tests: council, citations, pipeline, relay, Then · Now · Next, panel, Warrant, voice
npm run typecheck
npm run build
```

## Demo script (3 minutes)

1. Paste a real errand and a document (a lease, or a delayed-flight confirmation). Show that the document stays local: **What left this device** lists field names and bytes only.
2. Run it. Walk the timeline: route, live Exa sources, a dropped injection or low-quality source, verified citations.
3. Edit the drafted message and click **Approve and send**. The mail app opens with the message.
4. Set **Search the web** to `deny` and run again. The search is blocked before any request, and receipt #n shows it. Then set **Send on my behalf** to `deny` and try to approve. It is blocked too.
5. Close on the receipt chain ("intact") and the privacy claim.

## Status (14 November 2026)

| Verified | Not yet verified |
| --- | --- |
| `tsc` strict typecheck, Vite production build, 12/12 Node tests (pipeline against a fake relay and offline) | Live Exa via the keyless MCP tier: an EU flight-delay errand returned europa.eu and EUR-Lex sources, and the draft quoted them verbatim. Exa REST and TypeSafe with real keys are not tested yet. |
| Synthetic demo in a browser: injection dropped, citations verified, council revoke blocks approval with receipts | Gemma 4 E2B and Prompt API inference in the browser (not downloaded during development) |
| Relay without keys: health, 503s, 404, body limit | Exa Monitors webhook delivery (relay forwards `/api/webhooks/exa` to `/api/events` SSE; creation call not wired) |

## Warrant Compiler and the trust layer (algorithm work, 14 Nov 2026)

`src/warrant/`, `src/authority/`, `src/memory/` and `relay/zk/` implement the proof-carrying request stack:

- **Two-lane compiler.**
  - The answer lane extracts grounded premises: thresholds, outcomes and tiered rules.
  - The authority lane runs citation-completion queries.
  - Role-aware triangulation checks each premise against re-fetched legal text, plus a three-way check against model memory.
  - Clarifying questions replace guesses.
- **Signed Warrant artifact and receiver verifier.**
  - Mandate scope, validity and revocation.
  - Quotes re-fetched verbatim.
  - Compiler provenance (commit and SBOM digest).
- **Zero-knowledge private facts.** Example: "household income <= the verified legal limit", proven with Kättely's Ristretto255 range proofs. The limit is bound to a verified public premise. The proof is bound to the receiver and mandate. It is self-attested until an issuer signs the commitment.
- **Action authority** (BankMatch ADR-002).
  - Independent propose, approve and execute actions.
  - Device-signed approvals bound to the proposal digest.
  - Idempotent execution and a hash-chained ledger.
- **Evidence memory** (ECRE records, JUURI-style HLC journal, SAMPO-style hybrid retrieval).
  - It holds verified claims only, each with a validity window.
  - A changed source triggers re-verification.
  - A JSONL journal persists it.

Demos:
- `node bench/warrant-demo.mjs --offline`
- `node bench/benefits-demo.mjs`, which needs python3, libsodium and a Kättely checkout at `KATTELY_PATH`

Evaluations: `bench/eval_*.mjs` and the `bench/*.md` reports.

## Next steps

- **Monitors.** Create an Exa monitor for "watch this deadline or price" via the relay, and judge each delivery with Jev noul questions (new? relevant? injection?) before alerting.
- **Contents.** When the user pastes a URL, read it with `/api/exa/contents` (relay endpoint exists) and treat it as a local document.
- **Agent API and Connect.** For multi-step errands such as flight rebooking (Jinko live fares), hand the task to `POST /agent/runs` and keep the council and citation checks around it.
- **Chibi Council.** Map `Capability` and receipts onto Chibi grants (Cedar PDP/PEP) once the host is verified in a run.
