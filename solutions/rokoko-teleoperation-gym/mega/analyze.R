#!/usr/bin/env Rscript
# Analyze actual paired MuJoCo episodes; R bootstrap draws are NOT physics runs.
library(stats)
library(grDevices)
library(graphics)

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 4L) {
  stop("Usage: Rscript analyze.R <result_dir> <csv_regex> <report_dir> <B>")
}
input_dir <- normalizePath(args[[1]], mustWork = TRUE)
pattern <- args[[2]]
report_dir <- args[[3]]
B <- as.integer(args[[4]])
if (is.na(B) || B < 100L || B > 50000L) {
  stop("Bootstrap replicates must be within 100..50000")
}
paths <- sort(list.files(input_dir, pattern = pattern, full.names = TRUE))
if (length(paths) < 1L) stop("No matching physics CSVs")
dir.create(report_dir, recursive = TRUE, showWarnings = FALSE)
policies <- c(
  "aligned_replay", "contact_feedback", "guarded_feedback", "safe_abstain"
)
regimes <- c(
  "nominal", "lateral_shift", "friction_mass", "sensor_dropout", "adversarial"
)

sha256_file <- function(path) {
  x <- system2("shasum", c("-a", "256", shQuote(path)), stdout = TRUE)
  if (length(x) != 1L) stop("Cannot check sha256")
  strsplit(trimws(x), "[[:space:]]+")[[1]][[1]]
}
manifest_string <- function(path, field) {
  l <- grep(paste0('"', field, '":'), readLines(path, warn = FALSE), value = TRUE)
  if (length(l) != 1L) stop(paste("No unique manifest field:", field))
  value <- sub('^.*: *"([^"]+)".*$', "\\1", l, perl = TRUE)
  if (identical(value, l)) stop("Malformed manifest string")
  value
}
manifest_integer <- function(path, field) {
  l <- grep(paste0('"', field, '":'), readLines(path, warn = FALSE), value = TRUE)
  if (length(l) != 1L) stop(paste("No unique integer manifest field", field))
  v <- sub('^.*: *([0-9]+),? *$', "\\1", l)
  if (identical(v, l)) stop(paste("Invalid integer manifest field", field))
  as.integer(v)
}
manifest_source_hashes <- function(path) {
  lines <- readLines(path, warn = FALSE)
  from <- grep('"source_sha256": {', lines, fixed = TRUE)
  if (length(from) != 1L) stop("No source SHA256 manifest block")
  closes <- which(seq_along(lines) > from & grepl('^ *},? *$', lines))
  if (!length(closes)) stop("Unterminated source SHA256 manifest block")
  vals <- trimws(lines[seq.int(from + 1L, min(closes) - 1L)])
  if (!length(vals)) stop("Empty source hash map")
  pattern <- '^"([^"]+)": *"([0-9a-f]{64})",?$'
  matches <- regmatches(vals, regexec(pattern, vals, perl = TRUE))
  if (any(lengths(matches) != 3L)) stop("Malformed source hash map")
  key <- vapply(matches, function(x) x[[2]], character(1))
  value <- vapply(matches, function(x) x[[3]], character(1))
  if (anyDuplicated(key)) stop("Duplicate source digest key")
  stats::setNames(value, key)
}
source_root <- normalizePath(file.path(input_dir, "..", ".."), mustWork = TRUE)
sources <- character(0)
source_hash_sets <- character(0)
plan_counts <- shard_counts <- shard_indexes <- seed_bases <- integer(0)
for (p in paths) {
  manifest <- sub("\\.csv$", ".manifest.json", p)
  if (!file.exists(manifest)) stop(paste("Missing manifest for", p))
  expected <- manifest_string(manifest, "raw_csv_sha256")
  if (!identical(expected, sha256_file(p))) {
    stop(paste("CSV SHA256 mismatch for", p))
  }
  sources <- c(sources, manifest_string(manifest, "source_commit"))
  plan_counts <- c(plan_counts, manifest_integer(manifest, "total_case_plan"))
  shard_counts <- c(shard_counts, manifest_integer(manifest, "shards"))
  shard_indexes <- c(shard_indexes, manifest_integer(manifest, "local_shard"))
  seed_bases <- c(seed_bases, manifest_integer(manifest, "seed_base"))
  hashes <- manifest_source_hashes(manifest)
  source_hash_sets <- c(source_hash_sets,
                        paste(names(hashes), hashes, collapse = ";"))
  # Validate actual currently accessible producer bytes against exact receipts,
  # not only a Git HEAD which could hide a dirty code tree.
  for (name in names(hashes)) {
    f <- file.path(source_root, name)
    if (!file.exists(f) || !identical(sha256_file(f), unname(hashes[[name]]))) {
      stop(paste("Producer source hash mismatch", name))
    }
  }
}
if (length(unique(sources)) != 1L || length(unique(source_hash_sets)) != 1L) {
  stop("Mixed source SHAs or inconsistent source file bytes")
}
if (length(unique(plan_counts)) != 1L ||
    length(unique(shard_counts)) != 1L ||
    length(unique(seed_bases)) != 1L ||
    shard_counts[[1]] != length(paths) ||
    !identical(sort(shard_indexes), seq.int(0L, shard_counts[[1]] - 1L))) {
  stop("Campaign shard completeness/seed-base/source plan mismatch")
}
d <- do.call(rbind, lapply(paths, function(p) {
  read.csv(p, stringsAsFactors = FALSE, check.names = FALSE)
}))
rownames(d) <- NULL
needed <- c(
  "case_id", "seed", "regime", "policy", "safe_success", "damage_proxy",
  "final_goal_error_m", "false_success", "object_workspace_excursion",
  "object_obstacle_contact_steps", "pusher_obstacle_contact_steps",
  "pusher_object_contact_steps", "synthetic_human_requests",
  "unsafe_deadman_target_updates", "abstained", "goal_dwell_ticks",
  "peak_step_impulse_ns", "held_contact_impulse_ns"
)
if (!all(needed %in% names(d))) stop("Missing physics CSV fields")
if (!identical(sort(unique(d$policy)), sort(policies))) {
  stop("Unexpected or missing controller")
}
if (anyNA(d[, needed]) ||
    anyDuplicated(d[, c("case_id", "policy")])) {
  stop("Missing or duplicated physics episode")
}
if (!all(tapply(d$policy, d$case_id, length) == 4L)) {
  stop("Each case needs all four physics-policy trials")
}
if (any(d$safe_success < 0 | d$safe_success > 1)) {
  stop("Invalid success values")
}
one_seed <- aggregate(seed ~ case_id, d, function(z) length(unique(z)))
if (any(one_seed$seed != 1)) stop("Pairing seed mismatch")
n_cases <- length(unique(d$case_id))
n_runs <- nrow(d)
n_steps <- n_runs * 3000
if (n_cases != plan_counts[[1]] ||
    !identical(sort(unique(d$case_id)), seq.int(0L, n_cases - 1L)) ||
    any(d$seed != seed_bases[[1]] + d$case_id)) {
  stop("Campaign has missing/unexpected scenario IDs or wrong seed pairing")
}
d$unsafe <- as.integer(
  d$damage_proxy > 0 |
  d$object_obstacle_contact_steps > 0 |
  d$pusher_obstacle_contact_steps > 0 |
  d$object_workspace_excursion > 0 |
  d$unsafe_deadman_target_updates > 0
)
# Strict safety additionally excludes pusher-only obstacle strikes.
d$strict_success <- as.integer(d$safe_success > 0 & d$unsafe == 0L)
d$contact_episode <- as.integer(d$pusher_object_contact_steps > 0)

