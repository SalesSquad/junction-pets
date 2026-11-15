"""Schema-constrained greedy decoding through the one constraint hook plain Transformers has.

The research step found that Transformers has no JSON-schema decoding of its own; its hook is
`prefix_allowed_tokens_fn` (PrefixConstrainedLogitsProcessor): at every step a function returns the
token ids that may come next. Something has to compute those ids from the schema. Two engines are
offered behind the same hook, and the one actually used is recorded with every evaluation:

- "native-dfa" (this file, no extra dependency): the JSON schema is compiled to a regular expression
  over characters, the expression is run as an automaton with Brzozowski derivatives, and a token is
  allowed when all of its characters keep the automaton alive. It emits compact JSON with keys in
  schema order, i.e. exactly the canonical text the adapter is trained on. Supported schema subset:
  object (fixed key order), array (minItems/maxItems), enum, const, anyOf/oneOf, boolean, null,
  integer, and string with an anchored `pattern` (literals, classes, groups, |, ?, *, +, {m,n}).
- "lm-format-enforcer" (optional library): used when it is installed and the native engine cannot
  compile the schema. Its handling of `pattern` was not verified by the research step.

If neither is available the caller falls back to unconstrained decoding with tolerant parsing.
A constraint makes the output well-formed, not correct: confidence is still taken from the model's
unconstrained token probabilities (see evaluate.py).

Everything in this file except `LMFEConstraint` is pure Python and is unit-tested without a model.
"""

from __future__ import annotations

import json
import re

NULL = 0
EPS = 1
DIGITS = "0123456789"
WORD = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
# Characters a free (pattern-less) JSON string may contain here: printable ASCII without the quote
# and the backslash, plus the Finnish letters. No escapes are generated.
STRING_CHARS = "".join(chr(c) for c in range(0x20, 0x7F) if chr(c) not in '"\\') + "äöåÄÖÅ"
_BYTE_TOKEN = re.compile(r"<0x[0-9A-Fa-f]{2}>")


class Unsupported(ValueError):
    """The schema or pattern uses something the native engine does not implement."""


class Automaton:
    """Regular expressions as interned nodes, run by Brzozowski derivatives (lazily built DFA)."""

    def __init__(self):
        self._nodes = [("null",), ("eps",)]
        self._ids = {("null",): NULL, ("eps",): EPS}
        self._nullable = {}
        self._deriv = {}
        self._first = {}

    def _mk(self, node):
        i = self._ids.get(node)
        if i is None:
            i = len(self._nodes)
            self._nodes.append(node)
            self._ids[node] = i
        return i

    # ---- constructors ---------------------------------------------------------------------
    def chars(self, cs):
        cs = frozenset(cs)
        return self._mk(("set", cs)) if cs else NULL

    def lit(self, text):
        return self.seq(*[self.chars(c) for c in text])

    def seq(self, *parts):
        out = EPS
        for p in reversed(parts):
            out = self._seq2(p, out)
        return out

    def _seq2(self, a, b):
        if a == NULL or b == NULL:
            return NULL
        if a == EPS:
            return b
        if b == EPS:
            return a
        items = []
        while self._nodes[a][0] == "seq":  # keep sequences right-nested, without recursion
            items.append(self._nodes[a][1])
            a = self._nodes[a][2]
        items.append(a)
        out = b
        for p in reversed(items):
            out = self._mk(("seq", p, out))
        return out

    def alt(self, *parts):
        items = set()
        for p in parts:
            if p == NULL:
                continue
            node = self._nodes[p]
            if node[0] == "alt":
                items |= node[1]
            else:
                items.add(p)
        if not items:
            return NULL
        if len(items) == 1:
            return next(iter(items))
        return self._mk(("alt", frozenset(items)))

    def star(self, a):
        if a in (NULL, EPS):
            return EPS
        if self._nodes[a][0] == "star":
            return a
        return self._mk(("star", a))

    def opt(self, a):
        return self.alt(a, EPS)

    def repeat(self, a, lo, hi):
        """a{lo,hi}; hi=None means unbounded."""
        if lo < 0 or (hi is not None and hi < lo):
            raise Unsupported(f"bad repetition bounds {lo},{hi}")
        head = [a] * lo
        if hi is None:
            return self.seq(*head, self.star(a))
        tail = EPS
        for _ in range(hi - lo):
            tail = self.opt(self.seq(a, tail))
        return self.seq(*head, tail)

    # ---- semantics ------------------------------------------------------------------------
    def nullable(self, n):
        hit = self._nullable.get(n)
        if hit is not None:
            return hit
        start = n
        while self._nodes[n][0] == "seq":
            if not self.nullable(self._nodes[n][1]):
                self._nullable[start] = False
                return False
            n = self._nodes[n][2]
        node = self._nodes[n]
        kind = node[0]
        if kind in ("eps", "star"):
            out = True
        elif kind == "alt":
            out = any(self.nullable(x) for x in node[1])
        else:  # null, set
            out = False
        self._nullable[start] = out
        return out

    def deriv(self, n, c):
        key = (n, c)
        hit = self._deriv.get(key)
        if hit is not None:
            return hit
        node = self._nodes[n]
        kind = node[0]
        if kind == "set":
            out = EPS if c in node[1] else NULL
        elif kind == "seq":
            a, b = node[1], node[2]
            out = self._seq2(self.deriv(a, c), b)
            if self.nullable(a):
                out = self.alt(out, self.deriv(b, c))
        elif kind == "alt":
            out = self.alt(*[self.deriv(x, c) for x in node[1]])
        elif kind == "star":
            out = self._seq2(self.deriv(node[1], c), n)
        else:  # null, eps
            out = NULL
        self._deriv[key] = out
        return out

    def first_chars(self, n):
        """Characters that can come next from this state."""
        hit = self._first.get(n)
        if hit is not None:
            return hit
        node = self._nodes[n]
        kind = node[0]
        if kind == "set":
            out = node[1]
        elif kind == "seq":
            out = self.first_chars(node[1])
            if self.nullable(node[1]):
                out = out | self.first_chars(node[2])
        elif kind == "alt":
            out = frozenset().union(*[self.first_chars(x) for x in node[1]])
        elif kind == "star":
            out = self.first_chars(node[1])
        else:
            out = frozenset()
        self._first[n] = out
        return out

    def walk(self, n, text):
        for ch in text:
            n = self.deriv(n, ch)
            if n == NULL:
                return NULL
        return n

    def matches(self, n, text):
        return self.nullable(self.walk(n, text))


