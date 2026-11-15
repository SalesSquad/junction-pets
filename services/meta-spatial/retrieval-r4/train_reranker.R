#!/usr/bin/env Rscript
# R4 research reranker. Base R owns the numerical fit; Python 3 validates JSON
# admission/provenance only. Historical test scores can never qualify runtime.

R4_FEATURES <- c("f_visual", "f_adapted", "f_text", "f_reverse_rank",
                 "f_density", "f_gap")
R4_SPLITS <- c("train", "dev", "cal", "test")
R4_REGULARIZATION <- c(0.01, 0.1, 1)

r4_abort <- function(message) stop(message, call. = FALSE)

r4_json_string <- function(value) {
  chars <- utf8ToInt(enc2utf8(value))
  escaped <- vapply(chars, function(ch) {
    if (ch == 34L) return("\\\"")
    if (ch == 92L) return("\\\\")
    if (ch < 32L) return(sprintf("\\u%04x", ch))
    intToUtf8(ch)
  }, character(1))
  paste0('"', paste0(escaped, collapse = ""), '"')
}

r4_json <- function(value) {
  if (is.null(value)) return("null")
  if (is.data.frame(value)) {
    return(r4_json(lapply(seq_len(nrow(value)), function(i) as.list(value[i, ]))))
  }
  if (is.list(value)) {
    keys <- names(value)
    if (!is.null(keys) && length(keys) > 0L && all(nzchar(keys))) {
      entries <- vapply(seq_along(value), function(i) {
        paste0(r4_json_string(keys[i]), ":", r4_json(value[[i]]))
      }, character(1))
      return(paste0("{", paste0(entries, collapse = ","), "}"))
    }
    return(paste0("[", paste0(vapply(value, r4_json, character(1)), collapse = ","), "]"))
  }
  if (length(value) != 1L) return(r4_json(unname(as.list(value))))
  if (is.na(value)) return("null")
  if (is.logical(value)) return(if (value) "true" else "false")
  if (is.numeric(value)) {
    if (!is.finite(value)) r4_abort("Nonfinite numeric value cannot be exported as JSON")
    return(sprintf("%.17g", value))
  }
  if (is.character(value)) return(r4_json_string(value))
  r4_abort("Unsupported JSON value")
}

r4_write_json <- function(value, path) {
  # Always use the same serializer so optional packages cannot change artifacts.
  writeLines(r4_json(value), path, useBytes = TRUE)
}

r4_python <- function(code, args = character()) {
  python <- Sys.which("python3")
  if (!nzchar(python)) r4_abort("Python 3 is required for input admission")
  result <- suppressWarnings(system2(python,
    c("-I", "-c", shQuote(code), vapply(args, shQuote, character(1))),
    stdout = TRUE, stderr = TRUE))
  status <- attr(result, "status")
  if (!is.null(status) && status != 0L) {
    r4_abort(paste("Python admission failed:", paste(result, collapse = "\n")))
  }
  result
}

r4_sha256 <- function(path) {
  code <- paste(
    "import hashlib,sys",
    "h=hashlib.sha256()",
    "with open(sys.argv[1], 'rb') as f:",
    "    for block in iter(lambda:f.read(1048576),b''):h.update(block)",
    "print(h.hexdigest())", sep = "\n")
  result <- r4_python(code, path)
  if (length(result) != 1L || !grepl("^[a-f0-9]{64}$", result)) {
    r4_abort("Invalid file hash result")
  }
  result
}

r4_validate_manifest <- function(path, input) {
  code <- paste(
    "import json,hashlib,sys",
    "def unique_pairs(pairs):",
    "    out={}",
    "    for k,v in pairs:",
    "        if k in out: raise ValueError('duplicate manifest key')",
    "        out[k]=v",
    "    return out",
    "def bad_constant(x): raise ValueError('nonfinite JSON constant')",
    "def require(ok,message):",
    "    if not ok: raise ValueError(message)",
    "raw=open(sys.argv[1],'rb').read()",
    "m=json.loads(raw,object_pairs_hook=unique_pairs,parse_constant=bad_constant)",
    "require(isinstance(m,dict), 'manifest must be an object')",
    "a=m.get('admission',{})",
    "require(a.get('family_disjoint') is True, 'family disjointness not admitted')",
    "require(a.get('image_hash_disjoint') is True, 'image-hash disjointness not admitted')",
    "require(m.get('feature_names')==sys.argv[3].split(','), 'feature order mismatch')",
    "h=hashlib.sha256()",
    "with open(sys.argv[2],'rb') as f:",
    "    for block in iter(lambda:f.read(1048576),b''):h.update(block)",
    "digest=h.hexdigest()",
    "require(m.get('input_sha256')==digest, 'candidate CSV hash mismatch')",
    "print(digest)",
    "print(hashlib.sha256(raw).hexdigest())", sep = "\n")
  result <- r4_python(code, c(path, input, paste(R4_FEATURES, collapse = ",")))
  if (length(result) != 2L || any(!grepl("^[a-f0-9]{64}$", result))) {
    r4_abort("Invalid manifest admission result")
  }
  list(input_sha256 = result[1], manifest_sha256 = result[2],
       family_disjoint = TRUE, image_hash_disjoint = TRUE,
       image_hash_verification = "source-builder admission, bound to exact CSV; images not re-read by R")
}

