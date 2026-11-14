#!/usr/bin/env Rscript
# Read-only paired TRAIN-world statistics for pinned original Rokoko CRACI archives.
# Base R only. The Python extractor verifies the byte-exact original artifacts.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) {
  stop("Usage: Rscript scripts/craci/rokoko_r_science_audit.R <verified-extraction-dir>")
}
root <- normalizePath(args[[1L]], mustWork = TRUE)
required_cols <- c("seed", "stratum", "world_hash", "strategy", "safe_goal",
                   "unsafe", "forward_reopened_after_side", "full_transition_count")

read_proof <- function(file, expected_rows, expected_arms) {
  d <- read.csv(file.path(root, file), stringsAsFactors = FALSE)
  stopifnot(all(required_cols %in% names(d)), nrow(d) == expected_rows)
  stopifnot(all(d$safe_goal %in% c(0L, 1L)), all(d$unsafe == 0L))
  stopifnot(setequal(unique(d$stratum), c("near", "clear")))
  stopifnot(setequal(unique(d$strategy), expected_arms))
  stopifnot(length(unique(d$seed)) == 160L)
  stopifnot(nrow(unique(d[c("seed", "strategy")])) == nrow(d))
  stopifnot(all(table(d$seed) == length(expected_arms)))
  stopifnot(nrow(unique(d[c("seed", "world_hash", "stratum")])) == 160L)
  stopifnot(length(unique(d$seed[d$stratum == "near"])) == 128L)
  stopifnot(length(unique(d$seed[d$stratum == "clear"])) == 32L)
  d
}

v10 <- read_proof("v10-trials.csv", 800L,
                  c("frozen_v5", "frozen_v6", "repeat_left", "frozen_v8",
                    "v10_loss_informed"))
hybrid <- read_proof("hybrid-trials.csv", 640L,
                     c("frozen_v5", "v8_hierarchical", "near-early-side-mask-rescue",
                       "rescue_off_v5"))
stopifnot(sum(v10$full_transition_count) == 38569L,
          sum(hybrid$full_transition_count) == 24167L,
          !any(v10$seed %in% hybrid$seed))

make_pair <- function(d, candidate, stratum = "all") {
  if (stratum != "all") d <- d[d$stratum == stratum, , drop = FALSE]
  a <- d[d$strategy == "frozen_v5", c("seed", "stratum", "world_hash", "safe_goal")]
  b <- d[d$strategy == candidate, c("seed", "stratum", "world_hash", "safe_goal")]
  merged <- merge(a, b, by = "seed", all = TRUE,
                  suffixes = c("_v5", "_candidate"))
  stopifnot(nrow(merged) == if (stratum == "all") 160L else
                                 if (stratum == "near") 128L else 32L)
  stopifnot(!anyNA(merged), all(merged$stratum_v5 == merged$stratum_candidate),
            all(merged$world_hash_v5 == merged$world_hash_candidate))
  merged
}

pair_stats <- function(run, d, candidate, stratum = "all") {
  m <- make_pair(d, candidate, stratum)
  y0 <- as.integer(m$safe_goal_v5)
  y1 <- as.integer(m$safe_goal_candidate)
  gained <- sum(y0 == 0L & y1 == 1L)
  lost <- sum(y0 == 1L & y1 == 0L)
  discordant <- gained + lost
  # Conditional exact McNemar: a two-sided sign test on same-world discordances.
  p <- if (discordant) binom.test(gained, discordant, p = 0.5)$p.value else NA_real_
  delta <- y1 - y0
  set.seed(20261115L + nrow(m) + nchar(run) + nchar(stratum))
  draws <- replicate(5000L, mean(sample(delta, length(delta), replace = TRUE)))
  ci <- as.numeric(quantile(draws, probs = c(0.025, 0.975), names = FALSE))
  data.frame(run = run, stratum = stratum, worlds = nrow(m),
             v5_safe_goals = sum(y0), candidate_safe_goals = sum(y1),
             novel = gained, lost = lost,
             delta_pp = 100 * mean(delta),
             bootstrap_lo_pp = 100 * ci[[1L]],
             bootstrap_hi_pp = 100 * ci[[2L]],
             exact_mcnemar_p = p, stringsAsFactors = FALSE)
}

summaries <- rbind(
  pair_stats("v10", v10, "v10_loss_informed", "all"),
  pair_stats("v10", v10, "v10_loss_informed", "near"),
  pair_stats("v10", v10, "v10_loss_informed", "clear"),
  pair_stats("hybrid", hybrid, "near-early-side-mask-rescue", "all"),
  pair_stats("hybrid", hybrid, "near-early-side-mask-rescue", "near"),
  pair_stats("hybrid", hybrid, "near-early-side-mask-rescue", "clear")
)
# Source qualification controls: fail closed rather than publish a changed dataset.
stopifnot(summaries$v5_safe_goals == c(37L, 12L, 25L, 30L, 15L, 15L))
stopifnot(summaries$candidate_safe_goals == c(26L, 10L, 16L, 30L, 15L, 15L))
stopifnot(summaries$novel == 0L,
          summaries$lost == c(11L, 2L, 9L, 0L, 0L, 0L))
