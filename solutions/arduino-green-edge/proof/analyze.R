#!/usr/bin/env Rscript
# Green Edge Proof Lab: day-level risk and paired energy accounting, SYNTHETIC ONLY.
# Usage: Rscript proof/analyze.R /path/to/synthetic-days.csv > /tmp/summary.csv
# Every simulated day (not its 8640 ten-second slots) is one descriptive unit.
library(stats)

fail <- function(message) stop(paste("Green Proof refused:", message), call. = FALSE)
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L || !file.exists(args[1])) {
  fail("expected exactly one existing synthetic-day CSV path")
}
input <- read.csv(args[1], stringsAsFactors = FALSE, check.names = FALSE)
expected <- c(
  "evidence", "source_sha", "partition", "scenario", "seed",
  "shift_hours", "sensor_bias_c", "baseline_ws", "edge_load_ws",
  "gross_ws", "edge_only_unmet_s", "baseline_unmet_s",
  "edge_unmet_s", "fallback_fraction", "fault_slots", "disturbance_digest"
)
if (!identical(names(input), expected) || nrow(input) < 32L ||
    nrow(input) > 384L || anyNA(input)) fail("unexpected input schema, size or missing values")
parent <- "7aee5bd372fa32fa92306f0db9fab39bd2ca1567"
if (!all(input$evidence == "SYNTHETIC") || !all(input$source_sha == parent)) {
  fail("only exact-source SYNTHETIC M3 data is permitted; not a meter validator")
}
if (!setequal(input$partition, c("calibration", "heldout")) ||
    !setequal(input$scenario, c("winter", "summer", "evening", "fault"))) {
  fail("both partitions and all four predeclared scenarios required")
}
numeric_cols <- c("seed", "shift_hours", "sensor_bias_c", "baseline_ws",
  "edge_load_ws", "gross_ws", "edge_only_unmet_s", "baseline_unmet_s",
  "edge_unmet_s", "fallback_fraction", "fault_slots")
if (any(!vapply(input[numeric_cols], is.numeric, logical(1))) ||
    any(!is.finite(as.matrix(input[numeric_cols])))) fail("non-finite or nonnumeric observation")
if (any(input$seed < 0 | input$seed != floor(input$seed)) ||
    any(input$baseline_ws < 0 | input$edge_load_ws < 0) ||
    any(input$edge_only_unmet_s < 0 | input$baseline_unmet_s < 0 |
        input$edge_unmet_s < 0) ||
    any(input$fallback_fraction < 0 | input$fallback_fraction > 1) ||
    any(input$gross_ws != input$baseline_ws - input$edge_load_ws) ||
    any(input$edge_only_unmet_s > input$edge_unmet_s)) {
  fail("invalid energy, coverage, or missed-service arithmetic")
}
keys <- paste(input$partition, input$scenario, input$seed, sep = ":")
if (anyDuplicated(keys) || any(!grepl("^fnv1a32:[0-9a-f]{8}$", input$disturbance_digest))) {
  fail("duplicate day or malformed diagnostic digest")
}
counts <- table(input$partition, input$scenario)
if (any(counts < 4L) || any(counts != counts[1L])) {
  fail("balanced 4..48 day cohorts per partition/season are required")
}
for (scenario in unique(input$scenario)) {
  cal <- input$seed[input$scenario == scenario & input$partition == "calibration"]
  hold <- input$seed[input$scenario == scenario & input$partition == "heldout"]
  if (length(intersect(cal, hold))) fail("calibration / held-out seed leakage")
}

# Exact, one-sided Clopper-Pearson bound on *day-level* extra-service escapes.
# Four-season Bonferroni correction is conservative for these four strata.
binom_upper <- function(misses, days, alpha = 0.05 / 4) {
  if (misses == days) return(1)
  qbeta(1 - alpha, misses + 1, days - misses)
}
tail_mean <- function(values, fraction = 0.1) {
  n <- max(1L, ceiling(length(values) * fraction))
  mean(sort(values)[seq_len(n)])
}
# A descriptive bootstrap; synthetic seeds are not guaranteed independent days
# and its interval is NOT a real-world physical performance confidence interval.
set.seed(20261114)
bootstrap_lower <- function(values, reps = 500L) {
  n <- length(values)
  draws <- replicate(reps, mean(sample(values, n, replace = TRUE)))
  as.numeric(quantile(draws, probs = 0.05, names = FALSE, type = 7))
}
format_summary <- function(frame, overhead_w) {
  net <- (frame$gross_ws - overhead_w * 86400) / 3600000
  escaped <- frame$edge_only_unmet_s > 0
  fallback <- frame$fallback_fraction > 0.05
  upper <- binom_upper(sum(escaped), length(escaped))
  data.frame(
    partition = frame$partition[1], scenario = frame$scenario[1],
    overhead_w = overhead_w, synthetic_days = length(net),
    mean_net_kwh = mean(net),
    minimum_net_kwh = min(net),
    cvar10_net_kwh = tail_mean(net),
    descriptive_bootstrap_lcb05_kwh = bootstrap_lower(net),
    nonpositive_net_days = sum(net <= 0),
    extra_service_fail_days = sum(escaped),
    upper_95_bonferroni_service_escape = upper,
    baseline_unmet_minutes = sum(frame$baseline_unmet_s) / 60,
    edge_unmet_minutes = sum(frame$edge_unmet_s) / 60,
    extra_unmet_minutes = sum(frame$edge_only_unmet_s) / 60,
    excessive_fallback_days = sum(fallback),
    all_days_pass_simulated_gates = all(net > 0 & !escaped & !fallback),
    statistically_qualified = FALSE,
    physical_measurement = FALSE,
    stringsAsFactors = FALSE
  )
}
parts <- c("calibration", "heldout")
cases <- c("winter", "summer", "evening", "fault")
overheads <- c(0, 4, 8, 12, 30)
output <- do.call(rbind, lapply(parts, function(part) {
  do.call(rbind, lapply(cases, function(scenario) {
    frame <- input[input$partition == part & input$scenario == scenario, , drop = FALSE]
    do.call(rbind, lapply(overheads, function(w) format_summary(frame, w)))
  }))
}))
write.csv(output, stdout(), row.names = FALSE, na = "NA")
n_per_scenario <- counts[1L]
zero_miss_upper <- binom_upper(0, n_per_scenario)
cat(sprintf("GREEN_PROOF_EVIDENCE=SYNTHETIC; SOURCE_SHA=%s; DAYS_PER_PARTITION_SCENARIO=%d\n",
  parent, n_per_scenario), file = stderr())
cat(sprintf("GLOBAL_VERDICT=NOT_QUALIFIED; zero-miss upper day risk at n=%d is %.4f (4-stratum simultaneous correction)\n",
  n_per_scenario, zero_miss_upper), file = stderr())
cat("All positive gains remain counterfactual model outputs. No physical or causal claims.\n", file = stderr())
