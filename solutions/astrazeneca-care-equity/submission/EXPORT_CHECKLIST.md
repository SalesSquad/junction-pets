# Public MIT export of this folder: checklist

What a public, MIT-licensed export of `solutions/astrazeneca-care-equity/` would need. **Nothing has
been published and no repository has been created.** Publishing the source, and whether to publish
an adapter, are the team's decisions (`NVIDIA_OPTIONS.md` section 4, decisions 10 and 11). The scans
below were run read-only on 14 November 2026 at 22:04-22:05 UTC on the working folder, while other
lanes were still adding files, and not on a final export tree. Rerun them on that tree right before
anything is pushed.

## 1. Status found tonight

| Check | Result | How |
| --- | --- | --- |
| LICENSE file | **Missing** in this folder and at the repository root (`../../`) | `ls` |
| Secret scan, pattern based | gitleaks 8.30.1, default rules: **7 findings, all false positives**: indicator key names (`key="cer..."` style) in `pipeline/fetch_public_data.py`, `data/snapshot/public-v1.json` and `web/data/app.json`; three JSON source-path strings in `data/scribe/v3/summary-v1.json`; and `s.countiesWithAtLeast3Kept` in `web/planner.mjs`, which matches the shape of a Vault token. Virtualenvs, bytecode, model weights, Parquet files and files over 25 MB were skipped | `gitleaks dir . --redact` with a config extending the default rules |
| Secret scan, exact values | The values of the 2 secret-like variables in the team's Verda inference and TypeSafe env files were searched for in 17,655 files: **0 files contain either value** | `runs/laneC-step10.jsonl`; values held only in the scanning process's environment and never printed |
| E-mail addresses | **0 files** (virtualenvs and binaries skipped) | `grep -rIlE` |
| Finnish personal identity code pattern | **0 files** | `grep -rIlE` |
| Absolute home paths (`/Users/<name>/...`) | **19 files**, mostly run logs, FLARE logs and download logs | `grep -rIl` |
| The owner's first name (as part of the laptop host name in run logs) | **43 files** | `grep -rIil` |
| Patient-like content | All notes are SYNTHETIC (model-written from sampled answer keys); simulated people only in the event log | `README.md`, `TRAINING.md` |
| Private references | `PROGRESS.md` names a private pull request and branch in another repository; `NVIDIA_OPTIONS.md` and `src/planner/tools.mjs` contain `../../` paths (the planner path stays inside this folder; the `NVIDIA_OPTIONS.md` links point to monorepo documents that will not exist in the export) | `grep` |
| Size of the folder as it is | 6.4 GB, almost all of it virtualenvs, model caches and adapters | `du -sh` |

## 2. Must do before publishing

- [ ] **Owner decision 10 (a):** publish the source at all, and under which account. No agent creates
      the repository or pushes.
- [ ] **Add `LICENSE`** (MIT, template in section 5). The copyright holder line is the team's choice.
- [ ] **Add `NOTICE`** with the Gemma notice and the third-party list (template in section 5).
- [ ] **Build the export tree from an explicit exclude list** (section 4), never by copying the
      working folder as it is. `scribe/v4/artifacts/` (952 MB at 22:05 UTC and growing, including a
      Hugging Face cache of Gemma base-model weights and new adapters) and
      `data/scribe/nemotron/cache/` (10 MB of model responses) are now listed in `.gitignore`
      (lines 30 and 26, checked 00:44 UTC), but still build the export tree from the explicit
      exclude list, and rerun the 22:05 UTC scans (path and name counts) on the final export tree;
      those counts are not rerun yet.
