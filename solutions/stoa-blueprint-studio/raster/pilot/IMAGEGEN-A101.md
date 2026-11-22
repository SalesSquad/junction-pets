# Stoa raster pilot: A-101

Source: the synthetic ImageGen drawing shown in the conversation, sheet A-101.
The expectations below were checked visually against the rendered image.
This specification is for a manual pilot. Freeze the actual image bytes and their SHA-256 before making it an automated fixture.

| Query | Expected answer | Evidence to highlight |
| --- | --- | --- |
| What area is printed for room 101? | 12 m² | Paired identifier and area in upper-left room |
| What area is printed for room 102? | 16 m² | Paired identifier and area in upper-right room |
| What area is printed for room 103? | 9 m² | Paired identifier and area in lower-left room |
| What area is printed for room 104? | 12 m² | Paired identifier and area in lower-right room |
| What area is printed for room 105? | Abstain: no matching room tag | Visible room tags 101–104 |
| Can a single pixel-to-metre ratio be used to measure these rooms? | Abstain: scale cues disagree | 0–5 m bar and horizontal 7.00 m dimension. In the displayed image the bar spans about 327 px and the dimension spans about 680 px, or about 65 and 97 px/m respectively. |

Report the literal-reading score, citation-localization score and correct-abstention score separately. In particular, a correct room number paired with another room's identical area is a citation failure.

## Implementation order

1. Use Stoa's existing raster OCR and region scorer to qualify literal readings on PNG/PDF pages. Bind OCR regions to page number, pixel dimensions and source hash. Keep OCR candidates available for inspection.
2. Require corroborating scale cues and consistent coordinate transforms before enabling raster measurements. Keep literal annotations available when scale validation fails.
3. Render a reference drawing from a deterministic SVG or DXF model with known geometry. Use the same model for clean, rotated, noisy and cropped renders. Keep exact polygon areas and reference boxes in a separate manifest.
4. Keep ImageGen drawings as stress cases. Add duplicate IDs, unit ambiguity and contradictory dimensions. Evaluate separately on rights-cleared real drawings held out from development before downstream adoption.