stopifnot(sum(v10$unsafe) == 0L, sum(hybrid$unsafe) == 0L)

# Exploratory multiplicity correction only within disjoint near/clear strata.
p_adj <- p.adjust(summaries$exact_mcnemar_p[2:3], method = "holm")
p_heterogeneity <- fisher.test(matrix(
  c(9L, 32L - 9L, 2L, 128L - 2L), nrow = 2L,
  byrow = TRUE))$p.value
fmt_p <- function(x) if (is.na(x)) "N/A (zero discordance)" else
  format.pval(x, digits = 4, eps = 0.0001)
fmt <- function(x) sprintf("%.2f", x)
tab_lines <- apply(summaries, 1, function(z) {
  paste0("| ", z[["run"]], " | ", z[["stratum"]], " | ", z[["worlds"]],
         " | ", z[["v5_safe_goals"]], " | ", z[["candidate_safe_goals"]],
         " | ", z[["novel"]], " | ", z[["lost"]],
         " | ", fmt(as.numeric(z[["delta_pp"]])),
         " | [", fmt(as.numeric(z[["bootstrap_lo_pp"]])), ", ",
         fmt(as.numeric(z[["bootstrap_hi_pp"]])), "]",
         " | ", fmt_p(as.numeric(z[["exact_mcnemar_p"]])), " |")
})
report <- c(
  "# Rokoko CRACI — independent R statistics of original TRAIN physics",
  "",
  "2026-11-15. NO-GO for model promotion. No new training, physics runs, or hidden holdouts.",
  "",
  "## Exact input provenance",
  "",
  "- V10: run 43649224059, original ZIP SHA256 c9bd2ae587d16111213ae7f3e142976d39575850605c312d66cc63ce5e125ccb; source 9cc583d3f0f24484b79c1929ba875c7a3b667806; harness a64e6fcc73a1d47485fe052990e31c9d9e45100f; 800 original TRAIN trials, 38,569 option transitions.",
  "- Hybrid: run 43650587631, original ZIP SHA256 286f83c729303a7fe159d68ca494b94f51f685370ffff3e8578cefe62eaf5e0c; source 39f48031f7bff3970516a3c055efe47603e78be5; harness e977ee1eb9c64a3be75b9967e8153f89a7772d76; 640 original TRAIN trials, 24,167 option transitions. Hosted run overall FAILED in post-physics Python/NumPy check; original raw is forensic evidence, not green qualification.",
  "- Python verifies both outer ZIP SHA256 values, original raw pieces and full originals, pinned source/harness, 18-D observation and seven-option mask declarations, 160 complete paired worlds per run, and TRAIN-only/no-test flags.",
  "- No original CRACI source receipt is provider-signed. Cost is unknown. R analysis does not replay physics.",
  "",
  "## Same-world V5 comparisons",
  "",
  "| Run | World group | N | V5 goals | Candidate goals | New | Lost | Difference pp | Exploratory paired bootstrap 95% pp | Exact McNemar p |",
  "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
  tab_lines,
  "",
  paste0("- V10 near/clear exploratory Holm-adjusted p-values: ",
         fmt_p(p_adj[[1L]]), " / ", fmt_p(p_adj[[2L]]),
         ". Post-hoc difference in lost V5 wins between clear/near: Fisher exact p ",
         fmt_p(p_heterogeneity), ". This is hypothesis-generating."),
  "- Hybrid and V10 use DIFFERENT 160-world TRAIN cohorts and are not statistically pooled. Hybrid zero discordance does not establish equivalence on new worlds.",
  "- Bootstrap intervals resample source-selected TRAIN worlds, not robots, deployment scenes or locked dev/test/OOD. P-values are conditional and repeated selection weakens inference.",
  "",
  "## Engineering consequence",
  "",
  "- V10 loses 11 V5 safe goals and recovers zero: 9 losses in 32 clear worlds and 2 losses in 128 near worlds. Protect V5 goal wins and 250-tick terminal dwell before optimising proxy reopening.",
  "- Hybrid has zero gained and zero lost safe goals against frozen V5. Forward reopening as a proxy cannot establish terminal goal success.",
  "- Do not promote V10, hybrid or V8 or repeat known-negative cohorts. Distinct preregistered fresh TRAIN source and independent physics review would be needed for a new qualification.",
  "",
  "Recompute: python3 scripts/craci/rokoko_r_audit_extract.py --v10-zip V10.zip --hybrid-zip HYBRID.zip --output-dir NEW_DIR; Rscript scripts/craci/rokoko_r_science_audit.R NEW_DIR."
)
write.csv(summaries, file.path(root, "paired-results.csv"), row.names = FALSE, na = "")
writeLines(report, file.path(root, "ROKOKO_R_AUDIT.md"), useBytes = TRUE)
cat("R SOURCE-BOUND TRAIN AUDIT COMPLETE\n")
print(summaries[, c("run", "stratum", "v5_safe_goals", "candidate_safe_goals",
                    "novel", "lost", "delta_pp", "exact_mcnemar_p")],
      row.names = FALSE)
cat("output=", root, "\n", sep = "")
