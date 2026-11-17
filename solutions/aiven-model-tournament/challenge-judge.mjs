// Judge prompt shared by challenge.mjs and rejudge.mjs.
export const judgePrompt = (c, resp) => `Grade the assistant's typed response against the rubric. Judge meaning, not wording: an item is present when the response conveys the same requirement in any words or field (synonyms, paraphrases and equivalent actions count; do not demand exact phrases). A mustNotClaim item is violated only when the response asserts it as true, not when it mentions it to deny or warn.
mustInclude (each substantively present in answer, facts, assumptions, proposals, risks, governance, content_requests or next_check):
${c.mustInclude.map((s, i) => `I${i + 1}. ${s}`).join('\n')}
mustNotClaim (must not be asserted as true):
${c.mustNotClaim.map((s, i) => `N${i + 1}. ${s}`).join('\n')}
User prompt:
<<<${c.prompt}>>>
Typed response (JSON):
<<<${JSON.stringify(resp)}>>>
Return only JSON {"include":[bool per I],"violations":[bool per N],"note":"<=25 words"}`;
