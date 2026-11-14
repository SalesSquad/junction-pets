"""Fill the result and limits sections of genomics/README.md from data/genomics/brca1-evo2-v1.json,
so that every figure in the README is the figure in the result file.
Research use only; not for clinical decisions."""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STRENGTHS = ["supporting", "moderate", "strong", "very_strong"]


def f(x, n=3):
    return "n/a" if x is None else f"{x:.{n}f}"


def ci(v, n=3):
    if not v or v.get("value") is None:
        return "not computed"
    return f"{f(v['value'], n)} ({f(v['ci95'][0], n)} to {f(v['ci95'][1], n)})"


def thr_cell(acmg, direction, strength, fmt="{:.3g}"):
    t = acmg["thresholds"][direction][strength]["score_threshold"]
    if t == "none":
        return "none"
    sh = acmg["share_reaching_at_least"][direction][strength]
    op = ">=" if direction == "pathogenic" else "<"
    return f"s {op} {fmt.format(t)} ({100 * sh['share_of_all_scored']:.1f}% of scored variants)"


def strongest(x):
    return "not established" if not x else f"{x['pathogenic']} / {x['benign']}"


def comparison_table(d):
    """Like for like: every row is computed on exactly the scored variants."""
    c = d["same_sample_comparison"]
    names = {"evo2": f"Evo 2 7B base, {d['method']['window_bp']:,} bp window", "cadd": "CADD (column of the supplement)",
             "phylop_mammalian": "phyloP, mammalian (column of the supplement)",
             "consequence_only": "Consequence class only (no model, no sequence)"}
    a, ms = d["acmg_amp_evidence"], d["missense_evidence"].get("strongest_reached")
    rows = ["| Score | AUROC | AUROC, missense only | Average precision | Strongest evidence, LOF / functional direction, all consequences (Tavtigian 2018; Pejaver 2022) | Same, missense only |",
            "| --- | --- | --- | --- | --- | --- |"]
    for k, name in names.items():
        x = c["scores"][k]
        if k == "evo2":
            ev = f"{strongest(a['tavtigian2018']['strongest_reached'])}; {strongest(a['pejaver2022']['strongest_reached'])}"
            mv = "not established" if not ms else f"{strongest(ms['tavtigian2018'])}; {strongest(ms['pejaver2022'])}"
        elif "strongest_reached" in x:
            ev = f"{strongest(x['strongest_reached']['tavtigian2018'])}; {strongest(x['strongest_reached']['pejaver2022'])}"
            m2 = x.get("missense_strongest_reached")
            mv = "not established" if not m2 else f"{strongest(m2['tavtigian2018'])}; {strongest(m2['pejaver2022'])}"
        else:
            ev = mv = "not applicable"
        rows.append(f"| {name} | {ci(x['auroc_lof_vs_func'])} | {ci(x.get('auroc_missense')) if 'auroc_missense' in x else 'not applicable'} | {ci(x['average_precision_lof_vs_func'])} | {ev} | {mv} |")
    return rows


def full_table_baselines(d):
    b = d["baselines_from_supplement"]
    rows = ["| Score, all 3,893 variants | AUROC | AUROC, missense only | Strongest evidence, all consequences (Tavtigian 2018; Pejaver 2022) | Same, missense only |",
            "| --- | --- | --- | --- | --- |"]
    for k, name in (("cadd", "CADD"), ("phylop_mammalian", "phyloP, mammalian")):
        x = b[k]
        e = x["acmg_amp_evidence"]
        m2 = x.get("missense_strongest_reached")
        rows.append(f"| {name} | {ci(x['auroc_lof_vs_func'])} | {ci(x['auroc_by_consequence'].get('Missense'))} | "
                    f"{strongest(e['tavtigian2018']['strongest_reached'])}; {strongest(e['pejaver2022']['strongest_reached'])} | "
                    f"{'not established' if not m2 else strongest(m2['tavtigian2018']) + '; ' + strongest(m2['pejaver2022'])} |")
    if "consequence_only" in b:
        rows.append(f"| Consequence class only | {ci(b['consequence_only']['auroc_lof_vs_func'])} | not applicable | not applicable | not applicable |")
    return rows


