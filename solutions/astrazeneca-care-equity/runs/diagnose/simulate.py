"""What the scribe's measured interval errors do to the county indicator.  SYNTHETIC, local numpy only.

Unlike eventlog.design_study.measured_extraction_study (independent per-date errors drawn from the
type-matched date errors of the v2 adapter), this draws the error of each core interval from the
within-note interval errors measured on the 700 held-out notes (diagnose.py / resolve_relative.py):
for a pair of DAY-precision gold events in one note, err = predicted span - true span, so errors that
share an anchor inside a note stay correlated.  An interval is lost with the measured share of pairs
whose two endpoints were not both found (right type, DAY precision).  Negative spans are excluded as
in the detector.  Extra predicted events are not modelled.

Detector, reference and simulator are the repository's own (eventlog/).  Writes only runs/diagnose/.
Run from the solution root: eventlog/.venv/bin/python runs/diagnose/simulate.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from eventlog.design_study import pathways  # noqa: E402
from eventlog.detect import log_days, moments, test_moments  # noqa: E402
from eventlog.power import sample_size  # noqa: E402
from eventlog.schema import ENDPOINTS, INTERVALS  # noqa: E402
from eventlog.simulate import plant  # noqa: E402

OUT = ROOT / "runs" / "diagnose"
CORE = INTERVALS[:3]
TABLE_N_20 = dict(primary_care=473, diagnostic=513, treatment=347)  # DATA_COLLECTION.md section 2, 20%, one look
SIGMA = dict(primary_care=0.938, diagnostic=0.977, treatment=0.803)


def profile(path, writer="all"):
    iv = json.loads(Path(path).read_text())
    sel = [r for r in iv if writer == "all" or r["writer"] == writer]
    found = [r for r in sel if r.get("found")]
    err = np.array([r["err"] for r in found], float)
    ea = np.array([r["e_a"] for r in found], float)
    eb = np.array([r["e_b"] for r in found], float)
    return dict(err=err, ea=ea, eb=eb, keep=len(found) / len(sel), pairs=len(sel), found=len(found),
                exact=float(np.mean(err == 0)) if len(err) else None)


def noisy_logs(rng, t, prof, independent=False):
    """Log-durations of the three core intervals with the profile's interval errors; nan when lost."""
    a = np.rint(t)
    spans = np.stack([a[..., b] - a[..., s] for s, b in ENDPOINTS[:3]], axis=-1)
    if prof is None:
        return log_days(spans)
    k = len(prof["err"])
    if independent:
        e = prof["eb"][rng.integers(0, k, spans.shape)] - prof["ea"][rng.integers(0, k, spans.shape)]
    else:
        e = prof["err"][rng.integers(0, k, spans.shape)]
    obs = spans + e
    lost = rng.random(spans.shape) >= prof["keep"]
    obs = np.where(lost, np.nan, obs)
    return log_days(obs), obs, spans


def run_cell(rng, n, ratio, prof, ref_truth, reps, independent=False, ref_prof="same"):
    rp = prof if ref_prof == "same" else ref_prof
    ref = noisy_logs(rng, ref_truth, rp, independent)
    ref = ref if rp is None else ref[0]
    rmean, rvar, rn = moments(ref, axis=0)
    truth = pathways(rng, (reps, n))
    out = {}
    for stage in range(3):
        target = plant(truth, stage, ratio) if ratio != 1 else truth
        res = noisy_logs(rng, target, prof, independent)
        if prof is None:
            logs = res
            a = np.rint(target)
            obs = spans = np.stack([a[..., b] - a[..., s] for s, b in ENDPOINTS[:3]], axis=-1)
        else:
            logs, obs, spans = res
        mean, var, cnt = moments(logs)
        flag, z, located = test_moments(mean, var, cnt, rmean, rvar, rn)
        s = spans[..., stage]
        o = obs[..., stage]
        med_true = np.median(s, axis=1)
        med_obs = np.nanmedian(np.where(o >= 0, o, np.nan), axis=1)
        clean_sd = np.nanstd(log_days(s))
        noisy_sd = np.nanstd(logs[..., stage])
        out[CORE[stage]] = dict(located=float((located == stage).mean()), any_flag=float(flag.any(axis=-1).mean()),
                                median_bias_days=round(float(np.nanmean(med_obs - med_true)), 2),
                                median_abs_dev_days=round(float(np.nanmean(np.abs(med_obs - med_true))), 2),
                                true_median_days=round(float(med_true.mean()), 1),
                                log_sd_clean=round(float(clean_sd), 3), log_sd_noisy=round(float(noisy_sd), 3),
                                testable_mean=round(float(cnt[..., stage].mean()), 1),
                                negative_span_share=round(float(np.nanmean(o < 0)), 4))
        if ratio == 1:
            out[CORE[stage]] = dict(false_flag_any=float(flag.any(axis=-1).mean()))
            break  # null: one draw covers all three tests
    return out


