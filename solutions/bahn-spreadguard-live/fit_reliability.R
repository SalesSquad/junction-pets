#!/usr/bin/env Rscript
# Train P(late) from decision-time features and official, completed-world labels.
# Base R only. Example:
# Rscript fit_reliability.R --input orders.csv --output model.json \
#   --source-sha <full-source-sha>
# The output is a research candidate, never automatic authority to deploy it.

DEFAULT_FEATURES <- c(
  "slack_hours", "drive_hours", "ready_delay_hours", "eligible_supply",
  "backlog", "pending_quotes", "legs", "private", "premium", "manual",
  "low_charge_ev", "kind_next_day", "kind_3days", "weekday", "hour",
  "unbooked_age_hours"
)

fail <- function(...) stop(..., call. = FALSE)
as_array <- function(x) structure(as.list(unname(x)), class = "json_array")

json_string <- function(x) {
  chars <- utf8ToInt(enc2utf8(x))
  encoded <- vapply(chars, function(k) {
    if (k == 34L) return('\\"')
    if (k == 92L) return("\\\\")
    if (k < 32L) return(sprintf("\\u%04x", k))
    intToUtf8(k)
  }, character(1))
  paste0('"', paste0(encoded, collapse = ""), '"')
}

json_encode <- function(x) {
  if (is.null(x)) return("null")
  if (inherits(x, "json_array")) {
    return(paste0("[", paste(vapply(x, json_encode, character(1)), collapse = ","), "]"))
  }
  if (is.list(x)) {
    if (is.null(names(x))) return(json_encode(as_array(x)))
    if (any(!nzchar(names(x))) || anyDuplicated(names(x))) fail("Invalid JSON object keys")
    parts <- vapply(seq_along(x), function(i) {
      paste0(json_string(names(x)[i]), ":", json_encode(x[[i]]))
    }, character(1))
    return(paste0("{", paste(parts, collapse = ","), "}"))
  }
  if (length(x) != 1L) return(json_encode(as_array(x)))
  if (is.na(x)) return("null")
  if (is.logical(x)) return(if (x) "true" else "false")
  if (is.numeric(x)) return(if (is.finite(x)) sprintf("%.17g", x) else "null")
  json_string(as.character(x))
}

write_json <- function(value, path) {
  directory <- dirname(path)
  if (!dir.exists(directory)) fail("Output directory does not exist: ", directory)
  temporary <- tempfile("reliability-", tmpdir = directory)
  on.exit(unlink(temporary), add = TRUE)
  writeLines(json_encode(value), temporary, useBytes = TRUE)
  if (!file.rename(temporary, path)) fail("Could not atomically publish output: ", path)
}

