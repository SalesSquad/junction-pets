# scribe/v4: preregistered evaluation and MLX adapters

v4 trained three Gemma 3 LoRA adapters on Apple silicon (`scribe/mlx2`, outputs under `data/scribe/v4/`) and scored them, the frozen Finnish date resolver and the Nemotron reader once on a preregistered stress set; all notes are SYNTHETIC.
The final numbers are in `data/scribe/v4/eval/results-v1.json`, rendered to `RESULTS.md` by `eval8.py score`, which reads only stored model outputs.
Reproduce them: `bash scribe/v4/reproduce.sh` (no keys, network, model or GPU; about 3 seconds).
It runs `eval8.py verify`, `eval8.py score` and `local_pairs.py`, compares with the committed files ignoring timestamps, restores them, and prints REPRODUCED or DIFFERS with the differing keys.
Which modules are live and which are history: `../ARCHIVE.md`.
