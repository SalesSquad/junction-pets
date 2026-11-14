#!/usr/bin/env bash
# SAMA pathway scribe: start vLLM's OpenAI-compatible server with the Gemma base
# model and the LoRA adapter as the named model "pathway-scribe".
#
# Research artefact trained on synthetic text. Not a medical device.
#
# Every flag below was checked against the vLLM v0.29.0 documentation
# (docs.vllm.ai/en/v0.29.0/cli/serve). This script started vLLM 0.29.0 on the
# project's A100 once, outside any container, through serve/smoke/tools/start_server.sh
# (version-2 270M adapter, bound to 127.0.0.1; serve/smoke/vllm.log). That was before
# guard.py and --middleware were added; the container image has never been built.
#
# Environment (all optional unless stated):
#   SCRIBE_API_KEY              bearer key clients must send. REQUIRED unless SCRIBE_ALLOW_NO_KEY=1.
#                               Passed to vLLM through VLLM_API_KEY, never on the command line.
#   SCRIBE_ALLOW_NO_KEY=1       start without a key (only behind a gateway that authenticates)
#   SCRIBE_BASE_MODEL           Hugging Face id of the base model        [unsloth/gemma-3-4b-it]
#   SCRIBE_BASE_REVISION        commit of that repository to pin         [none]
#   SCRIBE_BASE_LOCAL_DIR       base model baked into the image, if any  [/opt/scribe/base]
#   SCRIBE_ADAPTER_DIR          LoRA adapter directory                   [/opt/scribe/adapter]
#   SCRIBE_LORA_NAME            model name of the adapter                [pathway-scribe]
#   SCRIBE_BASE_NAME            model name of the plain base model       [gemma-base]
#   SCRIBE_HOST                 address to bind                          [0.0.0.0]
#   SCRIBE_PORT                 HTTP port                                [8000]
#   SCRIBE_GUARD_DIR            directory holding guard.py               [/opt/scribe]
#   SCRIBE_MAX_MODEL_LEN        prompt plus answer, in tokens            [2048]
#   SCRIBE_MAX_NUM_SEQS         sequences decoded together               [8]
#   SCRIBE_GPU_MEMORY_UTILIZATION  share of GPU memory vLLM may take     [0.90]
#   SCRIBE_MAX_LORA_RANK        must be >= the adapter's rank            [16]
#   SCRIBE_DTYPE                weights precision                        [bfloat16]
#   SCRIBE_TEXT_ONLY=0          keep image input enabled                 [1 = text only]
#   SCRIBE_STRUCTURED_OUTPUTS_CONFIG  JSON for --structured-outputs-config
#   SCRIBE_SKIP_BASE_CHECK=1    do not compare the adapter's base model with SCRIBE_BASE_MODEL
#   SCRIBE_EXTRA_ARGS           extra vLLM flags, split on spaces
#   SCRIBE_CHECK_ONLY=1         validate the adapter and exit (used at image build)
#   SCRIBE_DRY_RUN=1            print the command and exit
set -euo pipefail

BASE_MODEL="${SCRIBE_BASE_MODEL:-unsloth/gemma-3-4b-it}"
BASE_REVISION="${SCRIBE_BASE_REVISION:-}"
BASE_LOCAL_DIR="${SCRIBE_BASE_LOCAL_DIR:-/opt/scribe/base}"
ADAPTER_DIR="${SCRIBE_ADAPTER_DIR:-/opt/scribe/adapter}"
LORA_NAME="${SCRIBE_LORA_NAME:-pathway-scribe}"
BASE_NAME="${SCRIBE_BASE_NAME:-gemma-base}"
HOST="${SCRIBE_HOST:-0.0.0.0}"
PORT="${SCRIBE_PORT:-8000}"
MAX_MODEL_LEN="${SCRIBE_MAX_MODEL_LEN:-2048}"
MAX_NUM_SEQS="${SCRIBE_MAX_NUM_SEQS:-8}"
GPU_MEMORY_UTILIZATION="${SCRIBE_GPU_MEMORY_UTILIZATION:-0.90}"
MAX_LORA_RANK="${SCRIBE_MAX_LORA_RANK:-16}"
DTYPE="${SCRIBE_DTYPE:-bfloat16}"
TEXT_ONLY="${SCRIBE_TEXT_ONLY:-1}"
# Fixed backend: 'auto' may pick a different engine per request and per release.
# disable_any_whitespace is deliberately NOT set. With xgrammar 0.2.9 that option
# compiles the schema with separators ", " and ": " and the grammar then rejects
# the compact JSON the adapter was trained to write (serve/tests/test_xgrammar.py).
# The default grammar allows optional whitespace, so compact JSON stays legal.
DEFAULT_STRUCTURED_OUTPUTS_CONFIG='{"backend": "xgrammar"}'
STRUCTURED_OUTPUTS_CONFIG="${SCRIBE_STRUCTURED_OUTPUTS_CONFIG:-$DEFAULT_STRUCTURED_OUTPUTS_CONFIG}"
VLLM_BIN="${SCRIBE_VLLM_BIN:-vllm}"

