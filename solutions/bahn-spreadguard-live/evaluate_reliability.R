#!/usr/bin/env Rscript
# Paired world/seed bootstrap. Orders within a world are never resampled as IID.
# Rscript evaluate_reliability.R --input worlds.csv --output comparison.json \
#   --baseline admission --candidate reliability
# Required: seed_group,policy,won_orders,on_time_orders,margin_cents.
# Optional partition/split distinguishes development from untouched blind worlds.

fail <- function(...) stop(..., call. = FALSE)
as_array <- function(x) structure(as.list(unname(x)), class = "json_array")
json_string <- function(x) {
  encoded <- vapply(utf8ToInt(enc2utf8(x)), function(k) {
    if (k == 34L) return('\\"')
    if (k == 92L) return("\\\\")
    if (k < 32L) return(sprintf("\\u%04x", k))
    intToUtf8(k)
  }, character(1))
  paste0('"', paste0(encoded, collapse = ""), '"')
}
json_encode <- function(x) {
  if (is.null(x)) return("null")
  if (inherits(x, "json_array")) return(paste0("[", paste(vapply(x, json_encode, character(1)), collapse = ","), "]"))
  if (is.list(x)) {
    if (is.null(names(x))) return(json_encode(as_array(x)))
    if (any(!nzchar(names(x))) || anyDuplicated(names(x))) fail("Invalid JSON object keys")
    return(paste0("{", paste(vapply(seq_along(x), function(i) paste0(json_string(names(x)[i]), ":", json_encode(x[[i]])), character(1)), collapse = ","), "}"))
  }
  if (length(x) != 1L) return(json_encode(as_array(x)))
  if (is.na(x)) return("null")
  if (is.logical(x)) return(if (x) "true" else "false")
  if (is.numeric(x)) return(if (is.finite(x)) sprintf("%.17g", x) else "null")
  json_string(as.character(x))
}
write_json <- function(value, path) {
  if (!dir.exists(dirname(path))) fail("Output directory does not exist")
  temporary <- tempfile("paired-reliability-", tmpdir = dirname(path))
  on.exit(unlink(temporary), add = TRUE)
  writeLines(json_encode(value), temporary, useBytes = TRUE)
  if (!file.rename(temporary, path)) fail("Could not atomically publish output")
}
parse_args <- function(args) {
  options <- list()
  allowed <- c("input", "output", "baseline", "candidate", "draws", "seed", "source-sha")
  i <- 1L
  while (i <= length(args)) {
    key <- args[[i]]
    if (key %in% c("--help", "--self-check")) {
      options[[substring(key, 3L)]] <- TRUE
      i <- i + 1L
    } else {
      if (!startsWith(key, "--") || !(substring(key, 3L) %in% allowed)) fail("Unknown argument: ", key)
      if (i == length(args) || startsWith(args[[i + 1L]], "--")) fail("Missing value for ", key)
      name <- substring(key, 3L)
      if (!is.null(options[[name]])) fail("Duplicate argument: ", key)
      options[[name]] <- args[[i + 1L]]
      i <- i + 2L
    }
  }
  options
}

partition_values <- function(data) {
  fields <- intersect(c("partition", "split"), names(data))
  normalize <- function(x) {
    x <- tolower(trimws(as.character(x)))
    x[x %in% c("dev", "train", "training")] <- "development"
    x[x %in% c("test", "holdout", "heldout")] <- "blind"
    if (any(is.na(x) | !(x %in% c("development", "blind")))) fail("Partitions must be development or blind")
    x
  }
  if (!length(fields)) return(rep("development", nrow(data)))
  result <- normalize(data[[fields[[1L]]]])
  if (length(fields) > 1L && !identical(result, normalize(data[[fields[[2L]]]]))) fail("partition and split disagree")
  result
}

