"""Step 8 wrapper around scribe/mlx2/infer.py: same greedy MLX inference, but its run-log line goes to
runs/laneA-step8.jsonl (step 3's log is not ours). SYNTHETIC notes only; every output is a proposal a person confirms.

  HF_HUB_OFFLINE=1 scribe/artifacts/mlx-venv/bin/python scribe/v4/infer8.py --base 270m --format expression \
      --adapter scribe/v4/artifacts/B-270m-expr-aug/adapter --input data/scribe/stress/stress-v1.parquet \
      --output data/scribe/v4/eval/outputs/B-270m-expr-aug/stress.jsonl
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mlx2"))

import m2common as C  # noqa: E402

C.RUNLOG = C.ROOT / "runs/laneA-step8.jsonl"

import infer  # noqa: E402

if __name__ == "__main__":
    infer.main(sys.argv[1:])
    sys.exit(0)
