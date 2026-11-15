#!/usr/bin/env bash
# Installs Evo 2 (open weights, Apache-2.0) on the GPU box under /root/genomics.
# No NVIDIA/NGC key and no Hugging Face token is used. Research use only; not for clinical decisions.
set -euo pipefail
ROOT=/root/genomics
MODEL_REPO=${MODEL_REPO:-arcinstitute/evo2_7b_base}
mkdir -p "$ROOT"/{data,out,logs,hf}
cd "$ROOT"
step() { echo "=== $(date -u +%FT%TZ) $*"; }

step "python venv"
if ! python3 -c "import ensurepip" 2>/dev/null; then
  DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=180 update -q
  DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=180 install -y -q python3.12-venv
fi
# Triton (imported by the Evo 2 model code) compiles a small C extension at import time and needs Python.h
if [ ! -f /usr/include/python3.12/Python.h ]; then
  DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=180 install -y -q python3.12-dev
fi
[ -x venv/bin/python ] || python3 -m venv venv
. venv/bin/activate
python -m pip install -q -U pip setuptools wheel

step "torch 2.7.1 cu128"
pip install -q torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128
python -c "import torch; print('torch', torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0), 'cxx11abi', torch._C._GLIBCXX_USE_CXX11_ABI)"

step "flash-attn 2.8.0.post2 prebuilt wheel"
ABI=$(python -c "import torch; print(str(torch._C._GLIBCXX_USE_CXX11_ABI).upper())")
pip install -q "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.0.post2/flash_attn-2.8.0.post2+cu12torch2.7cxx11abi${ABI}-cp312-cp312-linux_x86_64.whl"
# torch must be imported first: flash_attn_2_cuda links against libc10.so from the torch wheel
python -c "import torch, flash_attn_2_cuda, flash_attn; print('flash_attn', flash_attn.__version__)"

step "evo2 0.6.0 (light install, no transformer-engine)"
pip install -q evo2==0.6.0
pip list 2>/dev/null | grep -i -E "^(torch|evo2|vtx|flash|transformer|triton|numpy|biopython|huggingface)" || true
python -c "import importlib.util as u; print('transformer_engine installed:', u.find_spec('transformer_engine') is not None)"

step "weights ${MODEL_REPO} (anonymous download)"
# Revision of arcinstitute/evo2_7b_base used on 2026-11-14 (data/genomics/evo2-run.json). Pinned so a rerun scores with the same weights.
MODEL_REVISION="${MODEL_REVISION:-074097e9dc788e8bfe045d6495b9f6153a7c6bfc}"
HF_HOME="$ROOT/hf" MODEL_REVISION="$MODEL_REVISION" python - <<PY
from huggingface_hub import snapshot_download
import os
p = snapshot_download("${MODEL_REPO}", revision=os.environ.get("MODEL_REVISION") or None)   # pinned below; unset = latest
print("snapshot_path", p)
print("revision", os.path.basename(p))
for f in sorted(os.listdir(p)):
    fp = os.path.join(p, f)
    print("file", f, os.path.getsize(fp))
PY
step "setup done"
