# Two-minute judge walkthrough

**0–15 seconds — Problem:** “AI writes code faster than reviewers can read every line. An AI summary may be persuasive while having no evidence. We need earned trust, with a person accountable.”

**15–35 seconds — Real change, honest boundary:** Show Tieto's official MessagePack example issue #2283: exact upstream base `32258fd…`, head `9df83c…`, four changed files. The code provenance is real; our sample check outcomes are synthetic because we have not run the .NET tests.

**35–60 seconds — Claim ledger:** Run `node demo.mjs`. Show the requirement ID, declared source SHAs, two AI-like claims and their check references. Explain that one claimed test is fail-on-base/pass-on-head, the other pass-on-both.

**60–85 seconds — The refusal:** Highlight `NON_DISCRIMINATING_CHECK` for the second claim. Both claims are also flagged `SYNTHETIC_ONLY`. An impressive summary cannot turn either into verified evidence.

**85–105 seconds — Human remains accountable:** Show `humanReviewSet` and the pending reviewer decision. The tool does not merge, verify signatures or make a privileged approval. A future actual log must be independently checked by a named person.

**105–120 seconds — Measurement & next:** Show measured local rule-check counts from the actual Node test report, not invented C# outcomes. Next step: run the official C# sample on base/head, capture logs, and compare false reassurance rates and human review effort against a plain summary.
