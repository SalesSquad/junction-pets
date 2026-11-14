"""Zero-shot scoring of single-nucleotide variants with Evo 2 open weights.

Runs on the GPU box under /root/genomics (see remote_setup.sh). No NVIDIA/NGC key
and no Hugging Face token is used: the Apache-2.0 weights come from the public
Hugging Face repository of the Arc Institute.

Score (method of the ArcInstitute/evo2 BRCA1 notebook):
    delta = mean log-likelihood(alternate window) - mean log-likelihood(reference window)
Lower delta = the model finds the alternate sequence less likely than the reference.

Sub-commands
    probe   measure GPU memory and time per forward pass for several window sizes
    choose  pick the window from the probe result, a GPU memory limit and a time budget
    score   score every variant; resumable through a JSON-lines checkpoint

Columns written by `score` (keys plus model output only, no assay measurements):
    chrom,pos,ref,alt,window,win_start_1based,win_end_1based,snv_index,
    evo2_ref_score,evo2_var_score,evo2_delta_score   (library float32 path, as in the notebook)
    evo2_delta_score_f64                             (same definition, log-softmax and mean in float64)
    evo2_site_llr                                    (log P(alt | upstream) - log P(ref | upstream) at the variant base)

Research use only; not for clinical decisions.
"""
import argparse, csv, json, os, platform, random, subprocess, sys, time
from importlib import metadata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from windows import build_windows, read_first_fasta_record          # on the GPU box (flat directory)
except ImportError:                                                     # inside the repository package
    from genomics.windows import build_windows, read_first_fasta_record

OUT_FIELDS = ["chrom", "pos", "ref", "alt", "window", "win_start_1based", "win_end_1based", "snv_index",
              "evo2_ref_score", "evo2_var_score", "evo2_delta_score", "evo2_delta_score_f64", "evo2_site_llr"]


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def version(pkg):
    try:
        return metadata.version(pkg)
    except Exception:
        return None


def nvsmi_process_mib():
    try:
        out = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout
        for line in out.splitlines():
            pid, used = [x.strip() for x in line.split(",")[:2]]
            if int(pid) == os.getpid():
                return int(used)
    except Exception:
        pass
    return None


def nvsmi_gpu_used_mib():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return None


def checkpoint_identity(model_name):
    """Repository id, revision (commit) and weight-file sha256 as found in the local Hugging Face cache."""
    info = {"model_name": model_name}
    try:
        from evo2.utils import HF_MODEL_NAME_MAP
        from huggingface_hub import constants
        repo = HF_MODEL_NAME_MAP[model_name]
        info["hf_repo"] = repo
        snap_root = os.path.join(constants.HF_HUB_CACHE, "models--" + repo.replace("/", "--"), "snapshots")
        revs = sorted(os.listdir(snap_root))
        info["hf_revision"] = revs[-1] if len(revs) == 1 else revs
        weights = os.path.join(snap_root, revs[-1], model_name + ".pt")
        info["weights_file"] = model_name + ".pt"
        info["weights_bytes"] = os.path.getsize(weights)
        if os.path.islink(weights):            # the cache names each large blob by its sha256
            info["weights_sha256_from_cache_blob_name"] = os.path.basename(os.path.realpath(weights))
    except Exception as exc:
        info["identity_error"] = str(exc)[:200]
    return info


