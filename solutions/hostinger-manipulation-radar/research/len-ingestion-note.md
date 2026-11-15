# Ingestion clarification before any successful extraction

The first attempt at the frozen protocol failed before extracting a graph: the released unused embedding arrays contain non-standard NaN, rejected by ijson. The extractor now uses Python standard-library JSON parsing, which accepts those values in ignored attributes. At most one bounded (512 MiB) raw JSON member exists transiently in RAM; no raw file is stored. Directed/simple graph schema and exact released 51/49 class counts are required.

Topology uses active endpoints only, permits source self-loops, normalizes density by n squared, and counts only distinct-node reverse pairs as reciprocal. This explicit definition was frozen before reading any extracted feature or test result. No source label, endpoint name, tweet text, bio, subtype or timestamp is a predictive input.

The sequential full-source connection delivered about 0.5 MB/s. The bounded reader now fetches eight ordinary public byte ranges concurrently (32 MiB prefetch) and reassembles the complete archive in original order in RAM. Every byte contributes to the original archive SHA-256; no raw data is persisted. This changes transport only, before any successful full ingestion or evaluation.

Header-only release audit found 104 unique member names (53 campaign and 51 noncampaign), not the documented 100 (51/49). No graph_labels.json was supplied in the archive or linked public dataset metadata. Protocol v1 is retained; v2 is frozen before fitting or looking at numeric features. V2 includes all released graphs, removes only byte-identical JSON duplicates, and states that filename labels are provisional. No cherry-picking four records to match the paper.

The completed source audit found 103 byte-distinct files after removing one exact duplicate; active-node range 100–8352 and unique-edge range 206–10682. Browser engineering size guards now match those released ranges. This does not change features, learned coefficients, threshold or the fixed held-out predictions. The published paper ranges did not cover the extra released graphs.
