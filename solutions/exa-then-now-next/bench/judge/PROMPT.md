# Judge instructions (same for every judge; judges are blind to the query arm)

Each item: `item` (number), `jurisdiction`, `question` (what a person asked), `reference_rule` (the correct legal rule, written by an expert), `url`, `title`, `highlights` (text excerpts retrieved from the page).

Label every item, judging ONLY from the given url, title and highlights:

- `states_rule`: `"yes"` if the highlights explicitly state the rule in `reference_rule` including its decisive number, period or amount (wording may differ); `"partial"` if they discuss the same rule but the decisive number or condition is missing; `"no"` otherwise.
- `contradicts`: `true` only if the highlights state a different number or condition for the same rule in the same jurisdiction; otherwise `false`.
- `source_type`: `"legal_text"` if the page is the text of legislation, a regulation, or a court decision itself (official consolidated versions and official translations included); `"official_guidance"` if it is a government, regulator or EU-institution page explaining the rule; `"secondary"` for law firms, news, blogs, NGOs, consumer associations, claim companies, encyclopedias; `"other"` otherwise.
- `jurisdiction_match`: `true` if the page concerns the item's jurisdiction.

Output: a JSON array with one object per item, in input order: `{"item": <number>, "states_rule": "...", "contradicts": <bool>, "source_type": "...", "jurisdiction_match": <bool>}`.