class Scorer:
    def __init__(self, model_name, cap_gib, use_kernels=False):
        import numpy as np
        import torch
        from evo2 import Evo2
        from evo2.scoring import logits_to_logprobs, prepare_batch
        self.np, self.torch = np, torch
        self._prepare_batch, self._logits_to_logprobs = prepare_batch, logits_to_logprobs
        self.free_before, self.total = torch.cuda.mem_get_info(0)
        torch.cuda.set_per_process_memory_fraction(min(1.0, cap_gib * 2 ** 30 / self.total), 0)
        t = time.time()
        self.evo2 = Evo2(model_name, use_kernels=use_kernels)
        self.load_seconds = round(time.time() - t, 2)
        self.model, self.tokenizer = self.evo2.model, self.evo2.tokenizer
        self.forward_passes = 0

    def env(self):
        torch = self.torch
        return {"gpu": torch.cuda.get_device_properties(0).name, "gpu_total_bytes": self.total,
                "gpu_free_bytes_before_load": self.free_before, "torch": torch.__version__,
                "torch_cuda": torch.version.cuda, "evo2": version("evo2"), "vtx": version("vtx"),
                "flash_attn": version("flash_attn"), "transformer_engine": version("transformer_engine"),
                "load_seconds": self.load_seconds, "gpu_bytes_allocated_after_load": torch.cuda.memory_allocated(0),
                "logits_dtype": getattr(self, "logits_dtype", None)}

    def logprobs(self, seq):
        """One forward pass. Returns (library float32 mean score, float64 per-position log-probabilities on GPU)."""
        torch, np = self.torch, self.np
        input_ids, _ = self._prepare_batch([seq], self.tokenizer, prepend_bos=False, device="cuda:0")
        with torch.inference_mode():
            logits, _ = self.model(input_ids)
            self.logits_dtype = str(logits.dtype)
            lib = self._logits_to_logprobs(logits, input_ids)                     # identical to evo2.scoring
            lib_mean = float(np.mean(lib.float().cpu().numpy()[0]))
            lp64 = torch.log_softmax(logits.double(), dim=-1)[:, :-1]
            lp64 = lp64.gather(2, input_ids[:, 1:].unsqueeze(-1)).squeeze(-1)[0]
        self.forward_passes += 1
        return lib_mean, lp64


def load_variants(path, limit=0):
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    return rows[:limit] if limit else rows


def cmd_probe(args):
    header, seq = read_first_fasta_record(args.fasta)
    rows = load_variants(args.variants, 1)
    pos, ref, alt = int(rows[0]["pos"]), rows[0]["ref"], rows[0]["alt"]
    m = {"label": "research use only; not for clinical decisions", "mode": "probe", "ts_utc": utc_now(),
         "host": platform.node(), "fasta_header": header, "cap_gib": args.cap_gib, "use_kernels": args.use_kernels,
         "gpu_used_mib_before_load_all_processes": nvsmi_gpu_used_mib(), "probe": []}
    sc = Scorer(args.model, args.cap_gib, args.use_kernels)
    torch = sc.torch
    m["checkpoint"] = checkpoint_identity(args.model)
    for w in [int(x) for x in args.windows.split(",")]:
        win = build_windows(seq, pos, ref, alt, window=w)
        entry = {"window": len(win["ref_seq"])}
        torch.cuda.reset_peak_memory_stats(0)
        try:
            lib, lp64 = sc.logprobs(win["ref_seq"])                                # warm-up
            torch.cuda.synchronize()
            t = time.time()
            for _ in range(args.repeats):
                lib, lp64 = sc.logprobs(win["ref_seq"])
            torch.cuda.synchronize()
            entry["seconds_per_forward"] = round((time.time() - t) / args.repeats, 4)
            entry["ref_score_library"] = lib
            entry["ref_score_f64"] = float(lp64.mean())
            api = float(sc.evo2.score_sequences([win["ref_seq"]], batch_size=1)[0])  # public API, for comparison
            entry["ref_score_public_api"] = api
            entry["abs_diff_library_vs_public_api"] = abs(api - lib)
            entry["status"] = "ok"
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc)[:300]
        entry["peak_allocated_bytes"] = torch.cuda.max_memory_allocated(0)
        entry["peak_reserved_bytes"] = torch.cuda.max_memory_reserved(0)
        entry["nvidia_smi_process_mib"] = nvsmi_process_mib()
        m["probe"].append(entry)
        print(json.dumps(entry), flush=True)
        if entry["status"] != "ok":
            torch.cuda.empty_cache()
            break
    m.update(sc.env())
    with open(args.metrics, "w") as fh:
        json.dump(m, fh, indent=1)