parse_args <- function(args) {
  options <- list()
  allowed <- c("input", "output", "source-sha", "features", "lambda-grid", "seed")
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

numeric_column <- function(x, name) {
  value <- suppressWarnings(as.numeric(as.character(x)))
  if (any(!is.finite(value))) fail("Column ", name, " must contain finite numbers without missing values")
  value
}

partition_values <- function(data) {
  candidates <- intersect(c("partition", "split"), names(data))
  normalize <- function(x) {
    x <- tolower(trimws(as.character(x)))
    x[x %in% c("dev", "train", "training")] <- "development"
    x[x %in% c("test", "holdout", "heldout")] <- "blind"
    if (any(is.na(x) | !(x %in% c("development", "blind")))) fail("Partitions must be development or blind")
    x
  }
  if (!length(candidates)) return(rep("development", nrow(data)))
  result <- normalize(data[[candidates[[1L]]]])
  if (length(candidates) == 2L && !identical(result, normalize(data[[candidates[[2L]]]]))) {
    fail("partition and split columns disagree")
  }
  result
}

validate_data <- function(data, features) {
  needed <- c("late", "seed_group", "world_id", features)
  missing <- setdiff(needed, names(data))
  if (length(missing)) fail("Missing CSV columns: ", paste(missing, collapse = ", "))
  if (!nrow(data) || anyDuplicated(names(data))) fail("CSV is empty or has duplicate column names")
  forbidden <- c("late", "seed_group", "world_id", "order_id", "partition", "split", "policy", "source_sha")
  if (!length(features) || anyDuplicated(features) || any(features %in% forbidden)) fail("Invalid feature selection")
  for (name in c("seed_group", "world_id")) {
    data[[name]] <- trimws(as.character(data[[name]]))
    if (any(is.na(data[[name]]) | !nzchar(data[[name]]))) fail("Missing identifier in ", name)
  }
  data$late <- numeric_column(data$late, "late")
  if (any(!(data$late %in% c(0, 1)))) fail("late must be 0 or 1")
  for (name in features) data[[name]] <- numeric_column(data[[name]], name)
  data$.partition <- partition_values(data)
  if (any(vapply(split(data$.partition, data$seed_group), function(x) length(unique(x)) > 1L, logical(1)))) {
    fail("A seed_group occurs in both development and blind partitions")
  }
  if (any(vapply(split(data$seed_group, data$world_id), function(x) length(unique(x)) > 1L, logical(1)))) {
    fail("A world_id maps to more than one seed_group")
  }
  if ("order_id" %in% names(data)) {
    if (any(is.na(data$order_id) | !nzchar(trimws(as.character(data$order_id))))) fail("Missing order_id")
    if (anyDuplicated(data[c("world_id", "order_id")])) fail("Duplicate order snapshot: training requires one decision-time row per order")
  }
  counts <- c("official_won_orders", "official_on_time_orders")
  if (any(counts %in% names(data)) && !all(counts %in% names(data))) fail("Both official score count columns are required together")
  reconciled <- all(counts %in% names(data))
  if (reconciled) {
    for (name in counts) data[[name]] <- numeric_column(data[[name]], name)
    for (world in unique(data$world_id)) {
      rows <- data[data$world_id == world, , drop = FALSE]
      won <- unique(rows$official_won_orders)
      on_time <- unique(rows$official_on_time_orders)
      if (length(won) != 1L || length(on_time) != 1L || won != nrow(rows) || on_time != sum(rows$late == 0)) {
        fail("Labels do not reconcile with official score for world ", world)
      }
    }
  }
  attr(data, "labels_reconciled") <- reconciled
  data
}

scaler <- function(x) {
  center <- colMeans(x)
  scale <- apply(x, 2L, sd)
  constant <- !is.finite(scale) | scale < 1e-12
  scale[constant] <- 1
  list(center = center, scale = scale, constant = names(scale)[constant])
}

scaled_matrix <- function(x, preprocessor) {
  cbind(intercept = 1, sweep(sweep(x, 2L, preprocessor$center, "-"), 2L, preprocessor$scale, "/"))
}

fit_ridge <- function(x, y, lambda) {
  preprocessor <- scaler(x)
  design <- scaled_matrix(x, preprocessor)
  prevalence <- (sum(y) + 0.5) / (length(y) + 1)
  start <- c(qlogis(prevalence), rep(0, ncol(x)))
  if (length(unique(y)) < 2L) {
    return(list(coefficients = start, scaler = preprocessor, convergence = 0L,
                single_class_fallback = TRUE, lambda = lambda))
  }
  objective <- function(beta) {
    eta <- drop(design %*% beta)
    sum(pmax(eta, 0) + log1p(exp(-abs(eta))) - y * eta) + lambda * sum(beta[-1L]^2) / 2
  }
  gradient <- function(beta) {
    drop(crossprod(design, plogis(drop(design %*% beta)) - y)) + c(0, lambda * beta[-1L])
  }
  result <- optim(start, objective, gradient, method = "BFGS",
                  control = list(maxit = 1000L, reltol = 1e-11))
  if (result$convergence != 0L || any(!is.finite(result$par))) fail("Ridge optimization did not converge")
  list(coefficients = result$par, scaler = preprocessor, convergence = result$convergence,
       single_class_fallback = FALSE, lambda = lambda)
}

predict_ridge <- function(model, x) {
  plogis(drop(scaled_matrix(x, model$scaler) %*% model$coefficients))
}

classification_metrics <- function(y, probability) {
  if (length(y) != length(probability) || !length(y) || any(!is.finite(probability))) fail("Invalid prediction vector")
  clipped <- pmin(1 - 1e-12, pmax(1e-12, probability))
  positives <- sum(y == 1)
  negatives <- sum(y == 0)
  auc <- if (positives > 0 && negatives > 0) {
    (sum(rank(probability, ties.method = "average")[y == 1]) - positives * (positives + 1) / 2) / (positives * negatives)
  } else NA_real_
  threshold_rows <- lapply(c(0.02, 0.05, 0.1, 0.2, 0.5), function(threshold) {
    flagged <- probability >= threshold
    tp <- sum(flagged & y == 1)
    list(threshold = threshold, flagged_count = sum(flagged), true_positives = tp,
         false_positives = sum(flagged & y == 0),
         recall = if (positives) tp / positives else NA_real_,
         precision = if (sum(flagged)) tp / sum(flagged) else NA_real_)
  })
  bucket <- pmin(10L, floor(probability * 10) + 1L)
  calibration <- lapply(sort(unique(bucket)), function(bin) {
    selected <- bucket == bin
    list(bin = bin, count = sum(selected), mean_probability = mean(probability[selected]),
         observed_late_share = mean(y[selected]))
  })
  list(row_count = length(y), positive_count = positives, observed_late_share = mean(y),
       mean_probability = mean(probability), log_loss = -mean(y * log(clipped) + (1 - y) * log1p(-clipped)),
       brier = mean((probability - y)^2), auc = auc,
       calibration_gap = mean(probability) - mean(y), thresholds = threshold_rows, calibration_bins = calibration)
}

world_metrics <- function(data, probability) {
  values <- lapply(sort(unique(data$world_id)), function(world) {
    selected <- data$world_id == world
    m <- classification_metrics(data$late[selected], probability[selected])
    list(world_id = world, seed_group = unique(data$seed_group[selected])[[1L]],
         row_count = m$row_count, positive_count = m$positive_count, log_loss = m$log_loss, brier = m$brier)
  })
  list(macro_log_loss = mean(vapply(values, `[[`, numeric(1), "log_loss")),
       macro_brier = mean(vapply(values, `[[`, numeric(1), "brier")), worlds = values)
}

train_model <- function(data, features, lambda_grid, source_sha, input_md5 = NULL, seed = 20261115L) {
  data <- validate_data(data, features)
  development <- data[data$.partition == "development", , drop = FALSE]
  blind <- data[data$.partition == "blind", , drop = FALSE]
  groups <- sort(unique(development$seed_group))
  if (length(groups) < 2L) fail("At least two independent development seed groups are required")
  if (length(unique(development$late)) < 2L) fail("Development labels must include late and on-time orders")
  x <- as.matrix(development[features])
  oof <- matrix(NA_real_, nrow(development), length(lambda_grid))
  baseline <- rep(NA_real_, nrow(development))
  folds <- vector("list", length(groups))
  for (i in seq_along(groups)) {
    validation_rows <- development$seed_group == groups[[i]]
    training_rows <- !validation_rows
    baseline[validation_rows] <- (sum(development$late[training_rows]) + 0.5) / (sum(training_rows) + 1)
    fold_models <- lapply(seq_along(lambda_grid), function(j) {
      fitted <- fit_ridge(x[training_rows, , drop = FALSE], development$late[training_rows], lambda_grid[[j]])
      oof[validation_rows, j] <<- predict_ridge(fitted, x[validation_rows, , drop = FALSE])
      fitted
    })
    folds[[i]] <- list(held_out_seed_group = groups[[i]],
                      training_seed_groups = as_array(groups[groups != groups[[i]]]),
                      training_world_ids = as_array(sort(unique(development$world_id[training_rows]))),
                      validation_world_ids = as_array(sort(unique(development$world_id[validation_rows]))),
                      training_rows = sum(training_rows), validation_rows = sum(validation_rows),
                      center = as_array(fold_models[[1L]]$scaler$center),
                      scale = as_array(fold_models[[1L]]$scaler$scale),
                      single_class_fallback = fold_models[[1L]]$single_class_fallback)
  }
  if (anyNA(oof) || anyNA(baseline)) fail("Cross-validation left predictions missing")
  candidates <- lapply(seq_along(lambda_grid), function(j) {
    list(lambda = lambda_grid[[j]], pooled = classification_metrics(development$late, oof[, j]),
         by_world = world_metrics(development, oof[, j]))
  })
  objective <- vapply(candidates, function(x) x$by_world$macro_log_loss, numeric(1))
  # A deterministic tie prefers stronger regularization, without looking at blind data.
  selected <- order(objective, -lambda_grid)[[1L]]
  fitted <- fit_ridge(x, development$late, lambda_grid[[selected]])
  baseline_metrics <- list(pooled = classification_metrics(development$late, baseline),
                           by_world = world_metrics(development, baseline))
  candidate_metrics <- candidates[[selected]]
  blind_result <- if (nrow(blind)) {
    predictions <- predict_ridge(fitted, as.matrix(blind[features]))
    constant <- rep((sum(development$late) + 0.5) / (nrow(development) + 1), nrow(blind))
    list(row_count = nrow(blind), seed_groups = as_array(sort(unique(blind$seed_group))),
         world_ids = as_array(sort(unique(blind$world_id))),
         candidate = list(pooled = classification_metrics(blind$late, predictions), by_world = world_metrics(blind, predictions)),
         baseline = list(pooled = classification_metrics(blind$late, constant), by_world = world_metrics(blind, constant)),
         used_for_fitting_or_lambda_selection = FALSE)
  } else NULL
  warnings <- c(
    "Cross-validation chooses lambda; its selected score is developmental and may be optimistic.",
    "Prediction metrics do not establish a policy's on-time share, margin, or final-world reliability.",
    "The supplied labels cover won orders; effects on requests rejected by the source policy are not identified.",
    "Only decision-time features are valid; provenance and absence of future information require exporter review."
  )
  if (length(groups) < 5L) warnings <- c(warnings, "Fewer than five development seed groups: world generalization is weakly measured.")
  if (is.null(blind_result)) warnings <- c(warnings, "No untouched blind partition was supplied.")
  list(schemaVersion = 1L, modelType = "ridge_logistic", target = "late", probability = "P(late)",
       status = "development_candidate", featureNames = as_array(features),
       center = as_array(fitted$scaler$center), scale = as_array(fitted$scaler$scale),
       coefficients = as_array(fitted$coefficients),
       training = list(source_sha = source_sha, input_md5 = input_md5,
                       world_ids = as_array(sort(unique(development$world_id))), seed_groups = as_array(groups),
                       row_count = nrow(development), positive_count = sum(development$late),
                       negative_count = sum(development$late == 0), partition = "development",
                       data_source_shas = if ("source_sha" %in% names(data)) as_array(sort(unique(as.character(development$source_sha)))) else NULL,
                       labels_reconciled_with_official_score_columns = isTRUE(attr(data, "labels_reconciled")),
                       selected_lambda = lambda_grid[[selected]], objective = "sum_log_loss + lambda/2 * sum(non_intercept_coefficients^2)",
                       intercept_penalized = FALSE, constant_features = as_array(fitted$scaler$constant),
                       random_seed = seed, r_version = R.version.string),
       validation = list(method = "leave_one_seed_group_out", preprocessing = "fit_inside_each_training_fold",
                         selection_criterion = "mean_world_log_loss", fold_count = length(groups), folds = folds,
                         lambda_candidates = candidates, selected = candidate_metrics, intercept_baseline = baseline_metrics,
                         selected_beats_baseline_log_loss = candidate_metrics$by_world$macro_log_loss < baseline_metrics$by_world$macro_log_loss,
                         selected_beats_baseline_brier = candidate_metrics$by_world$macro_brier < baseline_metrics$by_world$macro_brier,
                         untouched_blind = blind_result, automatic_policy_promotion = FALSE),
       limitations = as_array(warnings))
}

self_check <- function() {
  set.seed(20261115L)
  n <- 800L
  x <- matrix(rnorm(n * length(DEFAULT_FEATURES)), nrow = n,
              dimnames = list(NULL, DEFAULT_FEATURES))
  data <- data.frame(seed_group = rep(paste0("seed-", 1:5), each = n / 5),
                     world_id = rep(paste0("world-", 1:5), each = n / 5),
                     late = rbinom(n, 1, plogis(-1.2 + 2 * x[, 1] - x[, 2])), x,
                     partition = rep(c(rep("development", 4), "blind"), each = n / 5), check.names = FALSE)
  model <- train_model(data, DEFAULT_FEATURES, c(0.1, 1, 10), paste(rep("a", 40), collapse = ""))
  stopifnot(model$training$row_count == 640L, length(model$coefficients) == 17L,
            all(unlist(model$scale) > 0),
            model$validation$selected_beats_baseline_log_loss,
            model$validation$selected_beats_baseline_brier,
            !("world-5" %in% unlist(model$training$world_ids)),
            !model$validation$untouched_blind$used_for_fitting_or_lambda_selection)
  for (fold in model$validation$folds) {
    stopifnot(!(fold$held_out_seed_group %in% unlist(fold$training_seed_groups)))
    expected <- colMeans(as.matrix(data[data$partition == "development" & data$seed_group != fold$held_out_seed_group, DEFAULT_FEATURES]))
    stopifnot(max(abs(unlist(fold$center) - expected)) < 1e-12)
  }
  leaky <- data
  leaky$seed_group[leaky$partition == "blind"] <- "seed-1"
  stopifnot(inherits(tryCatch(validate_data(leaky, DEFAULT_FEATURES), error = identity), "error"))
  bad <- data
  bad$official_won_orders <- 1
  bad$official_on_time_orders <- 1
  stopifnot(inherits(tryCatch(validate_data(bad, DEFAULT_FEATURES), error = identity), "error"))
  single <- fit_ridge(x[1:10, , drop = FALSE], rep(0, 10), 1)
  stopifnot(single$single_class_fallback, all(is.finite(predict_ridge(single, x[1:2, , drop = FALSE]))))
  stopifnot(identical(json_string(paste0('a"b\\c', "\n")), '"a\\"b\\\\c\\u000a"'))
  cat(json_encode(list(status = "pass", kind = "synthetic_numerical_self_check",
                       checks = as_array(c("signal_recovery", "fold_only_scaling", "blind_exclusion", "partition_leak_rejection",
                                           "official_count_mismatch_rejection", "single_class_fold_fallback", "json_escaping")))), "\n")
}

main <- function() {
  options <- parse_args(commandArgs(trailingOnly = TRUE))
  if (isTRUE(options$help)) {
    cat("Usage: Rscript fit_reliability.R --input orders.csv --output model.json --source-sha FULL_SHA\n",
        "  [--features comma,separated | auto] [--lambda-grid 0.1,1,10] [--seed 20261115]\n",
        "  Rscript fit_reliability.R --self-check\n", sep = "")
    return(invisible(NULL))
  }
  if (isTRUE(options[["self-check"]])) return(self_check())
  for (name in c("input", "output", "source-sha")) if (is.null(options[[name]])) fail("Missing --", name)
  sha <- tolower(options[["source-sha"]])
  if (!grepl("^([0-9a-f]{40}|[0-9a-f]{64})$", sha)) fail("source-sha must be a full hexadecimal source commit SHA")
  if (identical(normalizePath(options$input, mustWork = FALSE), normalizePath(options$output, mustWork = FALSE))) fail("Input and output must differ")
  digest <- unname(tools::md5sum(options$input))
  data <- read.csv(options$input, stringsAsFactors = FALSE, check.names = FALSE)
  if (!identical(digest, unname(tools::md5sum(options$input)))) fail("Input changed while being read")
  features <- DEFAULT_FEATURES
  if (!is.null(options$features)) {
    if (identical(options$features, "auto")) {
      excluded <- grepl("(^\\.|^(official|future|truth|reveal|actual|final)_|(^|_)(id|seed|world|source|policy|partition|split|late|label|target|outcome|score|margin|revenue|won_orders|on_time|delivered|picked_up|cancelled|canceled)(_|$))", names(data), ignore.case = TRUE)
      features <- names(data)[!excluded]
    } else features <- trimws(strsplit(options$features, ",", fixed = TRUE)[[1L]])
  }
  lambda_grid <- if (is.null(options[["lambda-grid"]])) c(0.1, 1, 10) else suppressWarnings(as.numeric(strsplit(options[["lambda-grid"]], ",", fixed = TRUE)[[1L]]))
  if (!length(lambda_grid) || any(!is.finite(lambda_grid) | lambda_grid <= 0)) fail("lambda-grid must contain finite positive numbers")
  lambda_grid <- sort(unique(lambda_grid))
  seed <- if (is.null(options$seed)) 20261115L else suppressWarnings(as.numeric(options$seed))
  if (length(seed) != 1L || !is.finite(seed) || seed != floor(seed) || seed < 0 || seed > .Machine$integer.max) fail("Invalid random seed")
  set.seed(seed)
  model <- train_model(data, features, lambda_grid, sha, digest, seed)
  write_json(model, options$output)
  cat(json_encode(list(status = "candidate_written", output = options$output,
                       training_rows = model$training$row_count, development_seed_groups = length(model$training$seed_groups),
                       selected_lambda = model$training$selected_lambda,
                       cv_log_loss = model$validation$selected$by_world$macro_log_loss,
                       baseline_cv_log_loss = model$validation$intercept_baseline$by_world$macro_log_loss,
                       automatic_policy_promotion = FALSE)), "\n")
}

if (sys.nframe() == 0L) tryCatch(main(), error = function(e) { message("ERROR: ", conditionMessage(e)); quit(status = 1L) })
