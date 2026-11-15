"""One reader for the MLX clause judge, shared by the trainer, the scorer and the server.

The judge is read at one position: the prompt ends where the model's answer starts, and the logits of the option
letters there are the answer. Three things must be the same wherever that reading happens, or a trained adapter
is scored on something it never saw:

  the prompt      gpu/prompting.py: choice_content, rendered with the chat template; Gemma 4's thinking switch is
                  passed explicitly (mlx_lm turns it on by default for models that have a thought channel)
  the logits      the output head applied to the last position's hidden state, in float32, WITHOUT the final
                  soft cap (30 * tanh(x / 30)): this is what the adapter was trained on. Calling model(...) instead
                  gives soft-capped bfloat16 logits, which are flatter and tie on a coarse grid
  the options     the first k letters of LETTERS, each a single token
"""
import json, os, sys
import mlx.core as mx
from mlx_lm.models.cache import make_prompt_cache

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gpu"))
from prompting import LETTERS, choice_content  # noqa: E402  (re-exported)


def letter_ids(tok):
    ids = [tok.encode(l, add_special_tokens=False) for l in LETTERS]
    assert all(len(x) == 1 for x in ids), "an option letter is not a single token in this tokenizer"
    return [x[0] for x in ids]


def thinking_of(adapter_path, override=None):
    """Whether the prompt is rendered with the thinking switch on. An adapter is scored the way it was trained
    (adapter_config.json: enable_thinking; adapters from before the key existed were trained with it on);
    without an adapter it is off, as in gpu/prompting.py: chat()."""
    if override in ("on", "off"):
        return override == "on"
    if not adapter_path:
        return False
    try:
        return bool(json.load(open(os.path.join(adapter_path, "adapter_config.json"))).get("enable_thinking", True))
    except (OSError, ValueError):
        return True


def render(tok, situation, clauses, order, thinking, max_tokens=1536):
    text = tok.apply_chat_template([{"role": "user", "content": choice_content(situation, clauses, order)}], tokenize=False, add_generation_prompt=True, enable_thinking=thinking)
    return tok.encode(text, add_special_tokens=False)[-max_tokens:]


def head(lm, h):
    """Uncapped float32 logits over the vocabulary for hidden states h."""
    h = h.astype(mx.float32)
    out = lm.model.embed_tokens.as_linear(h) if lm.tie_word_embeddings else lm.lm_head(h)
    return out.astype(mx.float32)


def option_logits_train(lm, ids, letters, k):
    """For training: the whole prompt in one pass (gradients flow through it), head at the last position."""
    return head(lm, lm.model(ids)[:, -1, :])[0, mx.array(letters[:k])]


def option_logits(model, ids, letters, k):
    """For scoring and serving: prefill the cache with all but the last token (MLX is lazy, so no logits are
    computed for those positions), then the last token alone. Returns k Python floats."""
    lm = model.language_model
    cache = make_prompt_cache(model)
    if len(ids) > 1:
        lm.model(mx.array(ids[:-1])[None], cache=cache)
        mx.eval([c.state for c in cache])
    out = head(lm, lm.model(mx.array(ids[-1:])[None], cache=cache)[:, -1, :])[0]
    sel = out[mx.array(letters[:k])]
    mx.eval(sel)
    return [float(x) for x in sel.tolist()]