def cmd_choose(args):
    """Largest probed window that stays under the memory limit and whose projected full run fits the
    time budget. If no window fits the budget, the smallest window that fits in memory is taken and
    the run stops at the budget (the variants scored are then a random sample of positions)."""
    probe = json.load(open(args.probe))
    rows = load_variants(args.variants)
    n_forward = len(rows) + len({r["pos"] for r in rows})
    ok = [e for e in probe["probe"] if e["status"] == "ok" and e.get("nvidia_smi_process_mib") is not None
          and e["nvidia_smi_process_mib"] <= args.limit_mib]
    for e in ok:
        e["projected_seconds_full_run"] = round(e["seconds_per_forward"] * n_forward, 1)
    fits = [e for e in ok if e["projected_seconds_full_run"] <= args.budget_seconds]
    if args.prefer == "window":       # keep the largest window that fits in memory; coverage is what the budget allows
        pick = max(ok, key=lambda e: e["window"]) if ok else None
    else:                             # "coverage": score every variant, with the largest window that allows it
        pick = max(fits, key=lambda e: e["window"]) if fits else (min(ok, key=lambda e: e["window"]) if ok else None)
    decision = {"ts_utc": utc_now(), "n_forward_passes_full_run": n_forward, "limit_mib": args.limit_mib,
                "budget_seconds": args.budget_seconds, "prefer": args.prefer, "candidates": ok,
                "window": pick["window"] if pick else None,
                "full_run_expected_within_budget": bool(pick and pick in fits),
                "expected_share_of_forward_passes_within_budget": (min(1.0, round(args.budget_seconds / pick["projected_seconds_full_run"], 3)) if pick else None),
                "notebook_window": 8192, "deviates_from_notebook": bool(pick and pick["window"] != 8192)}
    with open(args.out, "w") as fh:
        json.dump(decision, fh, indent=1)
    print(decision["window"] if pick else 0)


