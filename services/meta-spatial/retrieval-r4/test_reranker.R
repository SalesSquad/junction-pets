#!/usr/bin/env Rscript
# Focused checks for numerical integrity, leakage, denominator and fail-closed policy.
script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_dir <- if (length(script_arg)) dirname(normalizePath(sub("^--file=", "", script_arg[1]))) else "."
source(file.path(script_dir, "train_reranker.R"))

checks <- 0L
check <- function(name, expression) {
  force(expression)
  checks <<- checks + 1L
  cat(sprintf("PASS %s\n", name))
}
must_fail <- function(expression, pattern) {
  message <- tryCatch({ force(expression); NULL }, error = function(error) conditionMessage(error))
  stopifnot(!is.null(message), grepl(pattern, message, fixed = TRUE))
}

fixture <- function() {
  rows <- list()
  for (partition in R4_SPLITS) for (q in seq_len(12)) for (candidate in seq_len(3)) {
    positive <- candidate == 2L
    family <- paste0(partition, "-f", ceiling(q / 2))
    rows[[length(rows) + 1L]] <- data.frame(
      split = partition, query_id = paste0(partition, "-q", q), query_family = family,
      candidate_id = if (positive) paste0(partition, "-q", q) else
        paste0(partition, "-negative-", q, "-", candidate),
      candidate_family = if (positive) family else paste0(partition, "-other-", q, "-", candidate),
      label = as.integer(positive), f_visual = c(0.8, 0.6, 0.4)[candidate],
      f_adapted = c(0.8, 0.6, 0.4)[candidate], f_text = if (positive) 0.9 else 0.1,
      f_reverse_rank = if (positive) 0.5 else 0.1, f_density = 0,
      f_gap = c(0.2, -0.2, -0.4)[candidate], baseline_rank = candidate,
      stringsAsFactors = FALSE)
  }
  do.call(rbind, rows)
}

data <- r4_validate_data(fixture())
train <- data[data$split == "train", , drop = FALSE]

check("train-only scaler and zero-variance handling", {
  scaler <- r4_scaler(train)
  changed <- data
  changed[changed$split != "train", R4_FEATURES] <- 1e6
  stopifnot(identical(scaler, r4_scaler(changed[changed$split == "train", ])),
            scaler$scale[5] == 1, scaler$center[5] == 0)
})

check("family/query weighting does not reward extra candidate rows", {
  weights <- r4_row_weights(train)
  family_mass <- tapply(weights, train$query_family, sum)
  query_mass <- tapply(weights, train$query_id, sum)
  stopifnot(max(family_mass) - min(family_mass) < 1e-12,
            max(query_mass) - min(query_mass) < 1e-12)
  pair <- r4_pairs(train, r4_transform(train, r4_scaler(train)))
  stopifnot(abs(sum(pair$weight) - 1) < 1e-12, pair$queries == 12L, pair$families == 6L)
})

check("analytic gradient matches finite differences", {
  difference <- matrix(c(-2, 1, 0.4, -0.1, 3, 1, -2, 4, 0.2, 0.6, -0.5, 2), ncol = 3)
  weight <- c(0.1, 0.2, 0.3, 0.4)
  beta <- c(0.2, -0.7, 0.4)
  epsilon <- 1e-6
  numeric_gradient <- vapply(seq_along(beta), function(i) {
    plus <- minus <- beta
    plus[i] <- plus[i] + epsilon
    minus[i] <- minus[i] - epsilon
    (r4_objective(plus, difference, weight, 0.1) -
       r4_objective(minus, difference, weight, 0.1)) / (2 * epsilon)
  }, numeric(1))
  stopifnot(max(abs(numeric_gradient - r4_gradient(beta, difference, weight, 0.1))) < 1e-7)
  stopifnot(is.finite(r4_objective(c(1e3, -1e3, 1e3), difference, weight, 0.1)))
})

fit <- r4_fit(data)
check("real parameter fit improves deliberately wrong baseline", {
  stopifnot(all(is.finite(fit$model$coefficients)), any(abs(fit$model$coefficients) > 1e-6),
            fit$report$metrics$dev$learned$recall_at_1 == 1,
            fit$report$metrics$dev$retained_candidate_r3_order$recall_at_1 == 0,
            identical(fit$model$feature_names, R4_FEATURES))
})

check("RRF may omit original top1 without dropping the query denominator", {
  changed <- data[!(data$split == "test" & data$query_id == "test-q1" &
                     data$baseline_rank == 1), , drop = FALSE]
  validated <- r4_validate_data(changed)
  stopifnot(identical(validated$baseline_rank, changed$baseline_rank),
            min(validated$baseline_rank[validated$split == "test" &
                                         validated$query_id == "test-q1"]) == 2)
  second <- r4_fit(changed)
  retained <- second$report$metrics$test$retained_candidate_r3_order
  stopifnot(identical(fit$model, second$model),
            retained$queries == 12L, retained$original_rank1_missing_queries == 1L,
            retained$original_rank1_retained_queries == 11L,
            abs(retained$recall_at_1 - 1 / 12) < 1e-12,
            second$report$metrics$test$learned$queries == 12L)
})

