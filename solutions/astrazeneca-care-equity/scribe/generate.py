"""Resumable teacher + semantic verification, with persistent request reservations."""

import argparse
import asyncio
import json
import os
import random
import time

import httpx
from common import DATA, log, save
from sample import ROUTES, sample
from verify import accept, code_check, questions

MODEL = "nemotron-3.5-super-vl"


class Pipeline:
    def __init__(self):
        self.ledger = DATA / "usage.json"
        self.usage = (
            json.loads(self.ledger.read_text())
            if self.ledger.exists()
            else dict(
                teacher_requests=0,
                typesafe_tokens=0,
                typesafe_requests=0,
                typesafe_reserved=0,
            )
        )
        self.sem = asyncio.Semaphore(12)
        self.client = httpx.AsyncClient(timeout=120)

    def persist(self):
        save(self.ledger, self.usage)

    async def request(self, url, body, teacher=False):
        for attempt in range(4):
            if teacher:
                if self.usage["teacher_requests"] >= 4500:
                    raise RuntimeError("teacher cap")
                self.usage["teacher_requests"] += 1
                key = os.environ["VERDA_INFERENCE_KEY"]
            else:
                # Reserve a conservative 100k tokens per outstanding/request attempt, stop below $1.
                if (
                    self.usage["typesafe_tokens"]
                    + self.usage["typesafe_reserved"]
                    + 100000
                ) * 0.042 / 1e6 > 1:
                    raise RuntimeError("conservative spend stop")
                self.usage["typesafe_reserved"] += 100000
                self.usage["typesafe_requests"] += 1
                key = os.environ["TYPESAFE_API_KEY"]
            self.persist()
            t = time.monotonic()
            try:
                resp = await self.client.post(
                    url, headers={"Authorization": "Bearer " + key}, json=body
                )
                if resp.status_code != 200:
                    raise RuntimeError("HTTP " + str(resp.status_code))
                result = resp.json()
                usage = result.get("usage", {})
                if not teacher:
                    if "input_tokens" not in usage or "output_tokens" not in usage:
                        raise RuntimeError("missing token usage")
                    self.usage["typesafe_tokens"] += (
                        usage["input_tokens"] + usage["output_tokens"]
                    )
                    self.usage["typesafe_reserved"] -= 100000
                self.persist()
                log(
                    "teacher_call" if teacher else "verifier_call",
                    inputs={"model": body["model"]},
                    metrics={"usage": usage, "seconds": time.monotonic() - t},
                    cost_usd=(
                        usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                    )
                    * 0.042
                    / 1e6
                    if not teacher
                    else None,
                )
                return result
            except Exception as exc:
                # Unknown billed failed requests retain reservation and cost stays unknown.
                log(
                    "teacher_call" if teacher else "verifier_call",
                    metrics={
                        "attempt": attempt,
                        "error": type(exc).__name__,
                        "detail": str(exc)
                        if isinstance(exc, RuntimeError)
                        else "transport error",
                    },
                    cost_usd=None,
                    status="error",
                )
                if attempt == 3:
                    raise
                await asyncio.sleep(2**attempt + random.random())

    async def judge(self, row, strict=False):
        result = await self.request(
            "https://api.typesafe.ai/v1/systemone",
            dict(
                model="jev-latest",
                state={
                    "note": row["note_text"],
                    "note_date": row["note_date"],
                    "expected_events": row["facts"],
                    "entry_route": row["entry_route"],
                },
                questions=questions(row, strict),
            ),
        )
        if set(result["answers"]) != set(questions(row, strict)):
            raise RuntimeError("missing verifier answers")
        return {k: float(v["noul"]) for k, v in result["answers"].items()}

    async def one(self, i):
        async with self.sem:
            row = sample(i)
            path = DATA / "cache" / f"{i:05d}.json"
            if path.exists():
                row = json.loads(path.read_text())
            if "accepted" in row:
                return row
            try:
                if "note_text" not in row:
                    facts = [
                        f"{f['meaning']}: {f['expression']}"
                        for f in row["facts"] + row["distractors"]
                    ]
                    prompt = (
                        f"Käytä luontevia kliinisiä lyhenteitä kuten pot., yt., anam., tk tai pkl (vain asiayhteyteen sopivia). Kirjoita merkintään pakollinen lause: 'Syöpäpolun tuloreitti on {ROUTES[row['entry_route']]}.' Kirjoita suomeksi kliininen {row['style']}, 90–120 sanaa (ehdoton vähimmäismäärä 60 sanaa). Potilas on täysin kuvitteellinen, nimiä ei käytetä. Tuloreitti on {ROUTES[row['entry_route']]}. Alla on KAIKKI sallitut päivätyt faktat. Käytä kaikki annetut päivämääräilmaukset täsmälleen alkuperäisessä muodossa. Älä lisää yhtään muuta päivämäärää tai tapahtumaa. Jos syntymäaikaa, rokotusta tai kontrollia ei ole luettelossa, älä mainitse niitä lainkaan. Jos luettelossa on kontrolli, se on vasta tulevaisuudessa. Varmista 60 sanan vähimmäismäärä lisäämällä neutraalia tekstiä tämänhetkisestä voinnista, toimintakyvystä, arjessa selviytymisestä ja potilaan saamasta yleisestä neuvonnasta. Älä lisää tutkimuksia, käyntejä tai hoitoja. Älä kirjoita otsikkoa tai luetteloa. Palauta vain valmis merkintä.\nMerkinnän viitepäivä on {row['note_date']}; älä tulosta viitepäivää. Kaikki luettelon varsinaiset tapahtumat liittyvät nimenomaan syöpäpolkuun.\nSALLITUT FAKTAT:\n"
                        + "\n".join(facts)
                    )

                    result = await self.request(
                        os.environ["VERDA_INFERENCE_BASE_URL"].rstrip("/")
                        + "/chat/completions",
                        dict(
                            model=MODEL,
                            messages=[
                                {
                                    "role": "system",
                                    "content": "You write Finnish clinical prose with strict length and factual constraints. Output 80 to 120 whitespace-separated Finnish words. Count words before responding. A 40-word note is invalid. Do not invent dates or dated events. All dated facts are supplied; no names. Use neutral current-status and counselling prose to reach at least 80 words.",
                                },
                                {
                                    "role": "user",
                                    "content": prompt
                                    + "\nKaikki luetellut faktat ovat pakollisia, myös syntymäaika ja rokotuskäynti jos ne luetellaan. Kirjoita vähintään 15 kokonaista lausetta. Kuvaa vointia ja neuvontaa riittävän laajasti, yhteensä 80–120 sanaa. Älä tiivistä alle 80 sanaan.",
                                },
                            ],
                            temperature=0.65,
                            max_tokens=650,
                            chat_template_kwargs={"enable_thinking": False},
                        ),
                        True,
                    )
                    row.update(
                        note_text=result["choices"][0]["message"]["content"] or "",
                        teacher_model=MODEL,
                        teacher_prompt=prompt,
                        teacher_prompt_version="v6-explicit-route",
                        teacher_usage=result.get("usage", {}),
                    )
                    save(path, row)
                row["code_check"] = code_check(row)
                if row["code_check"]["ok"]:
                    row["verifier_probabilities"] = await self.judge(row)
                    row["accepted"] = accept(row["verifier_probabilities"])
                else:
                    row.update(accepted=False, verifier_probabilities={})
                save(path, row)
                return row
            except Exception as exc:
                row["error"] = type(exc).__name__
                save(path, row)
                return row

    async def run(self, start, count):
        t = time.monotonic()
        rows = await asyncio.gather(*(self.one(i) for i in range(start, start + count)))
        log(
            "generation_batch",
            command=f"generate.py --start {start} --count {count}",
            metrics={
                "seconds": time.monotonic() - t,
                "count": count,
                "accepted": sum(r.get("accepted", False) for r in rows),
            },
        )
        print(
            json.dumps(
                {
                    "seconds": time.monotonic() - t,
                    "count": count,
                    "accepted": sum(r.get("accepted", False) for r in rows),
                    "usage": self.usage,
                }
            )
        )
        await self.client.aclose()


async def preflight():
    p = Pipeline()
    r = await p.client.get(
        os.environ["VERDA_INFERENCE_BASE_URL"].rstrip("/") + "/models",
        headers={"Authorization": "Bearer " + os.environ["VERDA_INFERENCE_KEY"]},
    )
    r.raise_for_status()
    ids = [x["id"] for x in r.json()["data"]]
    save(DATA / "models.json", {"ids": ids})
    log(
        "models",
        outputs=["data/scribe/models.json"],
        metrics={"requested_model_available": MODEL in ids},
    )
    print(json.dumps({"model_available": MODEL in ids}))
    await p.client.aclose()


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--start", type=int, default=0)
    a.add_argument("--count", type=int, default=20)
    a.add_argument("--preflight", action="store_true")
    args = a.parse_args()
    asyncio.run(
        preflight() if args.preflight else Pipeline().run(args.start, args.count)
    )