def main():
    rng = np.random.default_rng(20261114)
    reps = 1000
    ref_truth = pathways(rng, (100_000,))
    files = {
        "C-270m-all-v2data as is": OUT / "intervals-C-270m-all-v2data.json",
        "C-270m-all-v2data + code resolver": OUT / "intervals-C-270m-all-v2data-resolved.json",
        "V3-270m-all as is": OUT / "intervals-V3-270m-all.json",
        "V3-270m-all + code resolver": OUT / "intervals-V3-270m-all-resolved.json",
        "v2-selected as is": OUT / "intervals-v2-selected.json",
        "S-1b-lora-r16 + code resolver": OUT / "intervals-S-1b-lora-r16-resolved.json",
    }
    profiles = {}
    for name, f in files.items():
        for w in ("all", "nemotron", "haiku"):
            profiles[(name, w)] = profile(f, w)
    result = dict(schema="scribe-interval-impact-v1", synthetic=True, reps=reps, reference_episodes=100_000,
                  error_model=__doc__.strip().split("\n\n")[1].replace("\n", " "), profiles={}, cells=[])
    for (name, w), p in profiles.items():
        e = p["err"]
        result["profiles"][f"{name} | {w}"] = dict(pairs=p["pairs"], found=p["found"], keep=round(p["keep"], 4),
                                                    exact_interval=round(p["exact"], 4), mean_err=round(float(e.mean()), 2),
                                                    sd_err=round(float(e.std(ddof=1)), 2), mad_err=float(np.median(np.abs(e))),
                                                    p90_abs=float(np.quantile(np.abs(e), .9)))
    conditions = [("confirmed (no error)", None)] + [(f"{name} | all", profiles[(name, "all")]) for name in files]
    for label, prof in conditions:
        for n in (500, 2000):
            cell = run_cell(rng, n, 1.3, prof, ref_truth, reps)
            result["cells"].append(dict(kind="planted 30%", condition=label, n=n, **cell))
            print(label, n, {k: (v["located"], v["median_bias_days"]) for k, v in cell.items()}, file=sys.stderr)
        # table n for 20%, one look (per interval)
        row = {}
        for stage, iname in enumerate(CORE):
            cell = run_cell(rng, TABLE_N_20[iname], 1.2, prof, ref_truth, reps)
            row[iname] = cell[iname]
        result["cells"].append(dict(kind="planted 20% at the table n (473/513/347)", condition=label, **row))
        # null, same error everywhere
        cell = run_cell(rng, 500, 1.0, prof, ref_truth, reps)
        result["cells"].append(dict(kind="null, same error in county and country", condition=label, n=500, **cell))
        if prof is not None:
            # independence check: same marginal endpoint errors, pairing broken
            cell = run_cell(rng, 500, 1.3, prof, ref_truth, reps, independent=True)
            result["cells"].append(dict(kind="planted 30%, endpoint errors drawn independently", condition=label, n=500, **cell))
            # county extracted, country from structured fields
            cell = run_cell(rng, 500, 1.0, prof, ref_truth, reps, ref_prof=None)
            result["cells"].append(dict(kind="null, county extracted, country structured", condition=label, n=500, **cell))
    # writer shift: county documentation like Haiku-written notes, country like Nemotron-written notes
    for name in files:
        cell = run_cell(rng, 500, 1.0, profiles[(name, "haiku")], ref_truth, reps, ref_prof=profiles[(name, "nemotron")])
        result["cells"].append(dict(kind="null, county errors from Haiku-written notes, country from Nemotron-written", condition=name, n=500, **cell))
    # analytic n inflation per interval for 20%: sigma_eff from the simulated noisy log-SD, divided by the kept share
    infl = {}
    for label, prof in conditions[1:]:
        c = next(x for x in result["cells"] if x["condition"] == label and x["kind"] == "planted 30%" and x["n"] == 2000)
        infl[label] = {}
        for iname in CORE:
            s_eff = c[iname]["log_sd_noisy"]
            s0 = c[iname]["log_sd_clean"]
            n0 = sample_size(1.2, s0)
            n1 = sample_size(1.2, s_eff, missingness=1 - prof["keep"])
            infl[label][iname] = dict(sigma_clean=s0, sigma_noisy=s_eff, n_needed_clean=n0, n_needed_noisy=n1,
                                      factor=round(n1 / n0, 2))
    result["n_inflation_20pct_one_look"] = infl
    (OUT / "interval-impact-v1.json").write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