r4_query_keys <- function(data) paste(data$split, data$query_id, sep = "\037")

r4_validate_data <- function(data, require_all_splits = TRUE) {
  required <- c("split", "query_id", "query_family", "candidate_id", "candidate_family",
                "label", R4_FEATURES, "baseline_rank")
  if (!is.data.frame(data) || nrow(data) == 0L) r4_abort("Candidate data must be nonempty")
  if (anyDuplicated(names(data))) r4_abort("Duplicate column names")
  missing <- setdiff(required, names(data))
  if (length(missing)) r4_abort(paste("Missing columns:", paste(missing, collapse = ",")))
  for (name in c("split", "query_id", "query_family", "candidate_id", "candidate_family")) {
    data[[name]] <- as.character(data[[name]])
    if (anyNA(data[[name]]) || any(!nzchar(data[[name]])) ||
        any(grepl("[\r\n\t\037]", data[[name]]))) {
      r4_abort(paste("Invalid identifier column", name))
    }
  }
  if (any(!data$split %in% R4_SPLITS)) r4_abort("Unknown split")
  if (require_all_splits && !setequal(unique(data$split), R4_SPLITS)) {
    r4_abort("All train/dev/cal/test splits are required")
  }
  for (name in c("label", R4_FEATURES, "baseline_rank")) {
    values <- suppressWarnings(as.numeric(as.character(data[[name]])))
    if (anyNA(values) || any(!is.finite(values))) r4_abort(paste("Nonfinite or nonnumeric", name))
    data[[name]] <- values
  }
  if (any(!data$label %in% c(0, 1))) r4_abort("Labels must be binary")
  if (any(data$label != as.integer(data$query_id == data$candidate_id))) {
    r4_abort("Label disagrees with exact product identity")
  }
  if (any(data$baseline_rank < 1 | data$baseline_rank != floor(data$baseline_rank))) {
    r4_abort("Baseline ranks must be positive integers")
  }
  keys <- r4_query_keys(data)
  if (anyDuplicated(paste(keys, data$candidate_id, sep = "\037"))) {
    r4_abort("Duplicate query/candidate pair")
  }
  groups <- split(seq_len(nrow(data)), keys)
  for (ids in groups) {
    if (length(unique(data$query_family[ids])) != 1L) r4_abort("Query family changes within query")
    if (sum(data$label[ids]) > 1) r4_abort("Multiple exact positives within a query")
    if (length(ids) > 100L) r4_abort("Candidate bound exceeds contract top100")
    if (anyDuplicated(data$baseline_rank[ids])) r4_abort("Duplicate baseline rank within query")
  }
  families <- unique(rbind(
    data.frame(family = data$query_family, split = data$split),
    data.frame(family = data$candidate_family, split = data$split)))
  if (anyDuplicated(families$family)) r4_abort("Family leakage across splits")
  products <- unique(rbind(
    data.frame(product = data$query_id, split = data$split),
    data.frame(product = data$candidate_id, split = data$split)))
  if (anyDuplicated(products$product)) r4_abort("Product identifier leakage across splits")
  identity_families <- unique(rbind(
    data.frame(product = data$query_id, family = data$query_family),
    data.frame(product = data$candidate_id, family = data$candidate_family)))
  if (anyDuplicated(identity_families$product)) r4_abort("Product family identity is inconsistent")
  data
}

r4_row_weights <- function(data) {
  # Equal mass per family, then per query within family, then per candidate row.
  keys <- r4_query_keys(data)
  query_rows <- table(keys)
  unique_queries <- !duplicated(keys)
  family_queries <- table(data$query_family[unique_queries])
  weight <- 1 / (as.numeric(query_rows[keys]) *
                   as.numeric(family_queries[data$query_family]))
  weight / sum(weight)
}

