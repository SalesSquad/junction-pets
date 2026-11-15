# Ingestion clarification before any successful extraction

The first attempt at the frozen protocol failed before extracting a graph: the released unused embedding arrays contain non-standard NaN, rejected by ijson. The extractor now uses Python standard-library JSON parsing, which accepts those values in ignored attributes. At most one bounded (512 MiB) raw JSON member exists transiently in RAM; no raw file is stored. Directed/simple graph schema and exact released 51/49 class counts are required.

Topology uses active endpoints only, permits source self-loops, normalizes density by n squared, and counts only distinct-node reverse pairs as reciprocal. This explicit definition was frozen before reading any extracted feature or test result. No source label, endpoint name, tweet text, bio, subtype or timestamp is a predictive input.