# ---- regular-expression subset used by JSON-schema `pattern` -------------------------------------


def parse_pattern(A, pattern, universe=STRING_CHARS):
    """Compile an anchored pattern (^...$) from a small regex subset into an automaton node."""
    if not (pattern.startswith("^") and pattern.endswith("$")):
        raise Unsupported("pattern must be anchored with ^ and $")
    src = pattern[1:-1]
    pos = 0

    def peek():
        return src[pos] if pos < len(src) else ""

    def take():
        nonlocal pos
        ch = src[pos]
        pos += 1
        return ch

    def escape(ch):
        if ch == "d":
            return set(DIGITS)
        if ch == "w":
            return set(WORD)
        if ch.isalnum():
            raise Unsupported(f"escape \\{ch} is not supported")
        return {ch}

    def char_class():
        chars = set()
        if peek() == "^":
            raise Unsupported("negated character classes are not supported")
        while peek() != "]":
            if not peek():
                raise Unsupported("unterminated character class")
            ch = take()
            if ch == "\\":
                chars |= escape(take())
                continue
            if peek() == "-" and pos + 1 < len(src) and src[pos + 1] != "]":
                take()
                hi = take()
                if hi == "\\":
                    hi = take()
                if ord(hi) < ord(ch):
                    raise Unsupported("bad character range")
                chars |= {chr(x) for x in range(ord(ch), ord(hi) + 1)}
            else:
                chars.add(ch)
        take()
        return A.chars(chars)

    def atom():
        ch = take()
        if ch == "(":
            if src.startswith("?:", pos):
                take(), take()
            elif peek() == "?":
                raise Unsupported("only (?:...) groups are supported")
            node = alternation()
            if peek() != ")":
                raise Unsupported("unbalanced parenthesis")
            take()
            return node
        if ch == "[":
            return char_class()
        if ch == "\\":
            return A.chars(escape(take()))
        if ch == ".":
            return A.chars(universe)
        if ch in "*+?{":
            raise Unsupported(f"nothing to repeat at {pos}")
        if ch in "^$":
            raise Unsupported("anchors inside a pattern are not supported")
        return A.chars(ch)

    def repeat():
        nonlocal pos
        node = atom()
        while peek() and peek() in "*+?{":
            ch = take()
            if ch == "*":
                node = A.star(node)
            elif ch == "+":
                node = A.seq(node, A.star(node))
            elif ch == "?":
                node = A.opt(node)
            else:
                end = src.find("}", pos)
                if end < 0:
                    raise Unsupported("unterminated {m,n}")
                body = src[pos:end]
                m = re.fullmatch(r"(\d+)(?:(,)(\d*))?", body)
                if not m:
                    raise Unsupported(f"bad repetition {{{body}}}")
                lo = int(m[1])
                hi = lo if not m[2] else (int(m[3]) if m[3] else None)
                node = A.repeat(node, lo, hi)
                pos = end + 1
            if ch != "?" and peek() == "?":
                raise Unsupported("lazy quantifiers are not supported")
        return node

    def concat():
        parts = []
        while peek() and peek() not in "|)":
            parts.append(repeat())
        return A.seq(*parts)

    def alternation():
        options = [concat()]
        while peek() == "|":
            take()
            options.append(concat())
        return A.alt(*options)

    node = alternation()
    if pos != len(src):
        raise Unsupported(f"unexpected {src[pos]!r} at {pos}")
    return node