r4_scaler <- function(train) {
  x <- as.matrix(train[, R4_FEATURES, drop = FALSE])
  weights <- r4_row_weights(train)
  center <- colSums(x * weights)
  centered <- sweep(x, 2L, center, "-")
  scale <- sqrt(colSums(centered^2 * weights))
  constant <- scale < 1e-12
  scale[constant] <- 1
  list(center = unname(center), scale = unname(scale),
       constant_features = R4_FEATURES[constant])
}

r4_transform <- function(data, scaler) {
  x <- as.matrix(data[, R4_FEATURES, drop = FALSE])
  result <- sweep(sweep(x, 2L, scaler$center, "-"), 2L, scaler$scale, "/")
  if (any(!is.finite(result))) r4_abort("Nonfinite standardized feature")
  result
}

r4_pairs <- function(train, x) {
  groups <- split(seq_len(nrow(train)), r4_query_keys(train))
  usable <- groups[vapply(groups, function(ids) sum(train$label[ids]) == 1L &&
                           length(ids) > 1L, logical(1))]
  if (!length(usable)) r4_abort("No trainable positive/negative query pairs")
  family <- vapply(usable, function(ids) train$query_family[ids[1]], character(1))
  family_queries <- table(family)
  differences <- vector("list", length(usable))
  weights <- vector("list", length(usable))
  for (i in seq_along(usable)) {
    ids <- usable[[i]]
    positive <- ids[train$label[ids] == 1]
    negative <- ids[train$label[ids] == 0]
    differences[[i]] <- matrix(x[positive, ], nrow = length(negative),
                              ncol = ncol(x), byrow = TRUE) - x[negative, , drop = FALSE]
    weights[[i]] <- rep(1 / (unname(family_queries[family[i]]) * length(negative)),
                        length(negative))
  }
  difference <- do.call(rbind, differences)
  weight <- unlist(weights, use.names = FALSE)
  weight <- weight / sum(weight)
  list(difference = difference, weight = weight, queries = length(usable),
       families = length(unique(family)), skipped_queries = length(groups) - length(usable),
       pairs = nrow(difference))
}

r4_objective <- function(beta, difference, weight, lambda) {
  score <- drop(difference %*% beta)
  # Stable log(1 + exp(-score)) without overflow or an arbitrary clipped loss.
  loss <- pmax(-score, 0) + log1p(exp(-abs(score)))
  sum(weight * loss) + 0.5 * lambda * sum(beta^2)
}

r4_gradient <- function(beta, difference, weight, lambda) {
  score <- drop(difference %*% beta)
  drop(crossprod(difference, -weight * plogis(-score))) + lambda * beta
}

r4_rank_queries <- function(data, score) {
  if (length(score) != nrow(data) || any(!is.finite(score))) r4_abort("Invalid rank scores")
  groups <- split(seq_len(nrow(data)), r4_query_keys(data))
  summaries <- lapply(groups, function(ids) {
    ranking <- ids[order(-score[ids], data$candidate_id[ids], method = "radix")]
    positive <- which(data$label[ranking] == 1)
    rank <- if (length(positive)) positive[1] else NA_integer_
    top <- ranking[1]
    gap <- if (length(ranking) >= 2L) score[top] - score[ranking[2]] else 0
    data.frame(split = data$split[top], query_id = data$query_id[top],
      query_family = data$query_family[top], candidate_id = data$candidate_id[top],
      exact_correct = data$label[top] == 1,
      family_correct = data$candidate_family[top] == data$query_family[top],
      positive_rank = rank, candidates = length(ids),
      top_score = score[top], gap = gap, confidence = score[top] + gap,
      stringsAsFactors = FALSE)
  })
  output <- do.call(rbind, summaries)
  rownames(output) <- NULL
  output
}

r4_retrieval_metrics <- function(queries) {
  n <- nrow(queries)
  positive <- !is.na(queries$positive_rank)
  ranks <- queries$positive_rank
  rank_mean <- function(k) sum(positive & ranks <= k, na.rm = TRUE) / n
  list(queries = n, families = length(unique(queries$query_family)),
       candidate_recall = mean(positive), missing_positive_queries = sum(!positive),
       recall_at_1 = rank_mean(1), recall_at_5 = rank_mean(5),
       recall_at_10 = rank_mean(10), recall_at_50 = rank_mean(50),
       recall_at_100 = rank_mean(100),
       mrr = sum(1 / ranks[positive]) / n,
       family_recall_at_1 = mean(queries$family_correct))
}