def cmd_score(args):
    t0 = time.time()
    header, seq = read_first_fasta_record(args.fasta)
    rows = load_variants(args.variants, args.limit)

    groups, skipped = {}, []
    for row in rows:
        try:
            win = build_windows(seq, int(row["pos"]), row["ref"], row["alt"], window=args.window, strand=args.strand)
        except Exception as exc:
            skipped.append({"pos": row.get("pos"), "ref": row.get("ref"), "alt": row.get("alt"), "reason": str(exc)})
            continue
        groups.setdefault(win["ref_seq"], []).append((row, win))
    order = sorted(groups, key=lambda s: int(groups[s][0][0]["pos"]))
    random.Random(args.seed).shuffle(order)       # a run stopped early is then a random sample of positions

    done = {}
    if os.path.exists(args.checkpoint):
        with open(args.checkpoint) as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("window") == args.window and rec.get("strand", "+") == args.strand:
                    done[(str(rec["pos"]), rec["ref"], rec["alt"])] = rec
    n_resumed = len(done)

    m = {"label": "research use only; not for clinical decisions", "mode": "score", "ts_utc_start": utc_now(),
         "host": platform.node(), "fasta": os.path.basename(args.fasta), "fasta_header": header,
         "fasta_length": len(seq), "variants_file": os.path.basename(args.variants), "n_rows": len(rows),
         "n_skipped": len(skipped), "skipped_first10": skipped[:10], "n_unique_ref_windows": len(groups),
         "window": args.window, "strand": args.strand, "average_reverse_complement": False, "batch_size": 1,
         "prepend_bos": False, "cap_gib": args.cap_gib, "use_kernels": args.use_kernels, "seed": args.seed,
         "n_resumed_from_checkpoint": n_resumed,
         "gpu_used_mib_before_load_all_processes": nvsmi_gpu_used_mib()}

    sc = Scorer(args.model, args.cap_gib, args.use_kernels)
    torch = sc.torch
    m["checkpoint"] = checkpoint_identity(args.model)
    torch.cuda.reset_peak_memory_stats(0)
    t_score, stopped_early, n_groups_done, max_nvsmi = time.time(), False, 0, None
    with open(args.checkpoint, "a") as ck:
        for gi, ref_seq in enumerate(order):
            members = groups[ref_seq]
            todo = [(row, win) for row, win in members if (str(row["pos"]), row["ref"].upper(), row["alt"].upper()) not in done]
            if todo:
                if args.max_seconds and time.time() - t_score > args.max_seconds:
                    stopped_early = True
                    break
                ref_lib, ref_lp = sc.logprobs(ref_seq)
                for row, win in todo:
                    var_lib, var_lp = sc.logprobs(win["var_seq"])
                    k = win["index"]
                    rec = {"chrom": row.get("chrom", ""), "pos": str(row["pos"]), "ref": row["ref"].upper(),
                           "alt": row["alt"].upper(), "window": args.window, "strand": args.strand,
                           "win_start_1based": win["start"] + 1, "win_end_1based": win["end"], "snv_index": k,
                           "evo2_ref_score": ref_lib, "evo2_var_score": var_lib,
                           "evo2_delta_score": var_lib - ref_lib,
                           "evo2_delta_score_f64": float((var_lp - ref_lp).sum() / var_lp.numel()),
                           "evo2_site_llr": float(var_lp[k - 1] - ref_lp[k - 1]) if k >= 1 else None}
                    done[(rec["pos"], rec["ref"], rec["alt"])] = rec
                    ck.write(json.dumps(rec) + "\n")
                ck.flush()
            n_groups_done += 1
            if gi % 25 == 0:
                el = time.time() - t_score
                mib = nvsmi_process_mib()
                max_nvsmi = mib if max_nvsmi is None else max(max_nvsmi, mib or 0)
                rate = el / max(1, sc.forward_passes)
                print(json.dumps({"ts": utc_now(), "groups_done": n_groups_done, "groups_total": len(order),
                                  "variants_done": len(done), "forward_passes": sc.forward_passes,
                                  "elapsed_s": round(el, 1), "s_per_forward": round(rate, 4),
                                  "nvidia_smi_process_mib": mib}), flush=True)
    torch.cuda.synchronize()
    score_seconds = time.time() - t_score
    mib = nvsmi_process_mib()
    max_nvsmi = mib if max_nvsmi is None else max(max_nvsmi, mib or 0)

    recs = sorted(done.values(), key=lambda r: (int(r["pos"]), r["alt"]))
    with open(args.out, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(OUT_FIELDS)
        for r in recs:
            wr.writerow([r["chrom"], r["pos"], r["ref"], r["alt"], r["window"], r["win_start_1based"],
                         r["win_end_1based"], r["snv_index"], repr(r["evo2_ref_score"]), repr(r["evo2_var_score"]),
                         repr(r["evo2_delta_score"]), repr(r["evo2_delta_score_f64"]),
                         "" if r["evo2_site_llr"] is None else repr(r["evo2_site_llr"])])
    m.update(sc.env())
    m.update({"ts_utc_end": utc_now(), "n_scored": len(recs), "complete": (not stopped_early) and len(recs) == len(rows) - len(skipped),
              "stopped_early_by_time_budget": stopped_early, "forward_passes_this_run": sc.forward_passes,
              "score_seconds_this_run": round(score_seconds, 2),
              "seconds_per_forward": round(score_seconds / max(1, sc.forward_passes), 4),
              "seconds_per_variant_this_run": round(score_seconds / max(1, len(recs) - n_resumed), 4),
              "peak_allocated_bytes": torch.cuda.max_memory_allocated(0),
              "peak_reserved_bytes": torch.cuda.max_memory_reserved(0),
              "nvidia_smi_process_mib_max_sampled": max_nvsmi,
              "total_seconds_this_run": round(time.time() - t0, 2), "out": os.path.basename(args.out)})
    with open(args.metrics, "w") as fh:
        json.dump(m, fh, indent=1)
    print(json.dumps(m, indent=1), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("probe", "score"):
        p = sub.add_parser(name)
        p.add_argument("--fasta", required=True)
        p.add_argument("--variants", required=True, help="CSV with columns pos,ref,alt (1-based, plus-strand alleles)")
        p.add_argument("--metrics", required=True)
        p.add_argument("--model", default="evo2_7b_base")
        p.add_argument("--cap-gib", type=float, default=16.0, help="limit of the PyTorch allocator in GiB")
        p.add_argument("--use-kernels", action="store_true")
    sub.choices["probe"].add_argument("--windows", default="1024,2048,4096,8192")
    sub.choices["probe"].add_argument("--repeats", type=int, default=5)
    s = sub.choices["score"]
    s.add_argument("--out", required=True)
    s.add_argument("--checkpoint", required=True)
    s.add_argument("--window", type=int, default=8192)
    s.add_argument("--strand", default="+", choices=["+", "-"])
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--seed", type=int, default=20261114)
    s.add_argument("--max-seconds", type=float, default=0, help="stop cleanly after this many seconds of scoring")
    c = sub.add_parser("choose")
    c.add_argument("--probe", required=True)
    c.add_argument("--variants", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--limit-mib", type=int, default=17166, help="18 GB expressed in MiB as nvidia-smi reports it")
    c.add_argument("--budget-seconds", type=float, required=True)
    c.add_argument("--prefer", default="coverage", choices=["coverage", "window"])
    args = ap.parse_args()
    {"probe": cmd_probe, "score": cmd_score, "choose": cmd_choose}[args.cmd](args)


if __name__ == "__main__":
    main()
