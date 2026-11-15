# LEN graph research

This is a separate experimental whole-trend graph screen. It does not validate
the post-coaction v2 detector, infer bot identity, determine truth or intent, or
authorize enforcement.

## Source and annotation caveat

Atul Anand Gopalakrishnan, Jakir Hossain, Tuğrulcan Elmas and Ahmet Erdem Sarıyüce,
*Large Engagement Networks for Classifying Coordinated Campaigns and Organic
Twitter Trends*, ICWSM 2025:
https://sariyuce.com/papers/icwsm25.pdf
Dataset: https://erdemub.github.io/large-engagement-network/
Code/description: https://github.com/erdemUB/LEN

The paper explicitly releases the dataset under CC-BY for sharing/adaptation
(page 2). We add topology extraction, a deterministic split, standardization,
class-weighted regularized logistic fitting, threshold selection and reporting.
We redistribute no original tweets, biographies or graph records.

**The actual public small archive has 104 JSON graphs: 53 campaign and 51
noncampaign filename markers. The paper/README describe 100, with 51/49.
The original separate graph_labels.json index is absent from the archive and
linked metadata.** Thus results are agreement with provisional released
filename annotations, not independently confirmed gold labels. The initial
100-graph preregistration is retained in len-protocol.json; the header-only
release audit forced len-protocol-v2.json before any complete extraction, fit,
calibration metric or test result. No four graphs were selected away to match
the paper. Only byte-identical source JSON duplicates are removed, with
conflicting labels rejected.

## Frozen evaluation

Each complete graph is one unit. Stratify by annotation, sort the stable case
hash, allocate floor(60%) train, floor(20%) calibration, remainder test.
Compute feature means/scales only on train. Fit the frozen 12-feature model
and a size-only baseline (two features). Both use the same fixed learning rate,
iteration count and L2 penalty. Select thresholds only on calibration,
maximizing recall with empirical FPR <=10%; abstain if necessary.
Evaluate held-out labels only after model and thresholds are fixed.

Report TP/FP/TN/FN, accuracy, precision, recall, FPR and descriptive Wilson
intervals. A small calibration set does not establish a population false-alarm
bound. Collection bias, graph-size shortcuts, recurring actors across trends
and uncertain labels limit generalization. Scores are not calibrated
probabilities. Size guards in the browser are necessary but do not establish
that an uploaded graph follows the source collection process.

## Reproduce

Run from solutions/hostinger-manipulation-radar, with Python >=3.11 standard
library and Node >=22. No pip packages or model provider are needed.

1. python3 research/extract_len.py --output work/real-data/len-features.json
2. (cd research && python3 -m unittest test_len_research.py)
3. python3 research/evaluate_len.py --source work/real-data/len-features.json --output work/real-data/results
4. Copy only results/len-evaluation.json to public/graph/evaluation.json and
   results/len-model.json to public/graph/model.json.

Extraction reads the ~5.8 GB public tar through eight bounded ordinary HTTP
range requests at a time, preserves byte order and hashes the complete source.
At most one JSON graph (source guard 512 MiB) and bounded range buffers exist
in RAM. The standard JSON parser accepts source NaN values in ignored
embeddings; none enter features. Raw text and account fields are never written
or sent to a model. Ignored work/ contains only numeric topology, graph-level
source hashes/annotation markers and recoverable checkpoints. Hashes identify
whole public source files, not individual accounts.

Nodes are active edge endpoints; isolates are excluded. Density is m/n²,
including source self-loops. Reciprocity counts reverse edges between distinct
nodes only. Incoming/outgoing degree inequality, concentration and log sizes
complete the feature vector. Original IDs and all content/attributes are
discarded. The browser accepts only a bounded directed edge list, runs locally
and stores or uploads nothing.

The aggregate evaluation binds the original archive SHA-256, extracted numeric
artifact, frozen protocol, split and exact evaluator/extractor file hashes.
The private numeric cache is unnecessary to run the demo, and is excluded from
Git and Docker. Fresh inference on live feeds and Hostinger deployment remain
separate qualification steps.
