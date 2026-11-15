"""CPU-only tests. Run from the solution root: python -m unittest discover -s genomics/tests -t ."""
import json
import os
import random
import unittest

import numpy as np

from genomics import analyse as A
from genomics.fetch_data import col_index
from genomics.windows import build_windows, reverse_complement

HERE_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE_PKG)


class TestRankMetrics(unittest.TestCase):
    def test_auroc_hand_computed(self):
        # pairs (pos, neg): 3>1, 3>2, 3<3.5, 4>1, 4>2, 4>3.5  -> 5 of 6
        self.assertAlmostEqual(A.auroc([3, 4], [1, 2, 3.5]), 5 / 6, places=12)

    def test_auroc_ties_count_half(self):
        # pairs: 1<2 (0), 1>0 (1), 2=2 (0.5), 2>0 (1) -> 2.5 of 4
        self.assertAlmostEqual(A.auroc([1, 2], [2, 0]), 0.625, places=12)

    def test_auroc_extremes(self):
        self.assertEqual(A.auroc([5, 6], [1, 2]), 1.0)
        self.assertEqual(A.auroc([1, 2], [5, 6]), 0.0)

    def test_average_precision_hand_computed(self):
        # ranked by score: 1 0 1 1 0 -> precision at the positives 1/1, 2/3, 3/4
        ap = A.average_precision([0.9, 0.7, 0.6], [0.8, 0.5])
        self.assertAlmostEqual(ap, (1 + 2 / 3 + 3 / 4) / 3, places=12)

    def test_spearman_monotone(self):
        self.assertAlmostEqual(A.spearman([1, 2, 3, 4], [10, 20, 40, 80]), 1.0, places=12)


class TestAcmgBayes(unittest.TestCase):
    def test_tavtigian_strength_odds(self):
        # Tavtigian 2018: very strong 350, strong 18.7, moderate 4.3, supporting 2.08
        self.assertEqual(A.strength_lr("tavtigian2018", "very_strong"), 350.0)
        self.assertAlmostEqual(A.strength_lr("tavtigian2018", "strong"), 18.7, delta=0.05)
        self.assertAlmostEqual(A.strength_lr("tavtigian2018", "moderate"), 4.33, delta=0.05)
        self.assertAlmostEqual(A.strength_lr("tavtigian2018", "supporting"), 2.08, delta=0.005)

    def test_tavtigian_posteriors(self):
        # Table 1 footnote formula; prior 0.10: odds 350 -> 0.975, 81 -> 0.900, 1514 -> 0.994
        self.assertAlmostEqual(A.posterior(350, 0.10), 0.975, delta=0.0005)
        self.assertAlmostEqual(A.posterior(81, 0.10), 0.900, places=12)
        self.assertAlmostEqual(A.posterior(1514, 0.10), 0.994, delta=0.0005)
        self.assertGreater(A.posterior(350, 0.10), 0.90)       # one very strong criterion: likely pathogenic
        self.assertLess(A.posterior(350, 0.10), 0.99)          # but not pathogenic on its own

    def test_tavtigian_combination(self):
        # two strong criteria equal one very strong: 350^(2/2) = 350
        self.assertAlmostEqual(A.combined_lr("tavtigian2018", n_strong=2), 350.0, places=9)
        # one supporting benign criterion cancels one supporting pathogenic criterion
        self.assertAlmostEqual(A.combined_lr("tavtigian2018", n_supporting=1, b_supporting=1), 1.0, places=12)
        self.assertAlmostEqual(A.combined_lr("tavtigian2018", b_strong=1), 1 / 18.7, delta=0.0005)   # 0.053

    def test_pejaver_table1(self):
        # Pejaver 2022 Table 1: LR+ 2.406, 5.790, 33.53, 1124; posteriors 0.0999, 0.2108, 0.6073, 0.9811
        for s, lr, post in (("supporting", 2.406, 0.0999), ("moderate", 5.790, 0.2108),
                            ("strong", 33.53, 0.6073), ("very_strong", 1124, 0.9811)):
            self.assertAlmostEqual(A.strength_lr("pejaver2022", s), lr, delta=lr * 5e-4)
            self.assertAlmostEqual(A.posterior(A.strength_lr("pejaver2022", s), 0.0441), post, delta=5e-5)

    def test_strength_for_bound(self):
        self.assertEqual(A.strength_for_lr(1.5, "tavtigian2018", "pathogenic"), "none")
        self.assertEqual(A.strength_for_lr(2.1, "tavtigian2018", "pathogenic"), "supporting")
        self.assertEqual(A.strength_for_lr(5.0, "tavtigian2018", "pathogenic"), "moderate")
        self.assertEqual(A.strength_for_lr(20.0, "tavtigian2018", "pathogenic"), "strong")
        self.assertEqual(A.strength_for_lr(400.0, "tavtigian2018", "pathogenic"), "very_strong")
        self.assertEqual(A.strength_for_lr(0.6, "tavtigian2018", "benign"), "none")
        self.assertEqual(A.strength_for_lr(0.4, "tavtigian2018", "benign"), "supporting")
        self.assertEqual(A.strength_for_lr(0.05, "tavtigian2018", "benign"), "strong")