fail() {
    echo "scribe entrypoint: $1" >&2
    exit "${2:-64}"
}

# ---- adapter ---------------------------------------------------------------
[ -f "$ADAPTER_DIR/adapter_config.json" ] || fail "missing $ADAPTER_DIR/adapter_config.json" 66
if [ ! -f "$ADAPTER_DIR/adapter_model.safetensors" ] && [ ! -f "$ADAPTER_DIR/adapter_model.bin" ]; then
    fail "missing $ADAPTER_DIR/adapter_model.safetensors" 66
fi

# vLLM v0.29.0 (vllm/lora/peft_helper.py) refuses: rank above --max-lora-rank,
# modules_to_save, DoRA, and adapter bias; it has no notion of per-module ranks.
# Say so here, in plain words, before the model download starts. The base-model comparison uses the last path part,
# so google/gemma-3-4b-it, unsloth/gemma-3-4b-it and a local copy all match.
if command -v python3 >/dev/null 2>&1; then
    SCRIBE_CHECK_ADAPTER_DIR="$ADAPTER_DIR" SCRIBE_CHECK_BASE="$BASE_MODEL" \
    SCRIBE_CHECK_RANK="$MAX_LORA_RANK" SCRIBE_CHECK_SKIP_BASE="${SCRIBE_SKIP_BASE_CHECK:-0}" \
    python3 - <<'PY' || fail "adapter check failed" 65
import json, os, sys

adapter = os.environ["SCRIBE_CHECK_ADAPTER_DIR"]
base = os.environ["SCRIBE_CHECK_BASE"]
max_rank = int(os.environ["SCRIBE_CHECK_RANK"])
problems = []
try:
    with open(os.path.join(adapter, "adapter_config.json"), encoding="utf-8") as handle:
        config = json.load(handle)
except (OSError, ValueError) as exc:
    sys.exit(f"scribe entrypoint: cannot read adapter_config.json: {exc}")
for key in ("r", "lora_alpha", "target_modules"):
    if key not in config:
        problems.append(f"adapter_config.json has no {key!r}")
rank = config.get("r")
if isinstance(rank, int) and rank > max_rank:
    problems.append(f"adapter rank {rank} is above SCRIBE_MAX_LORA_RANK {max_rank}")
if config.get("modules_to_save"):
    problems.append("modules_to_save is set; vLLM serves LoRA weights only")
if config.get("use_dora"):
    problems.append("DoRA adapters are not supported by vLLM")
if config.get("bias", "none") != "none":
    problems.append("adapter bias is not supported by vLLM")
# vLLM reads one rank and one alpha for the whole adapter. Per-module ranks (EVA
# initialisation, rank_pattern) or per-module alphas would be scaled wrongly.
for key in ("rank_pattern", "alpha_pattern"):
    if config.get(key):
        problems.append(
            f"{key} is set ({len(config[key])} entries): vLLM applies a single rank and alpha. "
            "Merge the adapter into the base weights and serve the merged model instead"
        )


def last(name):
    return str(name).rstrip("/").split("/")[-1].lower()


if os.environ["SCRIBE_CHECK_SKIP_BASE"] != "1":
    trained = [("adapter_config.json", config.get("base_model_name_or_path"))]
    try:
        with open(os.path.join(adapter, "training-config.json"), encoding="utf-8") as handle:
            trained.append(("training-config.json", json.load(handle).get("base_model")))
    except (OSError, ValueError):
        pass
    for source, name in trained:
        if name and last(name) != last(base):
            problems.append(
                f"{source} says the adapter was trained on {name!r} but the server would load {base!r} "
                "(set SCRIBE_BASE_MODEL to the training base, or SCRIBE_SKIP_BASE_CHECK=1)"
            )
for problem in problems:
    print("scribe entrypoint: " + problem, file=sys.stderr)
sys.exit(1 if problems else 0)
PY
else
    echo "scribe entrypoint: python3 not found, adapter_config.json not checked" >&2
