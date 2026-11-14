# syntax=docker/dockerfile:1.7
#
# SAMA pathway scribe: a thin layer on the official vLLM OpenAI-server image that
# adds one LoRA adapter and a start script. Research artefact trained on
# synthetic text; not a medical device.
#
# Build from the project root. The adapter comes in as a named build context, so
# it can live anywhere and nothing else from the repository enters the image:
#
#   docker buildx build --platform linux/amd64 \
#     -f serve/Dockerfile \
#     --build-context adapter=data/scribe/adapter-v1 \
#     -t sama-scribe-gemma:v1 serve/
#
# The adapter directory must hold adapter_config.json and adapter_model.safetensors
# (what scribe/train_lora.py writes). training-config.json is copied too when present.
#
# Base model: by default it is NOT in the image. vLLM downloads the ungated mirror
# unsloth/gemma-3-4b-it (8.64 GB) into HF_HOME on first start; on
# Verda HF_HOME=/data/hf is the deployment's scratch disk, so later cold starts
# read it from disk. To bake the base model into the image instead, add
#   --build-arg BAKE_BASE_MODEL=1
# (bigger image, no Hugging Face call at start). For the version-2 270M adapter pass
#   --build-arg BASE_MODEL=unsloth/gemma-3-270m-it
#   --build-arg BASE_REVISION=23cf460f6bb16954176b3ddcc8d4f250501458a9
#
# Licence: Gemma 3 and every adapter or merged model derived from it are used under the
# Gemma Terms of Use (https://ai.google.dev/gemma/terms) and the Gemma Prohibited Use
# Policy (https://ai.google.dev/gemma/prohibited_use_policy). Not for automated decisions
# about real patients.

# Pinned by tag. v0.29.0 is the tag Verda's own vLLM tutorial was tested with;
# its Dockerfile builds against CUDA 13.0.3 and its entrypoint is `vllm serve`.
# For a byte-exact pin use the digest that Docker Hub listed on 2026-11-14:
#   docker.io/vllm/vllm-openai@sha256:c2914767605584b6d8f45686b82de173ecc99e781897aa3d0a66dacd72c51ae1
ARG VLLM_IMAGE=docker.io/vllm/vllm-openai:v0.29.0
FROM ${VLLM_IMAGE}

# Snapshot of unsloth/gemma-3-4b-it that the training box downloaded (runs/train.jsonl).
ARG BASE_MODEL=unsloth/gemma-3-4b-it
ARG BASE_REVISION=bf46152c47f5dd20b896357cb51abc4c03b8ee8c
ARG BAKE_BASE_MODEL=0

LABEL org.opencontainers.image.title="sama-scribe-gemma" \
      org.opencontainers.image.description="Gemma + LoRA 'pathway-scribe' behind vLLM. Synthetic training data. Research artefact, not a medical device." \
      sama.base-model="${BASE_MODEL}" \
      sama.base-revision="${BASE_REVISION}" \
      sama.synthetic-training-data="true"

ENV SCRIBE_BASE_MODEL=${BASE_MODEL} \
    SCRIBE_BASE_REVISION=${BASE_REVISION} \
    SCRIBE_BASE_LOCAL_DIR=/opt/scribe/base \
    SCRIBE_ADAPTER_DIR=/opt/scribe/adapter \
    SCRIBE_LORA_NAME=pathway-scribe \
    SCRIBE_PORT=8000 \
    HF_HOME=/data/hf \
    HF_HUB_DISABLE_TELEMETRY=1 \
    VLLM_NO_USAGE_STATS=1 \
    DO_NOT_TRACK=1

# The adapter: two required files, one optional (the [n] glob may match nothing).
COPY --from=adapter adapter_config.json adapter_model.safetensors training-config.jso[n] /opt/scribe/adapter/
COPY entrypoint.sh /opt/scribe/entrypoint.sh
COPY guard.py /opt/scribe/guard.py
COPY schema.json /opt/scribe/schema.json

# Fail the build, not the first cold start, if the adapter cannot be served.
RUN chmod 0755 /opt/scribe/entrypoint.sh \
    && SCRIBE_CHECK_ONLY=1 /opt/scribe/entrypoint.sh

# Optional: put the base model in the image.
RUN if [ "${BAKE_BASE_MODEL}" = "1" ]; then \
      HF_HOME=/tmp/hf-build python3 -c "import sys; from huggingface_hub import snapshot_download; snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2], local_dir='/opt/scribe/base')" "${BASE_MODEL}" "${BASE_REVISION}" \
      && rm -rf /tmp/hf-build /opt/scribe/base/.cache; \
    fi

EXPOSE 8000

# Replaces the base image's ENTRYPOINT ["vllm", "serve"]. Health: GET /health on 8000.
ENTRYPOINT ["/opt/scribe/entrypoint.sh"]