class TestBootstrapAndBins(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        self.pos = rng.normal(1.0, 1.0, 120)
        self.neg = rng.normal(0.0, 1.0, 300)

    def test_bootstrap_is_deterministic(self):
        a = A.with_interval(A.auroc, self.pos, self.neg, n_boot=200, seed=11)
        b = A.with_interval(A.auroc, self.pos, self.neg, n_boot=200, seed=11)
        c = A.with_interval(A.auroc, self.pos, self.neg, n_boot=200, seed=12)
        self.assertEqual(a, b)
        self.assertNotEqual(a["ci95"], c["ci95"])
        self.assertLess(a["ci95"][0], a["value"])
        self.assertGreater(a["ci95"][1], a["value"])

    def test_likelihood_ratio_table(self):
        t1 = A.local_likelihood_ratios(self.pos, self.neg, n_bins=5, n_boot=200, seed=3)
        t2 = A.local_likelihood_ratios(self.pos, self.neg, n_bins=5, n_boot=200, seed=3)
        self.assertEqual(t1, t2)
        self.assertEqual(sum(r["n_lof"] for r in t1["rows"]), 120)
        self.assertEqual(sum(r["n_func"] for r in t1["rows"]), 300)
        for r in t1["rows"]:
            self.assertLessEqual(r["lr_lower_95_one_sided"], r["lr_upper_95_one_sided"])
        self.assertGreater(t1["rows"][-1]["lr_plus"], t1["rows"][0]["lr_plus"])

    def test_lr_from_counts_hand_computed(self):
        # 10 of 99 positives and 4 of 199 negatives: (10.5/100) / (4.5/200) = 4.666...
        self.assertAlmostEqual(float(A.lr_from_counts(10, 4, 99, 199)), 0.105 / 0.0225, places=12)

    def test_thresholds_need_contiguous_bins(self):
        rows = [{"score_min": i, "score_max": i + 1, "lr_lower_95_one_sided": lo, "lr_upper_95_one_sided": up}
                for i, (lo, up) in enumerate([(0.01, 0.04), (0.1, 0.3), (0.5, 1.5), (3.0, 9.0), (1.0, 4.0), (25.0, 90.0)])]
        thr = A.thresholds_from_bins({"rows": rows}, "tavtigian2018")
        self.assertEqual(thr["pathogenic"]["strong"]["score_threshold"], 5)
        self.assertEqual(thr["pathogenic"]["supporting"]["score_threshold"], 5)   # bin 4 breaks the run
        self.assertEqual(thr["pathogenic"]["very_strong"]["score_threshold"], "none")
        self.assertEqual(thr["benign"]["supporting"]["score_threshold"], 2)
        self.assertEqual(thr["benign"]["strong"]["score_threshold"], 1)
        self.assertEqual(thr["benign"]["very_strong"]["score_threshold"], "none")
        scores = np.array([0.5, 1.0, 1.5, 2.0, 5.0, 5.5])
        share = A.shares_reaching(thr, scores, scores)
        self.assertEqual(share["pathogenic"]["strong"]["n_all_scored"], 2)      # 5.0 and 5.5
        self.assertEqual(share["benign"]["supporting"]["n_all_scored"], 3)      # 0.5, 1.0, 1.5 (2.0 is in the next bin)
        self.assertEqual(share["benign"]["very_strong"]["n_all_scored"], 0)

    def test_calibration_is_deterministic_and_bounded(self):
        s = np.concatenate((self.pos, self.neg))
        y = np.concatenate((np.ones(120), np.zeros(300)))
        c1, p1 = A.cross_fitted_calibration(s, y, 5, 5)
        c2, p2 = A.cross_fitted_calibration(s, y, 5, 5)
        self.assertEqual(c1, c2)
        self.assertTrue(np.all((p1 > 0) & (p1 < 1)))
        self.assertLess(c1["brier_score"], c1["brier_score_prevalence_only"])
        self.assertEqual(sum(r["n"] for r in c1["reliability_table"]), 420)


class TestClusterAndExactBounds(unittest.TestCase):
    def test_binomial_cdf_and_clopper_pearson(self):
        self.assertAlmostEqual(A.binom_cdf(1, 3, 0.5), 0.5, places=12)          # (1 + 3) / 8
        lo, up = A.clopper_pearson(0, 10, 0.05)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(up, 1 - 0.05 ** (1 / 10), places=9)               # closed form for k = 0
        lo, up = A.clopper_pearson(10, 10, 0.05)
        self.assertEqual(up, 1.0)
        self.assertAlmostEqual(lo, 0.05 ** (1 / 10), places=9)                   # closed form for k = n
        lo, up = A.clopper_pearson(3, 20, 0.025)
        self.assertAlmostEqual(A.binom_cdf(3, 20, up), 0.025, places=9)
        self.assertAlmostEqual(1 - A.binom_cdf(2, 20, lo), 0.025, places=9)

    def test_exact_bound_is_finite_and_cautious_for_an_empty_cell(self):
        # 10 loss-of-function against 0 functional: the smoothed point estimate is large, the exact bound is not
        lo, up = A.exact_lr_bounds(10, 105, 0, 295)
        self.assertEqual(up, float("inf"))
        self.assertGreater(lo, 1.0)
        self.assertLess(lo, float(A.lr_from_counts(10, 0, 105, 295)) / 5)
        self.assertEqual(A.strength_for_lr(lo, "tavtigian2018", "pathogenic"), "supporting")

    def test_table_uses_the_more_cautious_bound(self):
        rng = np.random.default_rng(3)
        pos, neg = rng.normal(1.0, 1.0, 90), rng.normal(0.0, 1.0, 210)
        gp, gn = np.arange(90) // 3, 1000 + np.arange(210) // 3
        t = A.local_likelihood_ratios(pos, neg, n_bins=5, n_boot=200, seed=3, groups_pos=gp, groups_neg=gn)
        for r in t["rows"]:
            self.assertLessEqual(r["lr_lower_95_one_sided"], r["lr_lower_exact"])
            self.assertGreaterEqual(r["lr_upper_95_one_sided"], r["lr_upper_exact"])
            if r["lr_lower_bootstrap"] is not None:
                self.assertGreaterEqual(min(r["n_lof"], r["n_func"]), A.MIN_BOOT_COUNT)
                self.assertLessEqual(r["lr_lower_95_one_sided"], r["lr_lower_bootstrap"])

    def test_cluster_bootstrap_keeps_positions_together_and_is_wider(self):
        groups = np.repeat(np.arange(40), 3)
        for idx in A.cluster_indices(groups, n_boot=20, seed=1):
            self.assertEqual(len(idx) % 3, 0)
            counts = np.bincount(groups[idx], minlength=40)
            self.assertTrue(np.all(counts % 3 == 0))                 # a position is in or out as a whole
        # perfectly correlated triplets: the cluster interval must be wider than the variant-level one
        rng = np.random.default_rng(5)
        base_p, base_n = rng.normal(0.6, 1, 40), rng.normal(0, 1, 100)
        pos, neg = np.repeat(base_p, 3), np.repeat(base_n, 3)
        gp, gn = np.repeat(np.arange(40), 3), np.repeat(1000 + np.arange(100), 3)
        a = A.with_interval(A.auroc, pos, neg, n_boot=400, seed=2)
        b = A.with_interval(A.auroc, pos, neg, n_boot=400, seed=2, groups_pos=gp, groups_neg=gn)
        self.assertAlmostEqual(a["value"], b["value"], places=12)
        self.assertGreater(b["ci95"][1] - b["ci95"][0], 1.3 * (a["ci95"][1] - a["ci95"][0]))
        self.assertEqual(b["bootstrap"]["positions"], 140)

    def test_paired_difference_of_a_score_with_itself_is_zero(self):
        rng = np.random.default_rng(6)
        pos, neg = rng.normal(1, 1, 30), rng.normal(0, 1, 60)
        d = A.paired_difference(A.auroc, pos, neg, pos, neg, np.arange(30), 100 + np.arange(60), n_boot=100, seed=1)
        self.assertEqual(d["value"], 0.0)
        self.assertEqual(d["ci95"], [0.0, 0.0])

    def test_grouped_folds_never_split_a_position(self):
        rng = np.random.default_rng(8)
        groups = np.repeat(np.arange(60), 3)
        y = np.repeat(rng.random(60) < 0.3, 3).astype(float)
        fold = A.grouped_folds(y, groups, 5, 1)
        for g in range(60):
            self.assertEqual(len(set(fold[groups == g])), 1)
        self.assertEqual(set(fold), set(range(5)))

    def test_consequence_only_predictor_is_cross_fitted(self):
        rows = []
        for i in range(60):
            for alt in "AC":
                rows.append({"pos": str(i), "ref": "G", "alt": alt, "func_class": "LOF" if i < 20 else "FUNC",
                             "consequence": "Nonsense" if i < 20 else "Synonymous"})
        p = A.consequence_only_scores(rows, 5, 1)
        lof = np.array([r["func_class"] == "LOF" for r in rows])
        self.assertEqual(A.auroc(p[lof], p[~lof]), 1.0)                 # consequence alone separates these
        self.assertTrue(np.all((p > 0) & (p < 1)))                      # smoothed, never exactly 0 or 1


class TestClusteredExactBound(unittest.TestCase):
    def test_incomplete_beta_hand_computed(self):
        # I_0.3(2, 5) = P(Binomial(6, 0.3) >= 2) = 1 - 0.7^6 - 6 * 0.3 * 0.7^5
        self.assertAlmostEqual(A.betainc_reg(2, 5, 0.3), 1 - 0.7 ** 6 - 6 * 0.3 * 0.7 ** 5, places=12)
        self.assertAlmostEqual(A.betainc_reg(1, 1, 0.37), 0.37, places=12)    # uniform

    def test_real_clopper_pearson_equals_integer_one(self):
        for k, n in ((0, 10), (3, 20), (10, 10), (7, 105), (39, 809), (67, 244)):
            for alpha in (0.025, 0.05):
                a, b = A.clopper_pearson(k, n, alpha), A.clopper_pearson_real(float(k), float(n), alpha)
                self.assertAlmostEqual(a[0], b[0], places=9)
                self.assertAlmostEqual(a[1], b[1], places=9)

    def test_design_effect(self):
        self.assertEqual(A.design_effect(np.repeat(np.arange(10), 3)), 3.0)     # triplets
        self.assertEqual(A.design_effect(np.arange(10)), 1.0)                   # singletons
        self.assertAlmostEqual(A.design_effect(np.array([1, 1, 2])), 5 / 3, places=12)
        self.assertEqual(A.design_effect(None), 1.0)

    def test_clustered_bound_is_wider_and_reduces_to_the_exact_one(self):
        lo, up = A.exact_lr_bounds(3, 448, 98, 1561)
        clo, cup = A.exact_lr_bounds_clustered(3.0, 448.0, 98.0, 1561.0, 2.2, 2.7)
        self.assertLess(clo, lo)
        self.assertGreater(cup, up)
        same = A.exact_lr_bounds_clustered(3.0, 448.0, 98.0, 1561.0, 1.0, 1.0)
        self.assertAlmostEqual(same[0], lo, places=9)
        self.assertAlmostEqual(same[1], up, places=9)

    def test_sparse_bins_use_the_clustered_bound(self):
        rng = np.random.default_rng(4)
        pos, neg = np.repeat(rng.normal(1.5, 1.0, 30), 3), np.repeat(rng.normal(0.0, 1.0, 100), 3)
        gp, gn = np.repeat(np.arange(30), 3), np.repeat(1000 + np.arange(100), 3)
        t = A.local_likelihood_ratios(pos, neg, n_bins=10, n_boot=200, seed=3, groups_pos=gp, groups_neg=gn)
        self.assertEqual(t["design_effect"]["lof"], 3.0)
        sparse = [r for r in t["rows"] if min(r["n_lof"], r["n_func"]) < A.MIN_BOOT_COUNT]
        self.assertTrue(sparse)
        for r in sparse:
            self.assertEqual(r["lr_lower_95_one_sided"], r["lr_lower_exact_clustered"])
            self.assertLessEqual(r["lr_lower_exact_clustered"], r["lr_lower_exact"])
        worst = A.worst_case_rows(t)["rows"]
        for r, w in zip(t["rows"], worst):
            self.assertLessEqual(w["lr_lower_95_one_sided"], r["lr_lower_95_one_sided"] + 1e-12)


class TestResultFile(unittest.TestCase):
    """Checks on the committed result file and README, when they exist."""
    PATH = os.path.join(ROOT, "data", "genomics", "brca1-evo2-v1.json")

    def setUp(self):
        if not os.path.exists(self.PATH):
            self.skipTest("no result file")
        with open(self.PATH) as fh:
            self.d = json.load(fh)
        if self.d["status"] == "not_run":
            self.skipTest("model not run")

    def test_headline_is_the_missense_result(self):
        h, d = self.d["headline"], self.d
        self.assertTrue(h["evidence_strength_basis"].startswith("missense"))
        self.assertEqual(h["missense_strongest_reached"], d["missense_evidence"]["strongest_reached"])
        self.assertEqual(h["auroc_lof_vs_func"]["value"], d["metrics"]["auroc_lof_vs_func"]["value"])
        self.assertEqual(h["auroc_missense"]["value"], d["metrics"]["auroc_by_consequence"]["Missense"]["value"])
        self.assertEqual(h["variants_scored"], d["data"]["variants_scored"])

    def test_counts_match_the_score_file(self):
        with open(os.path.join(ROOT, "data", "genomics", "evo2-scores.csv")) as fh:
            n = sum(1 for _ in fh) - 1
        self.assertEqual(self.d["data"]["variants_scored"], n)
        self.assertEqual(self.d["same_sample_comparison"]["n_variants"], n)
        self.assertEqual(self.d["status"], "partial" if n < self.d["data"]["variants_in_table"] else "complete")

    def test_one_interval_per_statistic(self):
        m, s = self.d["metrics"], self.d["same_sample_comparison"]["scores"]["evo2"]
        self.assertEqual(m["auroc_lof_vs_func"]["ci95"], s["auroc_lof_vs_func"]["ci95"])
        self.assertEqual(m["auroc_by_consequence"]["Missense"]["ci95"], s["auroc_missense"]["ci95"])

    def test_host_recorded_as_task_owned_and_no_placeholder_left(self):
        self.assertEqual(self.d["gpu_host"]["status"], "task-owned")
        self.assertNotIn("host_authorisation", self.d)
        for t in self.d["limits"]:
            self.assertNotIn("{", t)
            self.assertNotRegex(t.lower(), r"not approved|unapproved|owner confirmation")

    def test_readme_carries_the_result_file_figures(self):
        with open(os.path.join(HERE_PKG, "README.md")) as fh:
            readme = fh.read()
        a = self.d["metrics"]["auroc_lof_vs_func"]
        self.assertIn(f"{a['value']:.3f} ({a['ci95'][0]:.3f} to {a['ci95'][1]:.3f})", readme)
        self.assertIn(f"{self.d['data']['variants_scored']:,} of {self.d['data']['variants_in_table']:,} variants", readme)
        self.assertNotRegex(readme.lower(), r"parp|not approved|unapproved|owner confirmation")


class TestWindows(unittest.TestCase):
    def setUp(self):
        rnd = random.Random(1)
        self.seq = "".join(rnd.choice("ACGT") for _ in range(30000))

    def test_plus_strand_index(self):
        pos = 15000
        ref = self.seq[pos - 1]
        alt = "A" if ref != "A" else "C"
        w = build_windows(self.seq, pos, ref, alt, window=8192, strand="+")
        self.assertEqual(len(w["ref_seq"]), 8192)
        self.assertEqual(w["index"], 4096)                    # 4,096 upstream, the variant, 4,095 downstream
        self.assertEqual(w["start"], pos - 1 - 4096)
        self.assertEqual(w["ref_seq"][4096], ref)
        self.assertEqual(w["var_seq"][4096], alt)
        diff = [i for i in range(8192) if w["ref_seq"][i] != w["var_seq"][i]]
        self.assertEqual(diff, [4096])

    def test_minus_strand_index(self):
        pos = 15000
        ref = self.seq[pos - 1]
        alt = "A" if ref != "A" else "C"
        plus = build_windows(self.seq, pos, ref, alt, window=8192, strand="+")
        minus = build_windows(self.seq, pos, ref, alt, window=8192, strand="-")
        self.assertEqual(minus["index"], 8192 - 1 - 4096)     # 4095
        self.assertEqual(minus["ref_seq"], reverse_complement(plus["ref_seq"]))
        self.assertEqual(minus["var_seq"][4095], reverse_complement(alt))
        self.assertEqual(minus["ref_seq"][4095], reverse_complement(ref))
        diff = [i for i in range(8192) if minus["ref_seq"][i] != minus["var_seq"][i]]
        self.assertEqual(diff, [4095])

    def test_window_clipped_at_sequence_start(self):
        ref = self.seq[9]
        alt = "G" if ref != "G" else "T"
        w = build_windows(self.seq, 10, ref, alt, window=8192)
        self.assertEqual(w["start"], 0)
        self.assertEqual(w["index"], 9)
        self.assertEqual(w["var_seq"][9], alt)

    def test_reference_mismatch_is_rejected(self):
        ref = self.seq[99]
        wrong = "A" if ref != "A" else "C"
        with self.assertRaises(ValueError):
            build_windows(self.seq, 100, wrong, ref)

    def test_non_snv_is_rejected(self):
        with self.assertRaises(ValueError):
            build_windows(self.seq, 100, "AC", "A")

    def test_reverse_complement(self):
        self.assertEqual(reverse_complement("AACGT"), "ACGTT")

    def test_xlsx_column_index(self):
        self.assertEqual([col_index(c) for c in ("A1", "Z9", "AA3", "BJ10")], [0, 25, 26, 61])


if __name__ == "__main__":
    unittest.main()