validate_worlds <- function(data) {
  required <- c("seed_group", "policy", "won_orders", "on_time_orders", "margin_cents")
  if (!all(required %in% names(data))) fail("Missing required world-result columns")
  if (!nrow(data) || anyDuplicated(names(data))) fail("CSV is empty or has duplicate column names")
  for (name in c("seed_group", "policy")) {
    data[[name]] <- trimws(as.character(data[[name]]))
    if (any(is.na(data[[name]]) | !nzchar(data[[name]]))) fail("Missing ", name)
  }
  for (name in c("won_orders", "on_time_orders", "margin_cents")) {
    data[[name]] <- suppressWarnings(as.numeric(as.character(data[[name]])))
    if (any(!is.finite(data[[name]]) | data[[name]] != floor(data[[name]]) | abs(data[[name]]) >= 2^53)) fail(name, " must contain exactly representable integer counts/cents")
  }
  if (any(data$won_orders < 0 | data$on_time_orders < 0 | data$on_time_orders > data$won_orders)) fail("Invalid order counts")
  data$.partition <- partition_values(data)
  if (anyDuplicated(data[c("seed_group", "policy")])) fail("Duplicate policy result for a seed_group; do not count worlds twice")
  if (any(vapply(split(data$.partition, data$seed_group), function(x) length(unique(x)) > 1L, logical(1)))) fail("A seed_group occurs in multiple partitions")
  if ("world_id" %in% names(data)) {
    if (any(is.na(data$world_id) | !nzchar(trimws(as.character(data$world_id))))) fail("Missing world_id")
    if (anyDuplicated(data$world_id)) fail("A world_id is reused as independent evidence")
  }
  data
}

ratio <- function(numerator, denominator) if (denominator > 0) numerator / denominator else NA_real_

policy_summary <- function(rows) {
  share <- ifelse(rows$won_orders > 0, rows$on_time_orders / rows$won_orders, NA_real_)
  valid <- is.finite(share)
  qualifying <- rows$won_orders > 0 & rows$on_time_orders >= 0.9 * rows$won_orders
  list(world_count = nrow(rows), won_orders = sum(rows$won_orders), on_time_orders = sum(rows$on_time_orders),
       late_orders = sum(rows$won_orders - rows$on_time_orders),
       aggregate_on_time_share = ratio(sum(rows$on_time_orders), sum(rows$won_orders)),
       equal_world_mean_on_time_share = if (any(valid)) mean(share[valid]) else NA_real_,
       worst_world_on_time_share = if (any(valid)) min(share[valid]) else NA_real_,
       zero_won_world_count = sum(!valid), qualifying_world_count = sum(qualifying),
       all_observed_worlds_qualified = all(qualifying),
       observed_worlds_at_least_98_percent = sum(valid & share >= 0.98),
       observed_worlds_at_least_99_percent = sum(valid & share >= 0.99),
       margin_cents = sum(rows$margin_cents), mean_world_margin_cents = mean(rows$margin_cents))
}

paired_statistics <- function(baseline, candidate, indices) {
  b <- baseline[indices, , drop = FALSE]
  cand <- candidate[indices, , drop = FALSE]
  b_won <- sum(b$won_orders)
  c_won <- sum(cand$won_orders)
  b_share <- ratio(sum(b$on_time_orders), b_won)
  c_share <- ratio(sum(cand$on_time_orders), c_won)
  c(mean_world_margin_delta_cents = mean(cand$margin_cents - b$margin_cents),
    total_margin_delta_cents = sum(cand$margin_cents - b$margin_cents),
    aggregate_on_time_share_delta = c_share - b_share,
    candidate_aggregate_on_time_share = c_share,
    baseline_aggregate_on_time_share = b_share,
    won_orders_delta = c_won - b_won,
    won_orders_relative_change = if (b_won > 0) c_won / b_won - 1 else NA_real_)
}