def published(d):
    pv = d.get("published_values_not_reproduced") or {}
    L = ["### Published Evo 2 values, not reproduced here", ""]
    nb, bn = pv.get("arc_notebook"), pv.get("bionemo_framework_docs")
    if nb:
        L.append(f"- The Arc Institute BRCA1 notebook prints \"{nb['printed_line']}\" for `{nb['model']}` with a {nb['window_bp']:,} bp window "
                 f"({nb['definition']}). Source: <{nb['url']}>, read {nb['retrieved_utc'][:10]}.")
    if bn:
        L.append("- The NVIDIA BioNeMo Framework documentation lists " + ", ".join(f"{r['auroc']} for {r['model']}" for r in bn["rows"])
                 + f" on the same benchmark. Source: <{bn['url']}>, read {bn['retrieved_utc'][:10]}.")
    L += ["", "These are other people's numbers, obtained with the full 8,192 bp window. Nothing in this module reproduces or refutes them."]
    return L


def render_not_run(d):
    c = d["benchmark_check_without_model"]["assay_vs_clinvar"]
    a = c["assay_class_among_clinvar"]
    L = ["## Status: the Evo 2 scoring did not run", "",
         f"**There is no Evo 2 result in this module.** {d['status_reason']} `data/genomics/brca1-evo2-v1.json` has `status: \"not_run\"` and holds no model metric.", "",
         "### What the same analysis gives for two established scores", "",
         "CADD and phyloP are columns of the supplement, so they need no model run. Loss-of-function (823) against functional (2,821), intermediate (249) excluded; 95% intervals from 2,000 position-cluster bootstrap resamples.", ""]
    L += full_table_baselines(d)
    L += ["", "### Is the assay a fair proxy?", "",
          f"Among variants with a ClinVar label in the 2018 supplement, {a['pathogenic_or_likely']['LOF']} of {c['n_pathogenic_or_likely']} pathogenic or likely pathogenic variants are loss-of-function in the assay, and {a['benign_or_likely']['FUNC']} of {c['n_benign_or_likely']} benign or likely benign variants are functional. The assay's own function score separates the two groups with AUROC {ci(c['auroc_assay_function_score'])}.", ""]
    L += published(d)
    return L


SENS_HEAD = ("| {what} | LOF / functional direction (Tavtigian 2018) | LOF / functional direction (Pejaver 2022) | "
             "Most cautious bound in every bin (Tavtigian 2018; Pejaver 2022) | Top bin: loss-of-function, functional, lower bound |")


def sens_row(r):
    wc = r.get("strongest_reached_with_clustered_exact_bound_in_every_bin")
    worst = "n/a" if not wc else f"{strongest(wc['tavtigian2018'])}; {strongest(wc['pejaver2022'])}"
    return (f"| {r['n_bins']} | {strongest(r['strongest_reached']['tavtigian2018'])} | {strongest(r['strongest_reached']['pejaver2022'])} | {worst} | "
            f"{r['top_bin']['n_lof']}, {r['top_bin']['n_func']}, {r['top_bin']['lr_lower_95_one_sided']:.2f} |")


def mix(x):
    return ", ".join(f"{v} {k.lower()}" for k, v in sorted(x.items(), key=lambda kv: -kv[1])) or "none"