r4_cp_upper <- function(errors, total, alpha = 0.05) {
  if (total < 1L) return(NULL)
  if (errors == total) return(1)
  qbeta(1 - alpha, errors + 1, total - errors)
}

r4_policy_statistics <- function(queries, threshold, alpha = 0.05) {
  accepted <- if (is.null(threshold)) rep(FALSE, nrow(queries)) else queries$confidence >= threshold
  total <- sum(accepted)
  wrong <- sum(accepted & !queries$exact_correct)
  accepted_families <- unique(queries$query_family[accepted])
  error_families <- unique(queries$query_family[accepted & !queries$exact_correct])
  list(queries = nrow(queries), accepted = total, correct_accepted = total - wrong,
       wrong_accepted = wrong, coverage = total / nrow(queries),
       conditional_error = if (total) wrong / total else NULL,
       accepted_precision = if (total) 1 - wrong / total else NULL,
       query_binomial_upper95_descriptive = r4_cp_upper(wrong, total),
       query_binomial_assumption = "independent accepted queries; family correlation not covered",
       accepted_families = length(accepted_families),
       accepted_families_with_any_error = length(error_families),
       conditional_accepted_family_any_error_upper =
         r4_cp_upper(length(error_families), length(accepted_families), alpha),
       family_bound_alpha = alpha,
       family_bound_denominator = "accepted families, not all eligible families",
       conditional_query_error_certified = FALSE,
       physical_identity_verified = FALSE, action_authorized = FALSE)
}

r4_calibrate <- function(dev_queries, cal_queries) {
  # Fixed quantile locations use dev confidence only, before cal is examined.
  # The union correction accounts for selection among this finite threshold set.
  probabilities <- seq(0, 1, by = 0.05)
  thresholds <- unique(as.numeric(quantile(dev_queries$confidence, probabilities,
                                           names = FALSE, type = 1)))
  alpha <- 0.05 / length(thresholds)
  cells <- lapply(thresholds, function(threshold) {
    stats <- r4_policy_statistics(cal_queries, threshold, alpha)
    family_upper <- stats$conditional_accepted_family_any_error_upper
    eligible <- stats$accepted > 0L && !is.null(family_upper) &&
      family_upper <= 0.01 && stats$conditional_error <= 0.01
    list(threshold = threshold, eligible = eligible, statistics = stats)
  })
  eligible <- which(vapply(cells, function(cell) isTRUE(cell$eligible), logical(1)))
  selected <- NULL
  if (length(eligible)) {
    coverage <- vapply(cells[eligible], function(cell) cell$statistics$coverage, numeric(1))
    bound <- vapply(cells[eligible], function(cell)
      cell$statistics$conditional_accepted_family_any_error_upper, numeric(1))
    chosen <- eligible[order(-coverage, bound, thresholds[eligible], method = "radix")[1]]
    selected <- cells[[chosen]]
  }
  list(calibrated = !is.null(selected),
       threshold = if (is.null(selected)) NULL else selected$threshold,
       score_field = "top_score_plus_margin", conditional_risk_target = 0.01,
       coverage_target_strictly_above = 0.93,
       calibration_status = if (is.null(selected)) "insufficient_conditional_family_evidence" else
         "finite_grid_calibration_selected_research_only",
       calibration_candidate_statistics = cells,
       calibration_grid = "dev confidence quantiles at fixed 0.05 increments; no cal/test thresholds",
       calibration_family_alpha = alpha,
       calibration_selection_correction = "Bonferroni across fixed dev-derived threshold grid",
       family_bound_assumption = "independent exchangeable source families; correlations not established",
       conditional_query_error_certified = FALSE,
       qualification = FALSE, action_authorized = FALSE)
}