wilson <- function(k, n, z = qnorm(0.975)) {
  if (n < 1L) return(c(low = NA_real_, high = NA_real_))
  p <- k / n
  den <- 1 + z^2 / n
  center <- (p + z^2 / (2 * n)) / den
  half <- z / den * sqrt(p * (1 - p) / n + z^2 / (4 * n^2))
  c(low = max(0, center - half), high = min(1, center + half))
}

summarize_one <- function(policy) {
  x <- d[d$policy == policy, , drop = FALSE]
  ci <- wilson(sum(x$strict_success), nrow(x))
  data.frame(
    policy = policy, cases = nrow(x),
    strict_successes = sum(x$strict_success),
    success_rate = mean(x$strict_success),
    wilson_low = unname(ci[["low"]]),
    wilson_high = unname(ci[["high"]]),
    raw_goal_successes = sum(x$safe_success),
    unsafe_cases = sum(x$unsafe),
    broken_cases = sum(x$damage_proxy > 0),
    object_obstacle_cases = sum(x$object_obstacle_contact_steps > 0),
    pusher_obstacle_cases = sum(x$pusher_obstacle_contact_steps > 0),
    workspace_cases = sum(x$object_workspace_excursion > 0),
    deadman_command_violations = sum(x$unsafe_deadman_target_updates),
    contact_cases = sum(x$contact_episode),
    requests_not_actual_people = sum(x$synthetic_human_requests),
    abstained_cases = sum(x$abstained),
    mean_error_m = mean(x$final_goal_error_m),
    median_error_m = median(x$final_goal_error_m),
    max_impulse_ns = max(x$peak_step_impulse_ns),
    max_held_contact_impulse_ns = max(x$held_contact_impulse_ns)
  )
}
summary <- do.call(rbind, lapply(policies, summarize_one))
write.csv(summary, file.path(report_dir, "policy_summary.csv"),
          row.names = FALSE)

