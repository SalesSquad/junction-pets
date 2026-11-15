# Citation-region evaluation

Run `node benchmark/regions.mjs /absolute/path/regions.json`. No network, inference or drawings
are loaded. Independently annotated ground truth must be frozen before evaluating predictions.

Input example (synthetic; replace the SHA and boxes with your independent annotations):

```json
{
  "threshold": 0.5,
  "cases": [{
    "id": "synthetic-room-area",
    "expected": [{"sourceSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "page": 1, "box": [0, 0, 10, 10]}],
    "predicted": [{"sourceSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "page": 1, "box": [0, 0, 10, 10]}]
  }]
}
```

Boxes use `[xMin,yMin,xMax,yMax]` in the **same coordinate system and page orientation**.
Wrong source hash or page gives zero overlap. Use actual annotated bounds; a text insertion point
is not a box and must not receive fabricated extents. The existing entity-identity benchmark is
still appropriate for points and exact vector IDs. This scorer measures box overlap, not polygon
IoU or whether a cited region semantically supports an answer.

A maximum-cardinality bipartite matching at the threshold prevents duplicate predictions from
claiming the same expected region. Outputs include precision, recall, missing/extra regions and
mean IoU of matched pairs; unmatched regions reduce precision/recall. Matching maximizes count,
not total IoU. No predictions/labels yields null precision/recall, never a perfect score. Bounds:
10,000 cases, 200 predictions/labels each, 8 MiB CLI input. Score answer correctness separately.
No actual sponsor citation score has been measured with this new tool.
