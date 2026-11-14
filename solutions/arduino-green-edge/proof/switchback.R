#!/usr/bin/env Rscript
# Randomized paired switchback *design*, and unverified paired trial analysis.
# 'plan' produces a plan, NOT actual randomized hardware execution.
# Usage: Rscript proof/switchback.R plan 12 > /tmp/green-switchback-plan.csv
#        Rscript proof/switchback.R analyze /path/to/observed-pairs.csv
library(stats)

fail <- function(message) stop(paste("Switchback refused:", message), call. = FALSE)
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) {
  fail("use 'plan PAIRS' or 'analyze OBSERVED_CSV'")
}

if (args[1] == "plan") {
  n <- suppressWarnings(as.integer(args[2]))
  if (is.na(n) || n < 4L || n > 48L || as.character(n) != args[2]) {
    fail("4..48 balanced pairs required")
  }
  set.seed(20261114)
  arm <- replicate(n, sample(c("SCHEDULE", "EDGE"), size = 2))
  plan <- data.frame(
    pair_id = rep(seq_len(n), each = 2),
    period_in_pair = rep(1:2, n),
    assigned_strategy = as.vector(arm),
    duration_minutes_planned = 60L,
    washout_minutes_planned = 15L,
    evidence = "PLANNED_NOT_EXECUTED",
    stringsAsFactors = FALSE
  )
  write.csv(plan, stdout(), row.names = FALSE)
  cat("PLANNED_ONLY: no hardware, intervention, carryover qualification, or meter data.\n",
    file = stderr())
  quit(status = 0L)
}
if (args[1] != "analyze" || !file.exists(args[2])) {
  fail("unknown action or missing CSV")
}

# Observed records must be independent period-level readings after washout.
# Nothing in an uploaded CSV certifies sensor calibration or randomization.
d <- read.csv(args[2], stringsAsFactors = FALSE, check.names = FALSE)
required <- c("pair_id", "period_in_pair", "assigned_strategy",
  "load_kwh", "device_kwh", "missed_service_seconds", "duration_seconds",
  "source_class")
if (!identical(names(d), required) || nrow(d) < 8 || nrow(d) > 96 ||
    anyNA(d) || nrow(d) %% 2L != 0L) fail("unexpected observed-pairs schema or size")
if (!all(d$source_class == "USER_SUPPLIED_UNVERIFIED") ||
    !all(d$assigned_strategy %in% c("SCHEDULE", "EDGE"))) {
  fail("no official measurement/verified status can be inferred from a file")
}
num <- c("pair_id", "period_in_pair", "load_kwh", "device_kwh",
  "missed_service_seconds", "duration_seconds")
if (!all(vapply(d[num], is.numeric, logical(1))) ||
    any(!is.finite(as.matrix(d[num]))) ||
    any(as.matrix(d[c("load_kwh", "device_kwh", "missed_service_seconds")]) < 0)) {
  fail("invalid finite numeric input")
}
pairs <- sort(unique(d$pair_id))
if (!identical(pairs, seq_len(nrow(d) / 2L))) fail("pair ids must be 1..N")
if (!all(d$period_in_pair %in% c(1, 2)) ||
    any(d$duration_seconds <= 0) || any(d$duration_seconds > 86400)) {
  fail("invalid period/duration")
}
diff <- numeric(length(pairs))
extra_service <- numeric(length(pairs))
for (p in pairs) {
  frame <- d[d$pair_id == p, , drop = FALSE]
  if (nrow(frame) != 2L || !setequal(frame$period_in_pair, c(1, 2)) ||
      !setequal(frame$assigned_strategy, c("SCHEDULE", "EDGE")) ||
      length(unique(frame$duration_seconds)) != 1L) {
    fail(sprintf("pair %d must have two equally long, opposite assigned arms", p))
  }
  a <- frame[frame$assigned_strategy == "SCHEDULE", ]
  b <- frame[frame$assigned_strategy == "EDGE", ]
  diff[p] <- a$load_kwh - b$load_kwh - b$device_kwh
  extra_service[p] <- max(0, b$missed_service_seconds - a$missed_service_seconds)
}

# Within-pair sign-flip randomization test is valid only if assignment truly
# randomized and no carryover/interference. These conditions cannot be
# established from an uploaded CSV. Numerical results remain UNVERIFIED.
set.seed(20261114)
n <- length(diff)
observed <- mean(diff)
if (n <= 15L) {
  patterns <- as.matrix(expand.grid(rep(list(c(-1, 1)), n)))
  null <- as.vector(patterns %*% diff / n)
} else {
  signs <- matrix(sample(c(-1, 1), n * 20000, replace = TRUE), ncol = n)
  null <- as.vector(signs %*% diff / n)
}
p_two_sided <- (sum(abs(null) >= abs(observed)) + 1) / (length(null) + 1)
ci <- if (n >= 3L && sd(diff) > max(1e-12, abs(mean(diff)) * 1e-10)) {
  t.test(diff, conf.level = 0.95)$conf.int
} else c(NA_real_, NA_real_)
cat("SOURCE=USER_SUPPLIED_UNVERIFIED\n")
cat("CAUSAL_IDENTIFICATION=NOT_VERIFIED\n")
cat(sprintf("pairs=%d\npaired_net_kwh_mean=%.8f\npaired_net_kwh_min=%.8f\n",
  n, observed, min(diff)))
cat(sprintf("nominal_paired_t_ci95=[%.8f,%.8f]\n", ci[1], ci[2]))
if (anyNA(ci)) cat("T_INTERVAL_NOT_ESTIMABLE=constant or insufficient pair variation\n")
cat(sprintf("conditional_signflip_p_two_sided=%.6f\n", p_two_sided))
cat(sprintf("pairs_with_incremental_missed_service=%d\n", sum(extra_service > 0)))
cat("NO_REAL_SAVING_OR_SAFETY_CLAIM: calibration, randomization, washout, carryover and missing-data audit are not proven by this file.\n")
