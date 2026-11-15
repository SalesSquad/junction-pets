# Two-minute live walkthrough

Use the actual native application and its current bundled evidence. Do not narrate
an unobserved outcome as a success or name a real reviewer who has not decided.

1. **The question (0:00–0:20).** Open #2283. Read the requirement: a generic value
   type comes from an external assembly; the consumer must receive a generated
   resolver without analyzer/generator failure.
2. **The evidence (0:20–0:55).** Show the recorded #2283 comparison: base FAIL
   with AD0001/CS8785 and an absent resolver; changed version PASS with no
   diagnostics and a generated resolver. Both used the same frozen probe under
   SDK 9.0.100/net8.0 on Linux. Open provenance and explain local integrity versus
   runner trust; this result is scoped to that compiler compatibility experiment.
3. **The refusal (0:55–1:15).** Select “Counterexample: a green build.” Both
   generated-code compilations succeeded, but the base still produced
   AD0001/CS8785 and no resolver. Show why the claim “Both compilations pass,
   therefore the fix is proven” remains NEEDS EVIDENCE. These are real
   observations with a deliberately unsupported inference.
4. **The scale problem (1:15–1:40).** Select #2297. Show 237 changes grouped into
   222 generated snapshots and 15 other files. Expand the generated group to show
   that files are retained, not hidden. State that actual coverage-tool behavior
   is not proven by this grouping.
5. **The accountable decision (1:40–2:00).** Open the local decision sheet. Use
   a clearly declared demonstration reviewer and rationale. Export a local
   declaration if desired; show its packet digest and unauthenticated status.
   The application does not perform a merge.

## Lessons to retain

- All-green revision-specific suites do not establish same-test differential proof.
- A larger diff can contain less semantic change when most files are generated.
- Compile/setup failures must not be confused with reproducing the target bug.
- A checksum is an integrity mechanism, not authentication of a factual claim.
- The concept becomes assessable when uncertainty is visible in the actual UI.