w <- reshape(
  d[, c("case_id", "regime", "policy", "strict_success", "unsafe",
        "damage_proxy", "final_goal_error_m")],
  idvar = c("case_id", "regime"),
  timevar = "policy",
  direction = "wide"
)
w <- w[order(w$case_id), , drop = FALSE]
if (nrow(w) != n_cases) stop("Paired case count mismatch")
strata <- split(seq_len(nrow(w)), w$regime)
set.seed(20261114L)

paired_boot <- function(candidate, variable) {
  x <- w[[paste0(variable, ".aligned_replay")]]
  y <- w[[paste0(variable, ".", candidate)]]
  if (anyNA(x) || anyNA(y)) stop("Missing paired outcome")
  diff <- y - x
  draws <- numeric(B)
  for (b in seq_len(B)) {
    idx <- unlist(lapply(strata, function(ids) {
      sample(ids, length(ids), replace = TRUE)
    }), use.names = FALSE)
    draws[[b]] <- mean(diff[idx])
  }
  if (variable == "strict_success") {
    better <- sum(x == 0 & y == 1)
    worse <- sum(x == 1 & y == 0)
  } else if (variable == "unsafe") {
    # Lower unsafe-event rate is better; invert the binary direction.
    better <- sum(x == 1 & y == 0)
    worse <- sum(x == 0 & y == 1)
  } else {
    # Continuous goal error has no binary discordant labels.
    better <- NA_integer_
    worse <- NA_integer_
  }
  n_discord <- better + worse
  p_exact <- if (variable == "strict_success" && n_discord > 0L) {
    binom.test(min(better, worse), n_discord, 0.5)$p.value
  } else NA_real_
  scale <- if (variable == "final_goal_error_m") 1 else 100
  unit <- if (variable == "final_goal_error_m") "meters" else "percentage_points"
  data.frame(
    comparator = candidate, outcome = variable, n_paired = length(diff),
    delta = scale * mean(diff),
    ci_low = scale * unname(quantile(draws, 0.025)),
    ci_high = scale * unname(quantile(draws, 0.975)),
    unit = unit, better_discordant = better,
    worse_discordant = worse, exact_p = p_exact
  )
}
paired <- do.call(rbind, lapply(policies[-1], function(p) {
  rbind(
    paired_boot(p, "strict_success"),
    paired_boot(p, "unsafe"),
    paired_boot(p, "final_goal_error_m")
  )
}))
write.csv(paired, file.path(report_dir, "paired_bootstrap.csv"),
          row.names = FALSE)

regime_data <- aggregate(
  cbind(strict_success, unsafe, damage_proxy, contact_episode, abstained) ~
    regime + policy, d, mean
)
counts <- aggregate(case_id ~ regime + policy, d, length)
names(counts)[names(counts) == "case_id"] <- "episodes"
regime_data <- merge(regime_data, counts, by = c("regime", "policy"))
write.csv(regime_data, file.path(report_dir, "regime_summary.csv"),
          row.names = FALSE)

# Measured impulses reinterpreted post-hoc; NOT new physics simulations.
sensitivity <- do.call(rbind, lapply(c(0.004, 0.006, 0.008), function(th) {
  tmp <- aggregate(
    d$peak_step_impulse_ns > th,
    by = list(policy = d$policy), FUN = mean
  )
  names(tmp)[[2]] <- "fraction_above"
  tmp$threshold_ns <- th
  tmp
}))
write.csv(sensitivity,
          file.path(report_dir, "impulse_sensitivity.csv"),
          row.names = FALSE)

plot_metric <- function(field, title, filename) {
  mat <- vapply(policies, function(policy) {
    x <- regime_data[regime_data$policy == policy, , drop = FALSE]
    100 * x[[field]][match(regimes, x$regime)]
  }, numeric(length(regimes)))
  rownames(mat) <- regimes
  png(file.path(report_dir, filename), width = 1800, height = 1050, res = 150)
  op <- par(mar = c(8, 5, 4, 2))
  barplot(t(mat), beside = TRUE, names.arg = regimes,
          col = c("#526EC6", "#31A68E", "#EFAE51", "#8F939B"),
          ylim = c(0, 100), las = 2, ylab = "Actual MuJoCo episode rate (%)",
          main = title, legend.text = policies,
          args.legend = list(x = "topright", bty = "n", cex = .72))
  par(op)
  dev.off()
}
plot_metric("strict_success", "Rokoko: strict safe success by scenario",
            "success_by_regime.png")