def render_result(d):
    m, a, rt, mo, da, me = d["metrics"], d["acmg_amp_evidence"], d["runtime"], d["model"], d["data"], d["method"]
    ms, wc, sc = d["missense_evidence"], d.get("windows_compared"), d["same_sample_comparison"]
    T = lambda cal, st: a[cal]["strength_targets"][st]["lr"]          # evidence targets, from the result file
    n, total = da["variants_scored"], da["variants_in_table"]
    cnt = m["counts_scored_by_class"]
    w = me["window_bp"]
    L = ["## Result: Evo 2 7B base on a sample of the BRCA1 benchmark", ""]
    gh = d.get("gpu_host")
    if gh:
        L += [f"**GPU host: {gh['status']}.** The scores were produced on `{gh['host']}` ({gh['gpu']}). {gh['basis']} "
              f"{gh['end_state']} Provenance and the sha256 of the files analysed: `gpu_host` in the result file.", ""]
    if d["status"] == "partial":
        L += [f"**Partial result.** {n:,} of {total:,} variants are analysed here ({100 * n / total:.0f}%), at {m['positions_scored']} positions. The positions are a random sample (seeded order). "
              f"{d.get('status_reason') or ''} All figures below describe that sample, and the intervals are wide.", ""]
    else:
        L += [f"All {n:,} variants were scored.", ""]
    L += [f"**Deviation from the published method.** {me['deviations_from_notebook'][0] if me['deviations_from_notebook'] else 'none'} "
          f"The PyTorch allocator was capped at {rt['cap_gib']:g} GiB to keep this job under 18 GB of GPU memory. "
          "The notebook's published value was obtained with 8,192 bp, so the figures here are not a reproduction of it.", "",
          f"Scored classes: loss-of-function {cnt['LOF']:,}, functional {cnt['FUNC']:,}, intermediate {cnt['INT']:,} (excluded from the main metrics). "
          "All intervals are 95% percentile intervals from 2,000 bootstrap resamples of positions: the two or three variants at a position share one reference window and usually one class, so they are resampled together.", ""]

    L += ["### In one paragraph", ""]
    ev_all = a["tavtigian2018"]["strongest_reached"]
    em = sc["evo2_minus"]
    zero_in = lambda v: v["ci95"][0] <= 0 <= v["ci95"][1]
    def versus(v, name, other):
        verdict = f"Evo 2 {'higher' if v['value'] > 0 else 'lower'}, interval {'includes' if zero_in(v) else 'excludes'} zero"
        return f"against {ci(other)} for {name} on the same variants (difference {ci(v)}: {verdict})"
    level_text = lambda x: (f"**{x['tavtigian2018']['pathogenic']}** in the LOF direction and **{x['tavtigian2018']['benign']}** in the functional direction "
                            f"(Tavtigian 2018; {x['pejaver2022']['pathogenic']} and {x['pejaver2022']['benign']} with the Pejaver 2022 targets)")
    msr, mwr = ms.get("strongest_reached"), ms.get("strongest_reached_with_clustered_exact_bound_in_every_bin")
    if not msr:
        missense_level = "the evidence level is not established"
    else:
        levels = {msr[k][d] for k in msr for d in ("pathogenic", "benign")}
        missense_level = ("the score reaches **no evidence level** in either direction" if levels == {"none"} else
                          f"the strongest level reached is {level_text(msr)}")
        if mwr and mwr != msr:
            missense_level += f"; with the most cautious bound in every bin it is {level_text(mwr).replace('**', '')}"
    L += ["**Headline (missense variants).** A computational ACMG/AMP criterion is meant for missense variants, so the evidence level for missense variants alone is the headline; "
          "the level on all consequences together is given for reference only.", "",
          f"On this sample Evo 2 separates loss-of-function from functional variants with AUROC {ci(m['auroc_lof_vs_func'])}, "
          f"{versus(em['cadd']['auroc_lof_vs_func'], 'CADD', sc['scores']['cadd']['auroc_lof_vs_func'])}, "
          f"and {versus(em['consequence_only']['auroc_lof_vs_func'], 'a lookup of the consequence class with no model', sc['scores']['consequence_only']['auroc_lof_vs_func'])}. "
          f"For missense variants, the class a computational criterion is meant for, the AUROC is {ci(m['auroc_by_consequence'].get('Missense'))}, "
          f"{versus(em['cadd']['auroc_missense'], 'CADD', sc['scores']['cadd']['auroc_missense'])}, and {missense_level}. "
          f"The Evo 2 figures use the {w:,} bp window, which was kept after an interim look at the data, so they are the larger of two estimates (see the next section). "
          f"On all consequences together the level is \"{ev_all['pathogenic']}\" in the LOF direction; the variants above that threshold are listed below by consequence, "
          "and canonical splice and nonsense variants, which other ACMG/AMP criteria already cover, are among them. "
          "The evidence level moves with the number of score bins (see the sensitivity rows), so none of these levels is a calibration.", ""]

    if wc:
        L += ["### Two windows on the same variants", "",
              f"{wc['n_variants']} variants ({wc['n_lof']} loss-of-function, {wc['n_func']} functional, {wc['n_positions']} positions) were scored with both windows. Neither is the main result: the run continued with the longer window after an interim look at the data.", "",
              "| Window | AUROC, loss-of-function against functional | AUROC, missense only |", "| --- | --- | --- |"]
        for k, v in wc["by_window"].items():
            L.append(f"| {int(k):,} bp | {ci(v['auroc_lof_vs_func'])} | {ci(v.get('auroc_missense'))} |")
        dd = wc["difference_longer_minus_shorter"]
        L += [f"| Difference, {dd['windows'][0]:,} minus {dd['windows'][1]:,} bp | {ci(dd['auroc_lof_vs_func'])} | {ci(dd['auroc_missense'])} |", "",
              f"Spearman correlation between the two scores: {f(wc['spearman_between_windows'])}. The answer for a variant depends on a run setting, so \"same variant, same answer\" holds only if the window is fixed and reported."]
        il = me["window_choice"].get("interim_look")
        if il:
            ks = sorted(il["auroc_by_window"], key=int)
            L += [f"The interim look that settled the window used the first {il['n_variants']} variants scored ({il['n_positions']} positions, {il['n_lof']} loss-of-function, {il['n_func']} functional): "
                  f"AUROC {f(il['auroc_by_window'][ks[1]])} at {int(ks[1]):,} bp against {f(il['auroc_by_window'][ks[0]])} at {int(ks[0]):,} bp. "
                  f"The detailed tables below use {w:,} bp, so its AUROC is the larger of two estimates."]
        wb = wc.get("window_minus_baseline")
        if wb:
            bs = wc["baselines_same_variants"]
            names = {"cadd": "CADD", "phylop_mammalian": "phyloP"}
            L += ["", f"Comparison that does not depend on the window choice: on the same {wc['n_variants']} variants, "
                  + "; ".join(f"{names[k]} reaches {ci(bs[k]['auroc_lof_vs_func'])} (missense only {ci(bs[k]['auroc_missense'])}), and Evo 2 minus {names[k]} is "
                              + " and ".join(f"{ci(v['auroc_lof_vs_func'])} at {int(win):,} bp" for win, v in sorted(wb[k].items(), key=lambda kv: int(kv[0])))
                              + " (missense only " + " and ".join(f"{ci(v['auroc_missense'])} at {int(win):,} bp" for win, v in sorted(wb[k].items(), key=lambda kv: int(kv[0]))) + ")"
                              for k in wb) + "."]
        L.append("")

    L += [f"### Detailed measures, {w:,} bp window", "",
          "| Measure | Value (95% interval) |", "| --- | --- |",
          f"| AUROC, loss-of-function against functional | {ci(m['auroc_lof_vs_func'])} |",
          f"| AUROC as in the notebook (functional and intermediate merged) | {ci(m['auroc_lof_vs_func_and_int'])} |",
          f"| Average precision (prevalence {f(m['average_precision_lof_vs_func']['prevalence_lof'])}) | {ci(m['average_precision_lof_vs_func'])} |",
          f"| Brier score after cross-fitted calibration, folds by position (predicting the prevalence: {f(m['calibration']['brier_score_prevalence_only'])}; folds by variant: {f(m['calibration']['brier_score_folds_by_variant'])}) | {f(m['calibration']['brier_score'])} |",
          f"| Expected calibration error, 10 bins | {f(m['calibration']['expected_calibration_error'])} |", ""]
    L += ["### By consequence", "", "| Consequence | Loss-of-function | Functional | AUROC (95% interval) |", "| --- | --- | --- | --- |"]
    for c, v in m["auroc_by_consequence"].items():
        L.append(f"| {c} | {v['n_lof']} | {v['n_func']} | {ci(v)} |")
    L += ["", "\"Not computed\" means fewer than 5 scored variants in one of the two classes. In the full table nonsense variants have no functional member and 5' UTR variants no loss-of-function member.", ""]

    L += ["### Compared with established scores on the same variants", ""]
    L += comparison_table(d)
    em = sc["evo2_minus"]
    L += ["", f"Paired differences in AUROC, Evo 2 minus the other score, on the same {sc['n_variants']} variants: "
          f"CADD {ci(em['cadd']['auroc_lof_vs_func'])} (missense only {ci(em['cadd']['auroc_missense'])}); "
          f"phyloP {ci(em['phylop_mammalian']['auroc_lof_vs_func'])} (missense only {ci(em['phylop_mammalian']['auroc_missense'])}); "
          f"consequence class only {ci(em['consequence_only']['auroc_lof_vs_func'])}. "
          + ("Every interval includes zero." if all(v["ci95"][0] <= 0 <= v["ci95"][1] for x in em.values() for v in x.values())
             else "Intervals that exclude zero: " + "; ".join(f"{k.replace('_', ' ')} ({kk.replace('auroc_', '').replace('_', ' ')})" for k, x in em.items() for kk, v in x.items()
                                                              if not v["ci95"][0] <= 0 <= v["ci95"][1]) + ".")
          + f" Evo 2's figures here use the {w:,} bp window, kept after an interim look, so they are the larger of two estimates; the section on the two windows gives each window against CADD and phyloP on the variants scored with both.", "",
          "For scale, the two supplement scores on the whole table (no model run needed):", ""]
    L += full_table_baselines(d)

    L += ["", "### What evidence strength could the score carry?", "",
          "The labels are assay classes, a laboratory proxy: \"LOF direction\" below means evidence towards loss-of-function in the assay, not a pathogenic classification. "
          "Likelihood ratios are taken over quantile bins of the score. In a bin with at least 5 variants of each class, the one-sided 95% bound is the more cautious of an exact bound "
          "(Clopper-Pearson on the two class shares) and the position bootstrap. In a sparser bin it is the exact bound on effective counts: each count is divided by the worst-case design effect "
          f"of position clustering (all-variant table: loss-of-function {d['likelihood_ratio_table']['design_effect']['lof']:.2f}, functional {d['likelihood_ratio_table']['design_effect']['func']:.2f}), "
          "which keeps the bound conservative however strongly the variants of a position are correlated. "
          "\"Most cautious\" below applies that effective-count bound in every bin. A threshold exists only if every bin beyond it also qualifies.", "",
          "**Missense variants only (the headline).** "]
    if ms.get("strongest_reached"):
        t, pj = ms["strongest_reached"]["tavtigian2018"], ms["strongest_reached"]["pejaver2022"]
        rows = ms["likelihood_ratio_table"]["rows"]
        top, bottom = rows[-1], rows[0]
        L[-1] += (f"{ms['n_lof']} loss-of-function and {ms['n_func']} functional missense variants in {ms['n_bins']} bins ({ms['bin_rule']}; the rule was set {ms['bin_rule_set']}). "
                  f"Strongest level reached: LOF direction **{t['pathogenic']}**, functional direction **{t['benign']}** (Tavtigian 2018); LOF direction **{pj['pathogenic']}**, functional direction **{pj['benign']}** (Pejaver 2022). "
                  f"Top bin: {top['n_lof']} loss-of-function against {top['n_func']} functional, likelihood ratio {top['lr_plus']:.2f}, lower bound {top['lr_lower_95_one_sided']:.2f}; supporting evidence needs {T('tavtigian2018', 'supporting'):.2f} (Tavtigian 2018) or {T('pejaver2022', 'supporting'):.2f} (Pejaver 2022). "
                  f"Bottom bin: {bottom['n_lof']} against {bottom['n_func']}, likelihood ratio {bottom['lr_plus']:.2f}, upper bound {bottom['lr_upper_95_one_sided']:.2f}; supporting evidence needs at most {1 / T('tavtigian2018', 'supporting'):.2f} or {1 / T('pejaver2022', 'supporting'):.2f}.")
        L += ["", SENS_HEAD.format(what="Bins (missense)"), "| --- | --- | --- | --- | --- |"]
        L += [sens_row(r) for r in ms["bin_count_sensitivity"]]
    else:
        L[-1] += ms.get("note", "Not established.")
    L += ["", "**All consequences together (for reference; see the consequence mix below).**", "",
          "| Strength | LOF direction (assay class, proxy), Tavtigian 2018 | Functional direction, Tavtigian 2018 | LOF direction, Pejaver 2022 | Functional direction, Pejaver 2022 |",
          "| --- | --- | --- | --- | --- |"]
    for st in STRENGTHS:
        L.append(f"| {st.replace('_', ' ').capitalize()} | {thr_cell(a['tavtigian2018'], 'pathogenic', st)} | {thr_cell(a['tavtigian2018'], 'benign', st)} | "
                 f"{thr_cell(a['pejaver2022'], 'pathogenic', st)} | {thr_cell(a['pejaver2022'], 'benign', st)} |")
    rows = d["likelihood_ratio_table"]["rows"]
    top, bottom = rows[-1], rows[0]
    L += ["", f"`s` is minus the delta log-likelihood. Top bin: {top['n_lof']} loss-of-function and {top['n_func']} functional variants, likelihood ratio {top['lr_plus']:.1f}, "
          f"lower bound {top['lr_lower_95_one_sided']:.2f}. Bottom bin: {bottom['n_lof']} and {bottom['n_func']}, likelihood ratio {bottom['lr_plus']:.3f}, upper bound {bottom['lr_upper_95_one_sided']:.2f}. "
          f"Moderate evidence needs {T('tavtigian2018', 'moderate'):.2f} (Tavtigian 2018) or {T('pejaver2022', 'moderate'):.2f} (Pejaver 2022) in the LOF direction, "
          f"strong evidence {T('tavtigian2018', 'strong'):.1f} or {T('pejaver2022', 'strong'):.2f}, and the reciprocals in the functional direction.", ""]
    for name, label in (("tavtigian2018", "Tavtigian 2018"), ("pejaver2022", "Pejaver 2022")):
        cm = a[name]["consequence_mix_at_or_above_pathogenic_threshold"]
        for st in STRENGTHS:
            x = cm.get(st)
            if x:
                L.append(f"- Variants at or above the {st.replace('_', ' ')} threshold ({label}, s >= {x['score_threshold']:.3g}): {x['n']} in all, "
                         f"{x['by_class']['LOF']} loss-of-function ({mix(x['lof_by_consequence'])}), {x['by_class']['FUNC']} functional ({mix(x['func_by_consequence'])}), {x['by_class']['INT']} intermediate.")
    L += ["", SENS_HEAD.format(what="Bins (all consequences)"), "| --- | --- | --- | --- | --- |"]
    L += [sens_row(r) for r in m["bin_count_sensitivity"]["rows"]]
    L += ["", "The analysis uses 20 bins, the script default since before any score existed; the other rows show how far the level depends on that choice. "
          "These ratios are measured against assay classes on the same variants that set the bins, which flatters them. They are not a ClinGen calibration and they classify no variant.", ""]

    c = m["clinvar_cross_check"]
    L += ["### ClinVar cross-check", "",
          f"On scored variants with a ClinVar label in the 2018 supplement ({c['n_pathogenic_or_likely']} pathogenic or likely pathogenic, {c['n_benign_or_likely']} benign or likely benign): "
          f"Evo 2 AUROC {ci(c.get('auroc_evo2'))}, CADD {ci(sc['scores']['cadd'].get('auroc_clinvar'))}, phyloP {ci(sc['scores']['phylop_mammalian'].get('auroc_clinvar'))}. "
          f"The pathogenic group is {mix(c['consequence_mix']['pathogenic_or_likely'])}; the benign group is {mix(c['consequence_mix']['benign_or_likely'])}. "
          "This subset therefore mostly separates truncating and splice changes from silent ones, which any of the three scores does. "
          f"The assay's own function score reaches {ci(c.get('auroc_assay_function_score'))} on the same variants, which shows how close the proxy is to the clinical labels.", ""]

    s = m["sensitivity"]
    L += ["### Sensitivity checks", ""]
    if "auroc_lof_vs_func_float64_delta" in s:
        L.append(f"- **Numerical precision.** The model returns bfloat16 logits and the library takes the log-softmax in that precision. Recomputing the delta in float64 from the same logits gives AUROC {f(s['auroc_lof_vs_func_float64_delta'])} "
                 f"(Spearman correlation with the library value {f(s['spearman_float32_vs_float64_delta'], 4)}).")
    if "auroc_lof_vs_func_site_log_likelihood_ratio" in s:
        site = s["auroc_lof_vs_func_site_log_likelihood_ratio"]
        tail = (" That is lower than the full delta, so much of the signal comes from how the variant changes the likelihood of the downstream sequence."
                if site < m["auroc_lof_vs_func"]["value"] - 0.05 else "")
        L.append(f"- **Variant base only.** Using only the log-likelihood ratio at the variant base, given the upstream context, gives AUROC {f(site)}.{tail}")
    L.append(f"- Spearman correlation between `s` and the assay's function score: {f(s['spearman_s_vs_assay_function_score'])}.")
    L += ["", "### Model, runtime and memory", "",
          f"- Checkpoint `{mo['repository']}`, revision `{mo['revision']}`, file `{mo['weights_file']}` ({mo['weights_bytes']:,} bytes, sha256 `{mo['weights_sha256']}` as named by the Hugging Face cache; not recomputed).",
          f"- {mo['gpu']}; evo2 {mo['packages']['evo2']}, vtx {mo['packages']['vtx']}, torch {mo['packages']['torch']}, flash-attn {mo['packages']['flash_attn']}; Transformer Engine not installed.",
          f"- {rt['seconds_per_forward']:.4f} s per forward pass at {w:,} bp in the run ({rt.get('seconds_per_forward_source') or 'run metrics'}); model load {rt['load_seconds']} s.",
          f"- GPU memory: {rt['peak_allocated_bytes'] / 1e9:.2f} GB peak allocated by PyTorch ({rt.get('peak_memory_source') or 'run metrics'}), {rt['nvidia_smi_process_mib_max_sampled']:,} MiB for the process in nvidia-smi during the run.", "",
          "Probe on the same GPU (one reference window, mean of 5 forward passes):", "",
          "| Window | Seconds per forward pass | Peak allocated | Process in nvidia-smi | Projected full run (5,219 passes) |", "| --- | --- | --- | --- | --- |"]
    for p in rt.get("probe", []):
        if p["status"] == "ok":
            L.append(f"| {p['window']:,} bp | {p['seconds_per_forward']:.4f} | {p['peak_allocated_bytes'] / 1e9:.2f} GB | {p['nvidia_smi_process_mib']:,} MiB | {p['seconds_per_forward'] * 5219 / 60:.1f} min |")
        else:
            L.append(f"| {p['window']:,} bp | out of memory under the {rt['cap_gib']:g} GiB allocator cap | | | |")
    L += [""]
    L += published(d)
    return L


def main():
    d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "genomics", "brca1-evo2-v1.json")))
    path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "README.md")
    s = open(path).read()
    result = "\n".join(render_not_run(d) if d["status"] == "not_run" else render_result(d))
    limits = "\n".join(f"- {t}" for t in d["limits"])
    s = re.sub(r"<!-- RESULT:BEGIN -->.*?<!-- RESULT:END -->", lambda _: f"<!-- RESULT:BEGIN -->\n{result}\n<!-- RESULT:END -->", s, flags=re.S)
    s = re.sub(r"<!-- LIMITS:BEGIN -->.*?<!-- LIMITS:END -->", lambda _: f"<!-- LIMITS:BEGIN -->\n{limits}\n<!-- LIMITS:END -->", s, flags=re.S)
    open(path, "w").write(s)
    print(f"README sections rendered for status {d['status']}")


if __name__ == "__main__":
    main()
