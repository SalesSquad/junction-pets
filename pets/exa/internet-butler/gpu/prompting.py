"""One prompt and scoring definition for every Python entry point (trainer, server, evaluation).

A model trained with one prompt and scored with another gives wrong probabilities without any error, so the
question text, the clause shortening, the chat rendering and the answer tokens live here only.
"""
QUESTION = "Does `clause` set the amount, rate, limit or time limit that applies to the person in `situation` (the same kind of case, party and circumstances)?"
CHOICE_QUESTION = "Which option sets the amount, rate, limit or time limit that applies to the person in `situation` (the same kind of case, party and circumstances)? Answer with one letter."
LETTERS = "ABCDEFGHIJKLMNOP"
own = lambda c: c.split(" … ")[-1]


def fit(clause, n=900):
    """Shorten a clause to n characters: keep the start of its context chain and the clause itself (the last
    " … " part); when the clause alone is too long, keep its head and tail."""
    if len(clause) <= n:
        return clause
    o = own(clause)
    if len(o) >= n - 40:
        return o[: n // 2] + " … " + o[-(n // 2 - 3):]
    return clause[: n - len(o) - 3].rstrip() + " … " + o


def user_content(situation, clause, ablate=""):
    """Pointwise yes/no prompt. `ablate` withholds one side (shortcut controls: the model should fall to chance)."""
    s = "(withheld)" if ablate == "situation" else situation
    c = "(withheld)" if ablate == "clause" else fit(clause)
    return f"situation: {s}\nclause: {c}\nquestion: {QUESTION}\nAnswer yes or no."


def choice_content(situation, clauses, order=None, ablate=""):
    """Listwise prompt: every sibling clause as a lettered option, in `order` (shuffled in training)."""
    order = list(range(len(clauses))) if order is None else order
    per = max(160, min(600, 3600 // max(1, len(clauses))))
    s = "(withheld)" if ablate == "situation" else situation
    opts = "\n".join(f"{LETTERS[k]}) {'(withheld)' if ablate == 'clause' else fit(clauses[i], per)}" for k, i in enumerate(order))
    return f"situation: {s}\noptions:\n{opts}\nquestion: {CHOICE_QUESTION}"


def chat(tok, content):
    msgs = [{"role": "user", "content": content}]
    try:
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def answer_ids(tok, words=("yes", "no")):
    """Single, distinct token ids for the answer words as they appear right after the generation prompt."""
    ids = []
    for w in words:
        t = tok(w, add_special_tokens=False).input_ids
        assert len(t) == 1, (w, t, "answer word must be one token")
        ids.append(t[0])
    assert len(set(ids)) == len(ids), ("answer tokens must differ", ids)
    return ids