paired_comparison <- function(data, baseline_name, candidate_name, draws = 20000L, seed = 20261115L) {
  if (identical(baseline_name, candidate_name)) fail("Baseline and candidate must differ")
  data <- validate_worlds(data)
  chosen <- data[data$policy %in% c(baseline_name, candidate_name), , drop = FALSE]
  if (!all(c(baseline_name, candidate_name) %in% chosen$policy)) fail("Both requested policies need results")
  reports <- list()
  partitions <- intersect(c("development", "blind"), unique(chosen$.partition))
  for (partition_index in seq_along(partitions)) {
    partition <- partitions[[partition_index]]
    rows <- chosen[chosen$.partition == partition, , drop = FALSE]
    baseline <- rows[rows$policy == baseline_name, , drop = FALSE]
    candidate <- rows[rows$policy == candidate_name, , drop = FALSE]
    if (!setequal(baseline$seed_group, candidate$seed_group)) {
      fail("Unpaired seed groups in ", partition, "; obtain the missing counterpart rather than silently dropping it")
    }
    groups <- sort(baseline$seed_group)
    if (!length(groups)) fail("Empty paired partition")
    baseline <- baseline[match(groups, baseline$seed_group), , drop = FALSE]
    candidate <- candidate[match(groups, candidate$seed_group), , drop = FALSE]
    point <- paired_statistics(baseline, candidate, seq_along(groups))
    intervals <- NULL
    fraction_positive <- NA_real_
    lower_service <- NA_real_
    bootstrap_seed <- as.integer((as.double(seed) + partition_index - 1) %% .Machine$integer.max)
    if (length(groups) >= 2L) {
      set.seed(bootstrap_seed)
      simulations <- vapply(seq_len(draws), function(i) {
        sampled <- sample.int(length(groups), length(groups), replace = TRUE)
        paired_statistics(baseline, candidate, sampled)
      }, numeric(length(point)))
      rownames(simulations) <- names(point)
      intervals <- lapply(seq_along(point), function(j) {
        values <- simulations[j, ]
        finite <- is.finite(values)
        bounds <- if (any(finite)) quantile(values[finite], probs = c(0.025, 0.975), names = FALSE, type = 7) else c(NA_real_, NA_real_)
        list(metric = names(point)[[j]], estimate = unname(point[[j]]), lower_95 = bounds[[1L]], upper_95 = bounds[[2L]],
             finite_draw_count = sum(finite), undefined_draw_count = sum(!finite))
      })
      fraction_positive <- mean(simulations["mean_world_margin_delta_cents", ] > 0)
      service_draws <- simulations["candidate_aggregate_on_time_share", ]
      if (any(is.finite(service_draws))) lower_service <- unname(quantile(service_draws[is.finite(service_draws)], 0.05, type = 7))
    }
    pairs <- lapply(seq_along(groups), function(i) {
      list(seed_group = groups[[i]], baseline_world_id = if ("world_id" %in% names(baseline)) as.character(baseline$world_id[[i]]) else NULL,
           candidate_world_id = if ("world_id" %in% names(candidate)) as.character(candidate$world_id[[i]]) else NULL,
           baseline_won_orders = baseline$won_orders[[i]], candidate_won_orders = candidate$won_orders[[i]],
           baseline_on_time_share = ratio(baseline$on_time_orders[[i]], baseline$won_orders[[i]]),
           candidate_on_time_share = ratio(candidate$on_time_orders[[i]], candidate$won_orders[[i]]),
           baseline_margin_cents = baseline$margin_cents[[i]], candidate_margin_cents = candidate$margin_cents[[i]],
           margin_delta_cents = candidate$margin_cents[[i]] - baseline$margin_cents[[i]])
    })
    reports[[partition]] <- list(partition = partition, seed_groups = as_array(groups), pair_count = length(groups),
                                 baseline = policy_summary(baseline), candidate = policy_summary(candidate),
                                 paired_point_estimates = as.list(point), pairs = pairs,
                                 bootstrap = list(unit = "paired_seed_group", draws = if (length(groups) >= 2L) draws else 0L,
                                                  seed = bootstrap_seed, interval = "percentile_95_percent", intervals = intervals,
                                                  candidate_service_one_sided_95_lower = lower_service,
                                                  fraction_positive_margin_delta = fraction_positive,
                                                  fraction_is_posterior_probability = FALSE,
                                                  small_sample_warning = if (length(groups) < 5L) "Fewer than five paired seeds; uncertainty estimates are exploratory." else NULL,
                                                  one_pair_note = if (length(groups) == 1L) "One pair cannot estimate between-world uncertainty; intervals suppressed." else NULL))
  }
  list(schemaVersion = 1L, comparisonType = "paired_official_world_results", baseline_policy = baseline_name,
       candidate_policy = candidate_name, partitions = reports,
       omitted_policies = as_array(setdiff(unique(data$policy), c(baseline_name, candidate_name))),
       missing_partition_assumed_development = !any(c("partition", "split") %in% names(data)),
       limitations = as_array(c(
         "The caller must bind each row to a completed official world and the exact policy source; CSV content alone cannot verify origin.",
         "Development and blind partitions are reported separately and never pooled for promotion.",
         "Bootstrap pairs whole seed groups, retaining dependence among orders and correlation between policies.",
         "Intervals describe resampling of the observed worlds, not a guarantee for the secret final world or unseen regimes.",
         "Worst observed service is a descriptive minimum; it is not a confidence bound for unseen worlds.",
         "A high delivery share with reduced order volume can lower gross margin; all three quantities are reported.",
         "A declared blind partition is only blind if it was not used in development or model selection."
       )), automatic_policy_promotion = FALSE)
}