fi

if [ "${SCRIBE_CHECK_ONLY:-0}" = "1" ]; then
    echo "scribe entrypoint: adapter files and adapter_config.json at $ADAPTER_DIR passed the static checks"
    exit 0
fi

# ---- bearer key ------------------------------------------------------------
# vLLM reads VLLM_API_KEY when --api-key is not given, but v0.29.0 checks it only on
# paths starting with /v1, /v2, /inference and /cohere. POST /invocations (which runs
# generation), /tokenize, /detokenize, /metrics, /load, /version, /docs and others
# would answer without a key. So whenever a key is required, guard.py is loaded with
# --middleware and demands the key on every path except /health and /ping.
if [ -n "${SCRIBE_API_KEY:-}" ]; then
    export VLLM_API_KEY="$SCRIBE_API_KEY"
    KEY_STATE="required"
elif [ -n "${VLLM_API_KEY:-}" ]; then
    KEY_STATE="required"
elif [ "${SCRIBE_ALLOW_NO_KEY:-0}" = "1" ]; then
    KEY_STATE="NOT required (SCRIBE_ALLOW_NO_KEY=1)"
else
    fail "SCRIBE_API_KEY is not set. Set it, or set SCRIBE_ALLOW_NO_KEY=1 if a gateway in front authenticates every request." 64
fi
unset SCRIBE_API_KEY
GUARD_DIR="${SCRIBE_GUARD_DIR:-/opt/scribe}"
GUARD_ARGS=()
if [ "$KEY_STATE" = "required" ]; then
    [ -f "$GUARD_DIR/guard.py" ] || fail "missing $GUARD_DIR/guard.py: without it vLLM would leave paths outside /v1 open" 66
    export PYTHONPATH="$GUARD_DIR${PYTHONPATH:+:$PYTHONPATH}"
    GUARD_ARGS=(--middleware guard.BearerGuard)
    KEY_STATE="required on every path except /health and /ping"
fi

# ---- base model ------------------------------------------------------------
if [ -f "$BASE_LOCAL_DIR/config.json" ]; then
    MODEL="$BASE_LOCAL_DIR"            # baked into the image: no download at start
    export HF_HUB_OFFLINE=1
    REVISION_ARGS=()
else
    MODEL="$BASE_MODEL"                # fetched from Hugging Face into HF_HOME on first start
    export HF_HOME="${HF_HOME:-/data/hf}"
    REVISION_ARGS=()
    if [ -n "$BASE_REVISION" ]; then
        REVISION_ARGS=(--revision "$BASE_REVISION")
    fi
fi

# No anonymous usage report leaves the container.
export VLLM_NO_USAGE_STATS="${VLLM_NO_USAGE_STATS:-1}"
export DO_NOT_TRACK="${DO_NOT_TRACK:-1}"

CMD=("$VLLM_BIN" serve "$MODEL"
    --host "$HOST" --port "$PORT"
    --served-model-name "$BASE_NAME"
    --dtype "$DTYPE"
    --max-model-len "$MAX_MODEL_LEN"
    --max-num-seqs "$MAX_NUM_SEQS"
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
    --enable-lora --max-loras 1 --max-lora-rank "$MAX_LORA_RANK"
    --lora-modules "$LORA_NAME=$ADAPTER_DIR"
    --structured-outputs-config "$STRUCTURED_OUTPUTS_CONFIG"
    --disable-access-log-for-endpoints /health)
if [ "${#GUARD_ARGS[@]}" -gt 0 ]; then
    CMD+=("${GUARD_ARGS[@]}")
fi
if [ "${#REVISION_ARGS[@]}" -gt 0 ]; then
    CMD+=("${REVISION_ARGS[@]}")
fi
if [ "$TEXT_ONLY" = "1" ]; then
    CMD+=(--language-model-only)
fi
if [ -n "${SCRIBE_EXTRA_ARGS:-}" ]; then
    # shellcheck disable=SC2206  # word splitting is the documented behaviour
    EXTRA=($SCRIBE_EXTRA_ARGS)
    CMD+=("${EXTRA[@]}")
fi

echo "scribe entrypoint: bearer key $KEY_STATE; health check GET /health on port $PORT"
printf 'scribe entrypoint: command:'
printf ' %q' "${CMD[@]}"
printf '\n'

if [ "${SCRIBE_DRY_RUN:-0}" = "1" ]; then
    exit 0
fi
# exec: vLLM becomes PID 1 and receives the platform's SIGTERM directly.
exec "${CMD[@]}"
