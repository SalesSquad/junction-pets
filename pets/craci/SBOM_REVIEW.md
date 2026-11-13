# Synthetic SBOM consistency review

`reviewSyntheticSbom(jsonText)` in `sbom-review.mjs` is a deterministic,
repository-only exercise. It compares **supplied synthetic claims**, not real
artifacts. It performs no network calls, package installation, registry lookup,
signature verification, vulnerability scan or code execution. It is neither a
standard-format SBOM parser nor CRACI product integration. The generated
skills-only companion package does not ship or execute this module.

## Run the invented example

From the repository root, with Node 22+:

```sh
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {reviewSyntheticSbom} from "./pets/craci/sbom-review.mjs"; console.log(JSON.stringify(reviewSyntheticSbom(readFileSync("pets/craci/example-sbom.json","utf8")),null,2));'
node --test tests/pet-craci.test.mjs
```

All names, commits, digests, build IDs and the advisory are invented. `palette`
has matching declared evidence and an exact advisory match; that is **not a
confirmed exploit**. `unversioned` has null version and missing evidence, so its
consistency is `incomplete`. Neither component is verified. Before any real
triage, a separately authorized trusted verifier would need actual artifact
bytes, authenticated provenance, current advisory evidence and exposure/context.

## Exact input contract

The single argument must be JSON **text**, at most 65,536 UTF-8 bytes. Objects,
buffers and callbacks are not accepted. Ordinary `JSON.parse` semantics apply:
duplicate object members use the last value; escapes are decoded; invalid JSON
throws. This checker does not detect duplicate source members, canonicalize or
sign JSON. It rejects unknown fields after parsing, including fields asserting
`verified` or `confirmedExploit`. Every error is a `TypeError` prefixed
`Invalid synthetic SBOM:` and includes a location, not the supplied contents.

The top-level object requires exactly `schemaVersion: 1`, `synthetic: true`,
`components`, `dependencies` and `advisories`.

| Record | Required fields | Optional evidence fields |
| --- | --- | --- |
| Component (1–64) | Unique `ref`, `ecosystem`, `name` | `version`, `sha256`, `artifact`, `provenance` |
| Artifact claim | `ecosystem`, `name` | `version`, `sha256` |
| Provenance claim | `subject` with artifact-claim shape | `sourceCommit`, `builder`, `buildId` |
| Dependency (0–256) | `from`, `to`, both existing refs | None |
| Advisory (0–64) | Unique `id`, `ecosystem`, `name`, `versions` (1–32 distinct strings) | None |

Optional fields may be absent or `null`; both mean missing evidence, but receive
distinct `-missing` / `-null` issue codes. Empty strings, numeric zero and wrong
types are rejected. Version string `"0"` is a known version. Every component needs
all optional evidence fields populated before it can be internally `consistent`.

- `ref`: 1–64 lowercase ASCII letters/digits/hyphens, starting with a letter.
- `ecosystem`: 1–32 lowercase ASCII letters/digits/hyphens, starting with a letter.
- `name`, `builder`, `buildId`: 1–128 ASCII token characters, starting with a
  letter, digit or `@`; remaining characters may also be `.`, `_`, `/`, `+`, `-`.
- Advisory `id`: the same token grammar, limited to 64 characters.
- `version`: at most 64 characters; one to three numeric dot-separated parts,
  without leading zeroes except `0`, optionally followed by `-prerelease` and/or
  `+build` tokens made of ASCII letters/digits separated by dots/hyphens. No
  ranges, wildcards, `unknown` or `latest`. Matching is literal; no version
  normalization or version-range comparison is performed.
- `sha256`: exactly 64 lowercase hexadecimal characters, with no prefix.
- `sourceCommit`: exactly 40 lowercase hexadecimal characters. This syntax
  alone does not establish that a commit or build exists.

## Results and limits

`componentChecks` are sorted by ref. Each includes the declared identity,
`consistency`, issue codes and `verified: false`. Missing version/digest is
represented as `null` in output identity; the issue code preserves whether the
input was absent or null. Artifact and provenance subject comparison uses the
exact **ecosystem + name + version + SHA-256**. Case differences are mismatches.
Two components declaring the same ecosystem/name/version but different known
digests get `identity-digest-conflict`. A mismatch takes precedence over
incompleteness; all detected issues remain in the result.

`declaredDependencies` preserves only the supplied directed edges, sorted by
`from` then `to`. Dangling, self or duplicate edges are rejected. Cycles are
allowed. No transitive dependency, runtime use, reachability or exploit path is
inferred from these declarations.

`advisoryChecks` are sorted by advisory ID. An exact declared ecosystem/name and
one listed version yields `matchedRefs`, even if that component's artifact
evidence is incomplete or mismatched: the match is a **triage lead**, not trusted
inventory proof. Missing/null component versions are instead listed in
`unknownVersionRefs`. Advisories have no digest selector; they never authenticate
the component digest. Every advisory result has `confirmedExploit: false` and
`exploitability: "not-assessed"`. An empty match list does not establish safety,
patch status, complete inventory or advisory coverage.

Top-level `verified` and `provenanceAuthenticated` are always `false`.
`consistent` means only that the bounded supplied claims agree. No signature,
builder identity, provenance authenticity, artifact bytes or authorization is
verified, even when every field is present. The six existing authored companion
evaluation cases remain unchanged and are not executed model evaluations.