r4_fit <- function(data, maxit = 250L) {
  data <- r4_validate_data(data)
  train <- data[data$split == "train", , drop = FALSE]
  dev <- data[data$split == "dev", , drop = FALSE]
  scaler <- r4_scaler(train)
  pair <- r4_pairs(train, r4_transform(train, scaler))
  dev_x <- r4_transform(dev, scaler)
  candidates <- lapply(R4_REGULARIZATION, function(lambda) {
    fit <- optim(rep(0, length(R4_FEATURES)), r4_objective, gr = r4_gradient,
      difference = pair$difference, weight = pair$weight, lambda = lambda,
      method = "BFGS", control = list(maxit = maxit, reltol = 1e-10))
    if (fit$convergence != 0L || any(!is.finite(fit$par)) || !is.finite(fit$value)) {
      r4_abort(paste("Numerical optimizer failed for lambda", lambda))
    }
    score <- drop(dev_x %*% fit$par)
    metrics <- r4_retrieval_metrics(r4_rank_queries(dev, score))
    list(lambda = lambda, coefficients = unname(fit$par),
         objective = fit$value, convergence = fit$convergence,
         gradient_max_abs = max(abs(r4_gradient(fit$par, pair$difference, pair$weight, lambda))),
         evaluations = as.list(fit$counts), dev = metrics)
  })
  recalls <- vapply(candidates, function(item) item$dev$recall_at_1, numeric(1))
  mrr <- vapply(candidates, function(item) item$dev$mrr, numeric(1))
  # Predeclared grid order (0.01, 0.1, 1) breaks exact ties, never test scores.
  chosen <- order(-recalls, -mrr, seq_along(candidates), method = "radix")[1]
  selected <- candidates[[chosen]]
  score <- drop(r4_transform(data, scaler) %*% selected$coefficients)
  queries <- r4_rank_queries(data, score)
  baseline_queries <- r4_rank_queries(data, -data$baseline_rank)
  by_split <- split(queries, factor(queries$split, levels = R4_SPLITS))
  baseline_split <- split(baseline_queries, factor(baseline_queries$split, levels = R4_SPLITS))
  policy <- r4_calibrate(by_split$dev, by_split$cal)
  metrics <- lapply(R4_SPLITS, function(partition) {
    retained_baseline <- r4_retrieval_metrics(baseline_split[[partition]])
    retained_baseline$original_rank1_retained_queries <-
      sum(baseline_split[[partition]]$top_score == -1)
    retained_baseline$original_rank1_missing_queries <-
      sum(baseline_split[[partition]]$top_score != -1)
    retained_baseline$scope <-
      "R3 ordering restricted to retained candidates; full-gallery original baseline is in data manifest"
    list(split = partition, learned = r4_retrieval_metrics(by_split[[partition]]),
         retained_candidate_r3_order = retained_baseline,
         policy = r4_policy_statistics(by_split[[partition]], policy$threshold))
  })
  names(metrics) <- R4_SPLITS
  model <- list(schema_version = 1L, kind = "ridge_pairwise_logistic",
       feature_names = R4_FEATURES, scaler = scaler,
       coefficients = selected$coefficients, intercept = 0,
       regularization = selected$lambda,
       rank_score_is_probability = FALSE, policy = policy,
       action_authorized = FALSE, physical_identity_verified = FALSE,
       qualification = FALSE, qualification_reason = "historical_test_inspected_not_fresh_qualification")
  predictions <- data.frame(split = data$split, query_id = data$query_id,
                            candidate_id = data$candidate_id, rank_score = score,
                            stringsAsFactors = FALSE)
  report <- list(schema_version = 1L, work_id = "META-LENS-R4-COVERAGE93-20261114",
    status = "trained_research_only", feature_names = R4_FEATURES,
    training = list(rows = nrow(train), queries = length(unique(train$query_id)),
      families = length(unique(train$query_family)), trainable_queries = pair$queries,
      trainable_families = pair$families, skipped_untrainable_queries = pair$skipped_queries,
      pairs = pair$pairs, weighting = "equal family, then query, then negative within query",
      scaler_fit = "all training candidates only; family/query/row balanced",
      scaler_constant_features = scaler$constant_features,
      objective = "weighted logistic loss of positive-minus-negative score plus ridge",
      intercept = "zero: pairwise ranking cannot identify an intercept",
      fixed_regularization_grid = R4_REGULARIZATION, candidates = candidates,
      selected_index = chosen, selected_regularization = selected$lambda,
      selection = "dev exact recall@1, then MRR, then fixed grid order"),
    metrics = metrics, policy = policy,
    gate = list(status = "FAIL", qualification = FALSE,
      reason = "historical_test_inspected_not_fresh_qualification",
      coverage_target = ">0.93", conditional_query_error_target = "<=0.01",
      conditional_query_error_certified = FALSE,
      absent_catalog_qualification = FALSE, physical_identity_verified = FALSE),
    protocol = list(candidate_stats = "unlabeled transductive within-split catalog statistics",
      test_use = "historical diagnosis only; not model/threshold selection",
      unknown_objects = "missing positive within candidate set reported; not a real absent-catalog trial",
      physical_identity_verified = FALSE, action_authorized = FALSE))
  list(model = model, predictions = predictions, query_metrics = queries, report = report)
}