self_check <- function() {
  data <- data.frame(seed_group = rep(c("a", "b", "c"), 2), policy = rep(c("base", "new"), each = 3),
                     won_orders = 25, on_time_orders = c(24, 24, 24, 25, 25, 25),
                     margin_cents = c(1000, 2000, 3000, 1100, 2100, 3100))
  result <- paired_comparison(data, "base", "new", draws = 2000L)
  dev <- result$partitions$development
  stopifnot(dev$paired_point_estimates$mean_world_margin_delta_cents == 100,
            abs(dev$paired_point_estimates$aggregate_on_time_share_delta - 0.04) < 1e-12,
            dev$candidate$aggregate_on_time_share == 1,
            dev$bootstrap$intervals[[1L]]$lower_95 == 100,
            dev$bootstrap$intervals[[1L]]$upper_95 == 100,
            identical(result, paired_comparison(data[nrow(data):1L, ], "base", "new", draws = 2000L)))
  stopifnot(inherits(tryCatch(paired_comparison(data[-1L, ], "base", "new"), error = identity), "error"))
  stopifnot(inherits(tryCatch(validate_worlds(rbind(data, data[1L, ])), error = identity), "error"))
  leaky <- data
  leaky$partition <- c(rep("development", 3), rep("blind", 3))
  stopifnot(inherits(tryCatch(validate_worlds(leaky), error = identity), "error"))
  one <- paired_comparison(data[data$seed_group == "a", ], "base", "new")
  stopifnot(is.null(one$partitions$development$bootstrap$intervals))
  zero <- data[1L, ]
  zero$won_orders <- zero$on_time_orders <- 0
  stopifnot(!policy_summary(zero)$all_observed_worlds_qualified,
            is.na(policy_summary(zero)$aggregate_on_time_share))
  cat(json_encode(list(status = "pass", kind = "synthetic_numerical_self_check",
                       checks = as_array(c("known_paired_effect", "whole_seed_resampling", "row_order_invariance",
                                           "unpaired_rejection", "duplicate_rejection", "split_leak_rejection",
                                           "single_pair_intervals_suppressed", "zero_order_not_qualified")))), "\n")
}

main <- function() {
  options <- parse_args(commandArgs(trailingOnly = TRUE))
  if (isTRUE(options$help)) {
    cat("Usage: Rscript evaluate_reliability.R --input worlds.csv --output comparison.json --baseline NAME --candidate NAME\n",
        "  [--draws 20000] [--seed 20261115] [--source-sha FULL_SHA]\n",
        "  Rscript evaluate_reliability.R --self-check\n", sep = "")
    return(invisible(NULL))
  }
  if (isTRUE(options[["self-check"]])) return(self_check())
  for (name in c("input", "output", "baseline", "candidate")) if (is.null(options[[name]])) fail("Missing --", name)
  if (!is.null(options[["source-sha"]])) {
    options[["source-sha"]] <- tolower(options[["source-sha"]])
    if (!grepl("^([0-9a-f]{40}|[0-9a-f]{64})$", options[["source-sha"]])) fail("source-sha must be a full hexadecimal source commit SHA")
  }
  if (identical(normalizePath(options$input, mustWork = FALSE), normalizePath(options$output, mustWork = FALSE))) fail("Input and output must differ")
  read_integer <- function(name, fallback, minimum, maximum) {
    value <- if (is.null(options[[name]])) fallback else suppressWarnings(as.numeric(options[[name]]))
    if (length(value) != 1L || !is.finite(value) || value != floor(value) || value < minimum || value > maximum) fail("Invalid --", name)
    as.integer(value)
  }
  draws <- read_integer("draws", 20000L, 1000L, 1000000L)
  seed <- read_integer("seed", 20261115L, 0L, .Machine$integer.max)
  digest <- unname(tools::md5sum(options$input))
  data <- read.csv(options$input, stringsAsFactors = FALSE, check.names = FALSE)
  if (!identical(digest, unname(tools::md5sum(options$input)))) fail("Input changed while being read")
  result <- paired_comparison(data, options$baseline, options$candidate, draws, seed)
  result$provenance <- list(input_md5 = digest, source_sha = options[["source-sha"]], r_version = R.version.string,
                            supplied_source_shas = if ("source_sha" %in% names(data)) as_array(sort(unique(as.character(data$source_sha)))) else NULL)
  write_json(result, options$output)
  cat(json_encode(list(status = "comparison_written", output = options$output,
                       partitions = as_array(names(result$partitions)), automatic_policy_promotion = FALSE)), "\n")
}

if (sys.nframe() == 0L) tryCatch(main(), error = function(e) { message("ERROR: ", conditionMessage(e)); quit(status = 1L) })
