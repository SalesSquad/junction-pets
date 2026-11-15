"""Ground-truth-only selection of unused episodes for split deficits, within global cap."""

import asyncio, json, collections
from common import DATA, log
from generate import Pipeline
from sample import sample


async def main():
    p = Pipeline()
    i = 4000
    rows = [json.loads(x.read_text()) for x in (DATA / "cache").glob("*.json")]
    seen = {x["id"] for x in rows}
    counts = collections.Counter(x["split"] for x in rows if x.get("accepted"))
    used = []
    while p.usage["teacher_requests"] < 4500:
        wanted = (
            "val"
            if counts["val"] < 250
            else "test"
            if counts["test"] < 500
            else "train"
        )
        n = min(12, 4500 - p.usage["teacher_requests"])
        ids = []
        while len(ids) < n:
            row = sample(i)
            if (
                row["split"] == wanted
                and row["id"] not in seen
                and not (DATA / "cache" / f"{i:05d}.json").exists()
            ):
                ids.append(i)
                seen.add(row["id"])
            i += 1
        result = await asyncio.gather(*(p.one(j) for j in ids))
        used.extend(ids)
        counts.update(x["split"] for x in result if x.get("accepted"))
    await p.client.aclose()
    log(
        "split_topup",
        inputs={"indices": used},
        metrics={
            "counts_raw": dict(counts),
            "teacher_requests": p.usage["teacher_requests"],
        },
    )
    print(json.dumps({"counts_raw": dict(counts), "usage": p.usage}))


if __name__ == "__main__":
    asyncio.run(main())