# ---- JSON-schema subset → automaton ---------------------------------------------------------------


def _dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def compile_schema(A, schema):
    """Compile a JSON schema (subset) to the language of its compact, key-ordered JSON texts."""
    if not isinstance(schema, dict):
        raise Unsupported("schema must be an object")
    if "const" in schema:
        return A.lit(_dumps(schema["const"]))
    if "enum" in schema:
        return A.alt(*[A.lit(_dumps(v)) for v in schema["enum"]])
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return A.alt(*[compile_schema(A, s) for s in schema[key]])
    for key in ("allOf", "not", "if", "$ref", "patternProperties", "propertyNames"):
        if key in schema:
            raise Unsupported(f"schema keyword {key} is not supported")
    kind = schema.get("type")
    if isinstance(kind, list):
        return A.alt(*[compile_schema(A, {**schema, "type": k}) for k in kind])
    if kind == "object":
        props = list(schema.get("properties", {}).items())
        required = set(schema.get("required", [k for k, _ in props]))
        compiled = [(k, compile_schema(A, s), k in required) for k, s in props]

        def members(i, first):
            if i == len(compiled):
                return EPS
            key, value, needed = compiled[i]
            present = A.seq(A.lit(("" if first else ",") + _dumps(key) + ":"), value, members(i + 1, False))
            return present if needed else A.alt(present, members(i + 1, first))

        return A.seq(A.lit("{"), members(0, True), A.lit("}"))
    if kind == "array":
        if "items" not in schema or not isinstance(schema["items"], dict):
            raise Unsupported("array needs a single items schema")
        item = compile_schema(A, schema["items"])
        lo = int(schema.get("minItems", 0))
        hi = schema.get("maxItems")
        hi = None if hi is None else int(hi)
        if hi == 0:
            return A.lit("[]")
        more = A.seq(A.lit(","), item)
        if lo == 0:
            body = A.opt(A.seq(item, A.repeat(more, 0, None if hi is None else hi - 1)))
        else:
            body = A.seq(item, A.repeat(more, lo - 1, None if hi is None else hi - 1))
        return A.seq(A.lit("["), body, A.lit("]"))
    if kind == "string":
        if "pattern" in schema:
            if "minLength" in schema or "maxLength" in schema:
                raise Unsupported("pattern combined with length bounds is not supported")
            inner = parse_pattern(A, schema["pattern"])
        elif schema.get("format") == "date":
            inner = parse_pattern(A, r"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
        elif "format" in schema:
            raise Unsupported(f"string format {schema['format']!r} is not supported")
        else:
            lo = int(schema.get("minLength", 0))
            hi = schema.get("maxLength")
            inner = A.repeat(A.chars(STRING_CHARS), lo, None if hi is None else int(hi))
        return A.seq(A.lit('"'), inner, A.lit('"'))
    if kind == "integer":
        lo, hi = schema.get("minimum"), schema.get("maximum")
        bound = max(abs(int(x)) for x in (lo, hi) if x is not None) if (lo is not None or hi is not None) else 999999
        digits = max(1, len(str(bound)))
        natural = A.alt(A.lit("0"), A.seq(A.chars("123456789"), A.repeat(A.chars(DIGITS), 0, digits - 1)))
        if lo is not None and int(lo) >= 0:
            return natural  # range limits beyond the digit count are checked after decoding
        return A.seq(A.opt(A.lit("-")), natural)
    if kind == "boolean":
        return A.alt(A.lit("true"), A.lit("false"))
    if kind == "null":
        return A.lit("null")
    raise Unsupported(f"schema type {kind!r} is not supported")


# ---- tokens -------------------------------------------------------------------------------------


class TokenIndex:
    """Text of every ordinary vocabulary token, grouped by first character."""

    def __init__(self, tokenizer):
        vocab = tokenizer.get_vocab()
        skip = set(getattr(tokenizer, "all_special_ids", None) or [])
        skip |= set(getattr(tokenizer, "added_tokens_decoder", None) or {})
        self.text = {}
        self.by_first = {}
        for piece, token_id in vocab.items():
            if token_id in skip or not piece or _BYTE_TOKEN.fullmatch(piece):
                continue
            text = piece.replace("▁", " ")  # SentencePiece word-boundary marker
            self.text[token_id] = text
            self.by_first.setdefault(text[0], []).append((token_id, text))


class NativeConstraint:
    """Allowed next tokens for a compiled schema, tracked per batch row during greedy decoding."""

    backend = "native-dfa"

    def __init__(self, tokenizer, schema, stop_ids, pad_id, tokens=None):
        self.A = Automaton()
        self.root = compile_schema(self.A, schema)
        if self.root == NULL:
            raise Unsupported("schema admits no output")
        self.tokens = tokens or TokenIndex(tokenizer)
        self.stop_ids = list(stop_ids)
        if not self.stop_ids:
            raise Unsupported("no stop token")
        self.pad_id = self.stop_ids[0] if pad_id is None else pad_id
        self._allowed = {}
        self._rows = {}
        missing = [c for c in self.A.first_chars(self.root) if c not in self.tokens.by_first]
        if missing:
            raise Unsupported(f"vocabulary has no token starting with {missing!r}")

    def allowed(self, state):
        hit = self._allowed.get(state)
        if hit is None:
            A = self.A
            hit = []
            for c in A.first_chars(state):
                after_first = A.deriv(state, c)
                for token_id, text in self.tokens.by_first.get(c, ()):
                    s = after_first
                    for ch in text[1:]:
                        s = A.deriv(s, ch)
                        if s == NULL:
                            break
                    else:
                        hit.append(token_id)
            if A.nullable(state):
                hit.extend(self.stop_ids)
            if not hit:  # dead end: no token spells a continuation; stop rather than loop
                hit = list(self.stop_ids)
            self._allowed[state] = hit
        return hit

    def start(self, batch_size=None):
        self._rows = {}

    def step(self, row, generated):
        """Allowed token ids for batch row `row` after the generated ids so far."""
        consumed, state, finished = self._rows.get(row, (0, self.root, False))
        if consumed > len(generated):  # a new sequence on a reused row index
            consumed, state, finished = 0, self.root, False
        for token_id in generated[consumed:]:
            if finished:
                break
            if token_id in self.stop_ids:
                finished = True
            else:
                text = self.tokens.text.get(token_id)
                state = NULL if text is None else self.A.walk(state, text)
                if state == NULL:
                    finished = True  # left the grammar (cannot happen under the mask); stop
        self._rows[row] = (len(generated), state, finished)
        if finished:
            return [self.pad_id]
        return self.allowed(state)

    def prefix_fn(self, prompt_len):
        """Function for transformers' PrefixConstrainedLogitsProcessor: (batch_id, input_ids) -> ids."""

        def fn(batch_id, input_ids):
            return self.step(int(batch_id), [int(t) for t in input_ids[prompt_len:]])

        return fn


class LMFEConstraint:
    """lm-format-enforcer behind the same hook (optional dependency; not exercised by the unit tests)."""

    backend = "lm-format-enforcer"

    def __init__(self, tokenizer, schema):
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn

        self._fn = build_transformers_prefix_allowed_tokens_fn(tokenizer, JsonSchemaParser(schema))

    def start(self, batch_size=None):
        pass

    def prefix_fn(self, prompt_len):
        return self._fn


def build_constraint(tokenizer, schema, stop_ids, pad_id, backend="auto"):
    """Return (constraint or None, info). info records what was requested and what is actually used."""
    info = {"requested": backend, "backend": "none", "detail": ""}
    if backend == "off":
        info["detail"] = "unconstrained greedy decoding with tolerant parsing"
        return None, info
    if schema is None:
        info["detail"] = "the output format provides no JSON schema; unconstrained decoding with tolerant parsing"
        return None, info
    problems = []
    if backend in ("auto", "native"):
        try:
            constraint = NativeConstraint(tokenizer, schema, stop_ids, pad_id)
            info.update(backend=constraint.backend, detail="schema compiled to a character automaton")
            return constraint, info
        except Unsupported as e:
            problems.append(f"native-dfa: {e}")
    if backend in ("auto", "lmfe"):
        try:
            constraint = LMFEConstraint(tokenizer, schema)
            info.update(backend=constraint.backend, detail="; ".join(problems))
            return constraint, info
        except ImportError:
            problems.append("lm-format-enforcer: not installed")
        except Exception as e:  # library refused the schema or the tokenizer
            problems.append(f"lm-format-enforcer: {type(e).__name__}: {e}")
    info["detail"] = "fell back to unconstrained decoding with tolerant parsing (" + "; ".join(problems) + ")"
    return None, info
