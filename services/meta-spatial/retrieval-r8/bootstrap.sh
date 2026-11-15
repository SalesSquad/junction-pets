#!/usr/bin/env bash
set -euo pipefail
export META_R6_ROOT=/work/meta-r6
export META_R6_CODE="$META_R6_ROOT/source/services/meta-spatial/retrieval-r6"
export HF_HUB_DISABLE_IMPLICIT_TOKEN=1
export HF_HUB_DISABLE_TELEMETRY=1
export TOKENIZERS_PARALLELISM=false
export MAX_JOBS=8
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_PROGRESS_BAR=off
export PATH="/usr/local/cuda/bin:$PATH"
cd "$META_R6_ROOT"
python3.12 - <<'PY'
import hashlib,json,os
from pathlib import Path
root=Path(os.environ['META_R6_ROOT']); code=Path(os.environ['META_R6_CODE'])
for p,want in [(root/'inputs.json','47a015b6cf7f2ef10ff246fbf325e3f63459aa277d8ab3bd4bd6f61b4e0ce25f'),(root/'source.tar','5d68feb39f2b3b718af2c18dfaa9bd7947b44b7d7c6af15dfc6acf4964a4bd73'),(code/'extract_nvidia.py','a31e08d925b439b5d9e01d75dc9eb8a4397696425c2908853a96f6809421da11')]:
    assert hashlib.sha256(p.read_bytes()).hexdigest()==want,str(p)
print('SOURCE_AND_INPUT_SHA_VERIFIED',flush=True)
PY
echo R8_PHASE=install_runtime
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3.12-venv python3.12-dev build-essential
test ! -e "$META_R6_ROOT/venv"
if ! python3.12 -m venv "$META_R6_ROOT/venv"; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3.12-venv
  python3.12 -m venv "$META_R6_ROOT/venv"
fi
if ! command -v g++ >/dev/null; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends build-essential
fi
export META_R6_PYTHON="$META_R6_ROOT/venv/bin/python"
"$META_R6_PYTHON" -m pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cu130
"$META_R6_PYTHON" -m pip install numpy==2.2.6 pillow==12.0.0 shapely==2.1.2 huggingface_hub==0.36.0 transformers==4.51.3 timm==1.0.22 einops==0.8.1 safetensors==0.6.2 hatchling==1.27.0 editables==0.5 setuptools==80.9.0 wheel==0.45.1 ninja==1.13.0
command -v nvcc
nvcc --version
"$META_R6_PYTHON" - <<'PY'
import torch,json
assert torch.cuda.is_available(),'CUDA_UNAVAILABLE'
print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0),'capability':torch.cuda.get_device_capability(0)}),flush=True)
PY
export TORCH_CUDA_ARCH_LIST="$("$META_R6_PYTHON" -c 'import torch; a,b=torch.cuda.get_device_capability(0); print(f"{a}.{b}")')"
"$META_R6_PYTHON" - <<'PY'
import os
from pathlib import Path
from huggingface_hub import snapshot_download
root=Path(os.environ['META_R6_ROOT'])/'models'; rev='0e83e83f17943524b90afa6c0fd82ac2bc1a40ca'
snapshot_download(repo_id='nvidia/nemotron-ocr-v2',revision=rev,local_dir=str(root/('nemotron-ocr-v2-'+rev)),allow_patterns=['nemotron-ocr/**','v2_english/*','LICENSE*','README.md','THIRD_PARTY_NOTICES.md'],token=False,max_workers=4)
PY
echo R8_PHASE=compile_pinned_ocr
"$META_R6_PYTHON" -m pip install --no-build-isolation --no-deps "$META_R6_ROOT/models/nemotron-ocr-v2-0e83e83f17943524b90afa6c0fd82ac2bc1a40ca/nemotron-ocr"
"$META_R6_PYTHON" -m pip freeze > "$META_R6_ROOT/runtime-freeze.txt"
"$META_R6_PYTHON" - <<'PY'
import concurrent.futures,os,sys
from pathlib import Path
root=Path(os.environ['META_R6_ROOT']);sys.path.insert(0,os.environ['META_R6_CODE'])
import extract_nvidia as e
m,h=e.load_manifest(root/'inputs.json','8948b44454f1a5dd174395e6d69e1ae8b533688b');image_root=e.safe_root(root/'images')
def fetch(row):
    return e.admit_image(image_root,row)[1]
with (root/'prefetch-admissions.jsonl').open('x',encoding='utf-8') as out:
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        for i,r in enumerate(pool.map(fetch,m['images']),1):
            e.append_json(out,r)
            if i%250==0 or i==len(m['images']): print(f'PREFETCH {i}/{len(m["images"])}',flush=True)
print('PREFETCH_COMPLETE',h,flush=True)
PY
echo R8_PHASE=extract_all_images
"$META_R6_PYTHON" "$META_R6_CODE/extract_nvidia.py" --manifest "$META_R6_ROOT/inputs.json" --image-root "$META_R6_ROOT/images" --model-root "$META_R6_ROOT/models" --output "$META_R6_ROOT/extraction-01" --source-commit 8948b44454f1a5dd174395e6d69e1ae8b533688b --batch-size 16