plot_metric("unsafe", "Rokoko: unsafe episode rate by scenario",
            "unsafe_by_regime.png")

main <- paired[paired$comparator == "contact_feedback" &
                 paired$outcome == "strict_success", ]
if (nrow(main) != 1L) stop("No primary paired result")

report <- c(
  "# Rokoko MotionBridge — large, actual MuJoCo physics campaign",
  "",
  paste("Frozen executed source SHA:", unique(sources)),
  paste("Actual independent world/scenario seeds:", n_cases),
  paste("Actual completed MuJoCo physics episodes:", n_runs),
  paste("Actual 2 ms physics solver steps:", format(n_steps, big.mark = ",", scientific = FALSE)),
  paste("R paired-bootstrap replicates (NOT physics episodes):", B),
  paste("Raw CSV shards / SHA256 matched:", length(paths)),
  "",
  "## Verified controller outcomes",
  ""
)
for (i in seq_len(nrow(summary))) {
  x <- summary[i, ]
  report <- c(report, sprintf(
    "%s: %d/%d strict safe (%.1f%%, Wilson 95%% %.1f–%.1f%%), %d unsafe, %d damaged, %d object-obstacle, %d pusher-obstacle episodes.",
    x$policy, x$strict_successes, x$cases,
    100 * x$success_rate, 100 * x$wilson_low, 100 * x$wilson_high,
    x$unsafe_cases, x$broken_cases,
    x$object_obstacle_cases, x$pusher_obstacle_cases
  ))
}
report <- c(report, "", sprintf(
  "Contact feedback minus aligned replay: %.2f percentage points (stratified paired bootstrap 95%% CI %.2f to %.2f pp); exact two-sided paired p=%s.",
  main$delta, main$ci_low, main$ci_high, format(main$exact_p, digits = 5)
), "", "## Boundaries", "",
  "- The four controllers are scripted, NOT trained reinforcement learning.",
  "- The inputs are invented glove-derived progress and synthetic noisy camera observations.",
  "- Object and pusher dynamics, forces, collisions, failure flags and dwell are actual MuJoCo calculations.",
  "- Strict analysis additionally penalizes pusher-only obstacle collisions.",
  "- Fragility impulse thresholds are deliberately toy physics, not hardware calibration.",
  "- Paired bootstrap samples scenario IDs in predeclared strata; draws are R resamples, not robot trials.",
  "- No claim of real Rokoko SDK, physical robot safety, NVIDIA GPU, Google DeepMind Playground or actual human intervention.",
  "- API/model calls: NONE; no new paid compute. All raw failures remain in the source-pinned CSVs.",
  "",
  "## Artifacts", "",
  "Raw campaign-shard CSVs plus exact data/source SHA256 manifests in results/.",
  "policy_summary.csv, paired_bootstrap.csv, regime_summary.csv,",
  "impulse_sensitivity.csv, success_by_regime.png, unsafe_by_regime.png.",
  ""
)
# Large campaign shows the generalization gap: do not hide it in averages.
report <- c(report, "", "## Shift robustness: object-centred feedback", "")
for (regime_name in regimes) {
  r <- regime_data[
    regime_data$regime == regime_name &
      regime_data$policy == "contact_feedback", , drop = FALSE
  ]
  if (nrow(r) != 1L) stop("Missing regime outcome")
  report <- c(report, sprintf(
    "%s: %d/%d strict successes (%.1f%%); %.1f%% unsafe episodes.",
    regime_name, round(r$strict_success * r$episodes),
    r$episodes, 100 * r$strict_success, 100 * r$unsafe
  ))
}
report <- c(report, "",
  "Each of five regimes is equally weighted by benchmark design.",
  "Strong nominal success must not disguise near-zero shifted-world robustness.",
  "The replay baseline is a single fixed demonstration, not an optimal policy.",
  "No comparison here demonstrates trained RL or real robotics generalization.",
  "Next: a learned CPU option-value baseline and pre-registered new OOD cases.", "")
writeLines(if (length(report) && tail(report, 1L) == "") head(report, -1L) else report,
           file.path(report_dir, "REPORT.md"), useBytes = TRUE)
cat(sprintf(
  "R_ANALYSIS_DONE actual_scenarios=%d physics_episodes=%d solver_steps=%d bootstrap=%d\n",
  n_cases, n_runs, n_steps, B))
print(summary[, c("policy", "cases", "strict_successes",
                  "unsafe_cases", "broken_cases", "mean_error_m")],
      row.names = FALSE)
print(main[, c("delta", "ci_low", "ci_high", "exact_p")])