check("test labels cannot select model or acceptance policy", {
  changed <- data
  positives <- changed$split == "test" & changed$label == 1
  changed$candidate_id[positives] <- paste0("test-new-absent-", seq_len(sum(positives)))
  changed$candidate_family[positives] <- paste0("test-new-family-", seq_len(sum(positives)))
  changed$label[positives] <- 0
  second <- r4_fit(changed)
  stopifnot(identical(fit$model, second$model),
            second$report$metrics$test$learned$missing_positive_queries == 12L,
            second$report$metrics$test$learned$mrr == 0)
})

check("missing positives stay in recall denominator and deterministic ties", {
  test <- data[data$split == "test", ]
  positive <- test$query_id == "test-q1" & test$label == 1
  test$candidate_id[positive] <- "test-new-absent-q1"
  test$candidate_family[positive] <- "test-new-family-q1"
  test$label[positive] <- 0
  summaries <- r4_rank_queries(test, rep(0, nrow(test)))
  metrics <- r4_retrieval_metrics(summaries)
  stopifnot(metrics$queries == 12L, metrics$missing_positive_queries == 1L,
            abs(metrics$candidate_recall - 11 / 12) < 1e-12)
  q1 <- summaries[summaries$query_id == "test-q1", ]
  stopifnot(q1$candidate_id == sort(test$candidate_id[test$query_id == "test-q1"], method = "radix")[1])
})

check("small calibration abstains and full qualification always remains false", {
  stopifnot(!fit$model$policy$calibrated, is.null(fit$model$policy$threshold),
            !fit$model$qualification, !fit$model$action_authorized,
            fit$report$metrics$test$policy$accepted == 0L)
})

check("conditional family evidence counts clusters, not video-like duplicates", {
  n <- 1000L
  queries <- data.frame(query_id = paste0("q", seq_len(n)), query_family = paste0("f", seq_len(n)),
                        confidence = rep(1, n), exact_correct = rep(TRUE, n))
  policy <- r4_calibrate(queries, queries)
  stopifnot(policy$calibrated, !policy$qualification, !policy$conditional_query_error_certified)
  duplicates <- queries
  duplicates$query_family <- "one-physical-family"
  duplicate_policy <- r4_calibrate(queries, duplicates)
  stats <- r4_policy_statistics(duplicates, 1)
  stopifnot(!duplicate_policy$calibrated, stats$accepted_families == 1L,
            stats$accepted == 1000L, stats$conditional_accepted_family_any_error_upper > 0.9)
})

check("reject leakage, duplicate rows, nonfinite features and invalid supervision", {
  changed <- data
  changed$query_family[changed$split == "test"] <- "train-f1"
  must_fail(r4_validate_data(changed), "Family leakage")
  must_fail(r4_validate_data(rbind(data, data[1, ])), "Duplicate query/candidate")
  changed <- data
  changed$f_text[1] <- Inf
  must_fail(r4_validate_data(changed), "Nonfinite")
  changed <- data
  changed$label[1] <- 1
  must_fail(r4_validate_data(changed), "Label disagrees")
  changed <- data
  positives <- changed$split == "train" & changed$label == 1
  changed$candidate_id[positives] <- paste0("train-new-absent-", seq_len(sum(positives)))
  changed$candidate_family[positives] <- paste0("train-new-family-", seq_len(sum(positives)))
  changed$label[positives] <- 0
  must_fail(r4_fit(changed), "No trainable positive/negative")
})

check("manifest hash/admission and portable JSON round trip", {
  temporary <- tempfile("meta-r4-r-test-")
  dir.create(temporary)
  input <- file.path(temporary, "candidates.csv")
  manifest_path <- file.path(temporary, "data_manifest.json")
  model_path <- file.path(temporary, "model.json")
  write.csv(data, input, row.names = FALSE)
  manifest <- list(feature_names = R4_FEATURES, input_sha256 = r4_sha256(input),
                   admission = list(family_disjoint = TRUE, image_hash_disjoint = TRUE))
  r4_write_json(manifest, manifest_path)
  admission <- r4_validate_manifest(manifest_path, input)
  stopifnot(identical(admission$input_sha256, manifest$input_sha256))
  r4_write_json(fit$model, model_path)
  answer <- r4_python(paste(
    "import json,sys,math",
    "m=json.load(open(sys.argv[1]))",
    "assert m['qualification'] is False and m['policy']['threshold'] is None",
    "assert len(m['coefficients'])==6 and len(m['scaler']['center'])==6",
    "assert all(math.isfinite(x) for x in m['coefficients'])",
    "print('portable-json-ok')", sep = "\n"), model_path)
  stopifnot(identical(answer, "portable-json-ok"))
  manifest$admission$image_hash_disjoint <- FALSE
  r4_write_json(manifest, manifest_path)
  must_fail(r4_validate_manifest(manifest_path, input), "image-hash disjointness not admitted")
  manifest$admission$image_hash_disjoint <- TRUE
  manifest$input_sha256 <- paste(rep("0", 64), collapse = "")
  r4_write_json(manifest, manifest_path)
  must_fail(r4_validate_manifest(manifest_path, input), "candidate CSV hash mismatch")
  unlink(temporary, recursive = TRUE)
})

cat(sprintf("R4 focused checks: %d passed\n", checks))
