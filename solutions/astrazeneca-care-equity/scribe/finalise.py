"""Reconcile final code checks and verify explicit route statements; no teacher calls."""

import asyncio
import json

from common import DATA, log, save
from generate import Pipeline
from sample import ROUTES
from verify import accept, code_check


async def main():
    p = Pipeline()
    sem = asyncio.Semaphore(12)

    async def one(path):
        async with sem:
            row = json.loads(path.read_text())
            check = code_check(row)
            if row.get("code_check") != check:
                row.setdefault("code_check_history", []).append(row.get("code_check"))
                row["code_check"] = check
            if not check["ok"] or row.get("sampler_rejection"):
                row["accepted"] = False
            elif row.get("accepted") and "route" not in row["verifier_probabilities"]:
                q = {
                    "route": {
                        "type": "noul",
                        "instructions": f"Does the clinical note itself explicitly establish that the patient's cancer-pathway entry route was {ROUTES[row['entry_route']]} ({row['entry_route']})? Do not infer the route from the expected label. Absence of a stated entry route means no.",
                    }
                }
                result = await p.request(
                    "https://api.typesafe.ai/v1/systemone",
                    {
                        "model": "jev-latest",
                        "state": {
                            "note": row["note_text"],
                            "note_date": row["note_date"],
                        },
                        "questions": q,
                    },
                )
                row["verifier_probabilities"]["route"] = float(
                    result["answers"]["route"]["noul"]
                )
                row["accepted"] = accept(row["verifier_probabilities"])
            save(path, row)
            log(
                "episode_verified",
                inputs={
                    "cache": str(path.relative_to(DATA.parent.parent)),
                    "id": row["id"],
                },
                outputs={"accepted": row.get("accepted")},
                metrics={
                    "code_check": check,
                    "probabilities": row.get("verifier_probabilities"),
                },
            )

    await asyncio.gather(
        *(one(path) for path in sorted((DATA / "cache").glob("*.json")))
    )
    await p.client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