r4_parse_args <- function(args) {
  allowed <- c("--input", "--output", "--manifest", "--source-commit", "--maxit")
  if (length(args) %% 2L != 0L) r4_abort("Arguments must be --name value pairs")
  result <- list()
  if (length(args)) for (i in seq(1L, length(args), by = 2L)) {
    key <- args[i]
    if (!key %in% allowed || !is.null(result[[key]])) r4_abort(paste("Invalid or duplicate argument", key))
    result[[key]] <- args[i + 1L]
  }
  for (key in c("--input", "--output", "--manifest")) {
    if (is.null(result[[key]]) || !nzchar(result[[key]])) r4_abort(paste("Required", key))
  }
  if (!is.null(result[["--source-commit"]]) &&
      !grepl("^[a-f0-9]{40}$", result[["--source-commit"]])) r4_abort("Invalid source commit")
  result
}

r4_main <- function(args = commandArgs(trailingOnly = TRUE)) {
  config <- r4_parse_args(args)
  output <- config[["--output"]]
  artifacts <- c("model.rds", "model.json", "predictions.csv", "query_metrics.csv", "report.json")
  if (any(file.exists(file.path(output, c(artifacts, "failure.json"))))) {
    r4_abort("Refusing to overwrite existing R4 evidence")
  }
  if (!dir.exists(output) && !dir.create(output, recursive = TRUE)) r4_abort("Cannot create output directory")
  started <- proc.time()[["elapsed"]]
  result <- tryCatch({
    provenance <- r4_validate_manifest(config[["--manifest"]], config[["--input"]])
    script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
    script_path <- if (length(script_arg) == 1L) sub("^--file=", "", script_arg) else NULL
    script_hash_before <- if (is.null(script_path)) NULL else r4_sha256(script_path)
    data <- read.csv(config[["--input"]], stringsAsFactors = FALSE, check.names = FALSE,
                     colClasses = "character", na.strings = character())
    maxit <- if (is.null(config[["--maxit"]])) 250L else suppressWarnings(as.integer(config[["--maxit"]]))
    if (is.na(maxit) || maxit < 1L || maxit > 1000L) r4_abort("Invalid maxit")
    fit <- r4_fit(data, maxit = maxit)
    # Bind both pre/post bytes. A changed input during a run is an invalid run.
    if (r4_sha256(config[["--input"]]) != provenance$input_sha256 ||
        r4_sha256(config[["--manifest"]]) != provenance$manifest_sha256) {
      r4_abort("Input or manifest changed during training")
    }
    provenance$source_commit <- config[["--source-commit"]]
    if (!is.null(script_path)) {
      script_hash_after <- r4_sha256(script_path)
      if (script_hash_before != script_hash_after) r4_abort("Training script changed during execution")
      provenance$training_script_sha256 <- script_hash_before
    }
    fit$model$provenance <- provenance
    fit$report$provenance <- provenance
    fit$report$execution <- list(R_version = R.version.string, platform = R.version$platform,
      elapsed_seconds = proc.time()[["elapsed"]] - started,
      fit_engine = "base R stats::optim BFGS", randomness = "none",
      provider_inference_calls = 0L, qualification = FALSE)
    saveRDS(fit$model, file.path(output, "model.rds"), version = 3)
    r4_write_json(fit$model, file.path(output, "model.json"))
    write.csv(fit$predictions, file.path(output, "predictions.csv"), row.names = FALSE, na = "")
    write.csv(fit$query_metrics, file.path(output, "query_metrics.csv"), row.names = FALSE, na = "")
    fit$report$artifacts <- lapply(artifacts[artifacts != "report.json"], function(name)
      list(path = name, sha256 = r4_sha256(file.path(output, name))))
    r4_write_json(fit$report, file.path(output, "report.json"))
    fit
  }, error = function(error) {
    failure <- list(schema_version = 1L, status = "FAILED", error = conditionMessage(error),
                    qualification = FALSE, action_authorized = FALSE)
    r4_write_json(failure, file.path(output, "failure.json"))
    stop(error)
  })
  cat("R4 trained; research-only qualification=FALSE\n")
  cat(sprintf("lambda=%g test_recall_at_1=%.6f candidate_recall=%.6f policy_calibrated=%s\n",
    result$model$regularization, result$report$metrics$test$learned$recall_at_1,
    result$report$metrics$test$learned$candidate_recall, result$model$policy$calibrated))
  invisible(result)
}

if (sys.nframe() == 0L) r4_main()