- [ ] **Scrub or accept personal traces:** the laptop host name (contains the owner's first name) in
      run logs, and absolute home paths in 19 files. Option: replace them with `<host>` and `<home>`
      in the export copy only, and say so in the README.
- [ ] **Remove private references:** the private PR and branch names in `PROGRESS.md`; links to
      `../../docs/...` in `NVIDIA_OPTIONS.md` (keep the file, drop or rewrite the links).
- [ ] **Rerun both secret scans and the personal-data greps on the export tree**, and attach the
      gitleaks report (redacted) to the release notes.
- [ ] **Run `npm test` on the export tree** with Node 22. Python suites need their own virtualenvs
      and are documented, not required for the export to be valid.
- [ ] **Model weights (decision 10 b):** the adapters and cached weights (`*.safetensors`, 15 files,
      295 MB at 22:05 UTC) are not part
      of the source export. If one is published, do it as a separate release asset or model
      repository with its own model card and the Gemma notice, and say which notes trained it.
- [ ] **Training-data provenance (decision 11):** the best adapter (C-270m-all-v2data) was trained
      partly on 638 Claude Haiku-written notes. Whether Anthropic's Commercial Terms allow publishing
      that adapter is an open legal question. The safer published adapter is V3-270m-nemotron
      (trained on Nemotron-written notes only), which reaches 564/700 with the resolver
      (`runs/diagnose/resolve-relative-v1.json`). Disclose the training data either way.

## 3. Third-party terms to state or check

| Item in the folder | Terms | Status |
| --- | --- | --- |
| Gemma 3 base model (not redistributed) and any adapter derived from it | Gemma Terms of Use and Prohibited Use Policy; adapters are Model Derivatives; the policy names automated decisions in healthcare | Recorded in `serve/README.md`. A NOTICE is needed if an adapter or merged model is distributed |
| SYNTHETIC notes written by NVIDIA Nemotron 3.5 Super VL (`data/scribe/**`) | OpenMDW-1.1 model licence; terms for outputs from the event endpoint | **Not checked tonight** |
| SYNTHETIC notes written by Claude Haiku (`data/scribe/**`, 638 in training, 200 in test) | Anthropic Commercial Terms | **Open question** (decision 11) for training data and any adapter |
| THL Sotkanet indicators, Statistics Finland tables | CC BY 4.0, as recorded in `data/snapshot/public-v1.json` | Recorded; attribution must stay in the README |
| NORDCAN survival | "Free reuse with citation (NORDCAN terms)", as recorded in `data/snapshot/public-v1.json` | Recorded; citation must stay |
| National cancer strategy roadmap PDF and its full-text extraction (`data/roadmap/*.pdf`, `data/roadmap/roadmap.txt`) | Not recorded | **Check before publishing.** If redistribution is unclear, publish the URL and sha256 only and let the test fetch the PDF; the roadmap test needs the PDF to verify its 117 quotes |
| Literature quotes in `data/evidence/literature-v1.json` | Short quotations with citations | Keep citations |
| Findlay et al. 2018 table, GRCh37 chromosome 17 (`data/genomics/raw/`) | Reuse terms of the Springer table not confirmed (`genomics/README.md`) | Already git-ignored; keep out of the export |
| Evo 2 code and weights | Apache-2.0 (`genomics/README.md`) | Not redistributed |
| TypeSafe, NVIDIA, Verda, OpenAI, Anthropic API responses cached on disk | Provider terms | Keep caches out of the export (section 4) |

## 4. Exclude list for the export tree

Paths are relative to this folder. Sizes measured tonight.

| Exclude | Size | Why |
| --- | --- | --- |
| `**/.venv/`, `scribe/artifacts/mlx-venv/` | about 2.3 GB | virtualenvs |
| `scribe/artifacts/` | 3.0 GB | model caches, version-1 adapter, virtualenv |
| `scribe/v4/artifacts/` | 952 MB (22:05 UTC, growing) | Hugging Face cache with base-model weights, new MLX adapters; **not in `.gitignore`** |
| `scribe/v3/artifacts/`, `scribe/v2/artifacts/`, `serve/build/`, `**/*.safetensors` | 93 MB, 15 MB, 50 MB | adapters (decision 10 b) |
| `data/scribe/cache/`, `data/scribe/v3/judges/cache/`, `data/scribe/v3/teacher/cache/`, `data/scribe/v2/verify/` | 25 MB, 18 MB, 6.9 MB, 4.7 MB | per-request caches of paid calls |
| `data/scribe/nemotron/cache/` | 10 MB | per-request cache of tonight's Nemotron calls; **not in `.gitignore`** (the per-note result files next to it are enough) |
| `data/genomics/raw/`, `genomics/cache/` | 25 MB | third-party files with unconfirmed reuse terms |
| `.codex-logs/`, `.claude/`, `.ruff_cache/`, `**/__pycache__/`, `flare/workspace/`, `runs/*.tmp` | small | agent logs, local settings, caches |
| `ml/data/`, `ml/artifacts/*.pt` | 2.2 MB and part of 7.3 MB | already git-ignored |

Commands for the team, **not run**:

```bash
# from the repository root; EXPORT is a new empty directory outside the repository
rsync -a --prune-empty-dirs \
  --exclude '.venv/' --exclude '__pycache__/' --exclude '.ruff_cache/' \
  --exclude '.codex-logs/' --exclude '.claude/' --exclude 'runs/*.tmp' \
  --exclude 'scribe/artifacts/' --exclude 'scribe/v2/artifacts/' --exclude 'scribe/v3/artifacts/' \
  --exclude 'scribe/v4/artifacts/' --exclude 'serve/build/' --exclude '*.safetensors' \
  --exclude 'data/scribe/cache/' --exclude 'data/scribe/v3/judges/cache/' \
  --exclude 'data/scribe/v3/teacher/cache/' --exclude 'data/scribe/v2/verify/' \
  --exclude 'data/scribe/nemotron/cache/' --exclude 'data/genomics/raw/' --exclude 'genomics/cache/' \
  --exclude 'flare/workspace/' --exclude 'ml/data/' --exclude 'ml/artifacts/*.pt' \
  solutions/astrazeneca-care-equity/ "$EXPORT"/
gitleaks dir "$EXPORT" --redact --no-banner -f json -r "$EXPORT.gitleaks.json"
grep -rIl '/Users/' "$EXPORT" ; grep -rIil '<owner first name>' "$EXPORT"
(cd "$EXPORT" && npm test)
```

## 5. Templates

`LICENSE` (standard MIT text; fill the holder):

```
MIT License

Copyright (c) 2026 <COPYRIGHT HOLDER: the team decides>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

`NOTICE` (draft; check the Gemma wording against https://ai.google.dev/gemma/terms before
publishing, since it was written from memory and not re-read tonight):

```
This repository's own code and documents are under the MIT License (LICENSE).

Gemma: the pathway scribe is trained on Gemma 3. Gemma is provided under and subject to the
Gemma Terms of Use found at ai.google.dev/gemma/terms. Any Gemma model derivative (adapter or
merged model) is subject to those terms and to the Gemma Prohibited Use Policy
(ai.google.dev/gemma/prohibited_use_policy). Every extraction is a proposal that a person confirms;
it must not drive an automated decision about a patient.

Data: THL Sotkanet and Statistics Finland (CC BY 4.0); NORDCAN (free reuse with citation).
All patient-like data in this repository are SYNTHETIC: simulated people and notes written by
language models (NVIDIA Nemotron 3.5 Super VL, Claude Haiku). Not for clinical use.
```
