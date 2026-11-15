#!/usr/bin/env Rscript
# Source-bound world-paired V11 terminal goal audit. Requires verified original export.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) stop("Usage: Rscript rokoko_r_v11_audit.R <verified-dir>")
root <- normalizePath(args[[1L]], mustWork = TRUE)
d <- read.csv(file.path(root, "v11-trials.csv"), stringsAsFactors = FALSE)
arms <- c("frozen_v5","frozen_v6","frozen_v8","v10_loss_informed","v11_goal_preserving")
stopifnot(nrow(d) == 800L, setequal(unique(d$strategy), arms),
          length(unique(d$seed)) == 160L,
          nrow(unique(d[c("seed","strategy")])) == 800L,
          nrow(unique(d[c("seed","world_hash","stratum")])) == 160L,
          all(table(d$seed) == 5L),
          length(unique(d$seed[d$stratum == "near"])) == 128L,
          length(unique(d$seed[d$stratum == "clear"])) == 32L,
          sum(d$full_transition_count) == 34992L,
          all(d$safe_goal %in% c(0L, 1L)), all(d$unsafe %in% c(0L, 1L)))
by_arm <- lapply(arms, function(a) d[d$strategy == a, , drop=FALSE])
names(by_arm) <- arms
stopifnot(all(vapply(by_arm, function(x) sum(x$safe_goal), 0L) == c(18L,14L,0L,9L,18L)),
          all(vapply(by_arm, function(x) sum(x$unsafe), 0L) == c(0L,0L,1L,1L,0L)))
m <- merge(by_arm$frozen_v5, by_arm$v11_goal_preserving, by="seed", all=TRUE,
           suffixes=c("_v5","_v11"), sort=TRUE)
stopifnot(nrow(m) == 160L, !anyNA(m),
          all(m$world_hash_v5 == m$world_hash_v11),
          all(m$stratum_v5 == m$stratum_v11))
calc <- function(stratum) {
  rows <- if (stratum == "all") m else m[m$stratum_v5 == stratum, , drop=FALSE]
  old <- rows$safe_goal_v5
  new <- rows$safe_goal_v11
  new_goals <- sum(old == 0L & new == 1L)
  lost_goals <- sum(old == 1L & new == 0L)
  changed <- sum(rows$full_transition_sha256_v5 != rows$full_transition_sha256_v11)
  discordant <- new_goals + lost_goals
  mc <- if (discordant) binom.test(new_goals, discordant, 0.5)$p.value else NA_real_
  set.seed(20261115L + nrow(rows))
  boot <- replicate(5000L, mean(sample(new-old, replace=TRUE)))
  bounds <- 100*quantile(boot, c(.025,.975), names=FALSE)
  data.frame(stratum=stratum, worlds=nrow(rows), v5_goals=sum(old), v11_goals=sum(new),
             gained=new_goals,lost=lost_goals,changed_traces=changed,
             delta_pp=100*mean(new-old),bootstrap_low_pp=bounds[1],
             bootstrap_high_pp=bounds[2],exact_mcnemar_p=mc)
}
result <- do.call(rbind, lapply(c("all","near","clear"), calc))
stopifnot(result$v5_goals == c(18L,6L,12L), result$v11_goals == c(18L,6L,12L),
          all(result$gained == 0L), all(result$lost == 0L),
          result$changed_traces[1] == 62L)
near <- m[m$stratum_v5 == "near",,drop=FALSE]
v5_reopen <- sum(near$forward_reopened_after_side_v5)
v11_reopen <- sum(near$forward_reopened_after_side_v11)
stopifnot(v5_reopen == 60L, v11_reopen == 108L)
# These exact intervals describe only the selected source TRAIN worlds.
loss_upper <- 100*binom.test(0L, 18L)$conf.int[2]
gain_upper <- 100*binom.test(0L, 142L)$conf.int[2]
write.csv(result, file.path(root,"v11-paired-results.csv"), row.names=FALSE, na="")
report <- c(
  "# CRACI Rokoko V11 — independent source-pinned R audit",
  "",
  "2026-11-15: TRAIN-only negative science, not new physics or model promotion.",
  "",
  "## Original source provenance",
  "",
  "- Hosted original run 43653579339: source-reported SUCCESS, no provider-signed attestation.",
  "- Outer original ZIP SHA256 bbf94c662fab3ac0efab3448c9e917dcce473a2644efc82a3f4835dd85792bae.",
  "- Product SHA ab6df4054ef6ed350b479469590a48046a0c0a68; harness b1938bee9dbca482f645b5dde3359de38e6c125e.",
  "- TRAIN JSON SHA256 c3b3b399344fa18eff7a303cf27e2a510ab9eb74111a6216df1ec11a906579df.",
  "- Full original option gzip SHA256 0a38081a43426ee4774d09d22886202aaf56d59f6b925a0a75cb2f2da14c848b.",
  "- Original source and public observation/shield contracts independently checked by Python: 512 initial public scans, 160 paired TRAIN worlds, 800 five-arm trials, 34,992 original options. The original full raw gzip is SHA checked, not independently replayed as MuJoCo physics.",
  "- Locked dev/cal/test/OOD not read. No actual glasses/robot data, new spending, model promotion or provider signature.",
  "",
  "## True goal: 250-tick safe terminal dwell (same-world paired)",
  "",
  "| Stratum | Worlds | Frozen V5 | V11 | New | Lost | Changed full traces | Delta pp |",
  "|---|---:|---:|---:|---:|---:|---:|---:|",
  sprintf("| %s | %d | %d | %d | %d | %d | %d | %.2f |",
          result$stratum,result$worlds,result$v5_goals,result$v11_goals,
          result$gained,result$lost,result$changed_traces,result$delta_pp),
  "",
  "- Zero paired goal discordances; exact McNemar test is non-informative (sometimes reported p=1). The observed zero change and bootstrap interval [0,0] do not establish equivalence.",
  paste0("- 0/18 observed V5 goal wins lost: exact two-sided 95% upper loss rate ",
         sprintf("%.2f%%",loss_upper)," *on selected TRAIN winners*; this does not prove future win preservation."),
  paste0("- 0/142 baseline failures recovered: exact two-sided 95% upper new-win rate ",
         sprintf("%.2f%%",gain_upper)," *on selected TRAIN failures*; this is not deployment generalization."),
  paste0("- Near forward reopening increased ",v5_reopen,"/128 to ",v11_reopen,
         "/128, while both completed exactly 6/128 true near goals. Reopening is a proxy."),
  "- Original full trajectories changed in 62/160 worlds, without any new terminal goals. V8 and V10 each recorded one unsafe on this cohort; V5 and V11 recorded zero.",
  "",
  "## Decision",
  "",
  "NO_GO. Preserve V11 negative science. Do not rerun these 517000+ worlds or tune on them. Separate V12 source owners already own any new 518000+ trial; this audit does not authorize execution or model promotion.",
  "",
  "Reproduce from original immutable V11 ZIP with scripts/craci/rokoko_r_v11_extract.py and scripts/craci/rokoko_r_v11_audit.R using an unused output directory."
)
writeLines(report, file.path(root, "ROKOKO_R_V11_AUDIT.md"))
cat("V11_R_AUDIT_SOURCE_PINNED_OK\n")
print(result,row.names=FALSE)
cat(sprintf("95%% upper loss among observed V5 wins %.2f%%; gain among baseline failures %.2f%%\n",
            loss_upper,gain_upper))
