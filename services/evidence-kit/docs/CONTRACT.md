# Portable contract

Persisted state is bounded ordinary JSON. Undefined, sparse/extended arrays, accessors, symbols,
cycles, non-finite numbers, custom prototypes and lone UTF-16 surrogates reject. Canonical form
sorts object keys, retains array order and uses JSON encoding. SHA-256 uses UTF-8 Web Crypto in
Node and browser. Inputs are defensively copied; exposed records/manifests are deep-frozen.

- `evidence-kit.source/v1`: raw sha256/sizeBytes, filename/media type, adapter ID/version,
  units (`label`, optional `toMetres`), declared frame and declared rights/attribution.
- `evidence-kit.dataset/v1`: source, entity count and generation over normalized entities.
  An entity is `{id,kind,locator,data}`. DXF locators retain source ordinal/group-5 handle;
  CSV locators name 1-based logical record/column and header, independent of quoted newlines.
- Reference: `{sourceSha256,generation,id,recordSha256}`. Resolve every field against the active
  dataset. Missing IDs reject the whole request. Model-provided citation text is not admitted.
- `evidence-kit.claim/v1`: method `{id,version,parameters}`, question, supported/abstained status,
  level, value/null, refs, checks/reason, generation and claim hash. Supported claims require refs;
  abstentions require null value and no citations. Levels: source_observed, derived,
  geometry_measured, cross_checked, unavailable.
- `evidence-kit.review/v1`: bound claim/generation, root/head, events/current and Undo/Redo flags.
  Identity is locally declared and independentVerification remains false. Command shape:
  `{id,expectedHead,kind,reviewer,note,value,refs}`. Events hash sequence/previous/command/after.
  Async commands serialize; stale heads reject, identical retries are idempotent, conflicting IDs reject.
- `evidence-kit.packet/v2`: dataset, claim, review, separate historical records and authenticity
  `not-authenticated`. Envelope integrity is `{algorithm:'sha256',sha256,signed:false}`.
- `evidence-kit.historical/v1`: original schema/digest/content, status
  historical_requires_revalidation and independentVerification false.
- `evidence-kit.comparison/v1`: two manifests, stable-key differences and original refs.
  Alignment declaration and physical-change verification are separate fields.

Runtime validators are authoritative, including async hashes and actual replay. Method semantic
versions must change when behavior becomes incompatible. A changed claim cannot inherit review.
New adapters preserve native locators, units and frames and expose incomplete extraction. New
methods return explicit abstention and source references. Supply frozen positives and negatives
before claiming format qualification. I/O and authorization belong to the host, not the core.
