#!/usr/bin/env Rscript
# CRACI Rokoko policy tournament: training-only fitting, calibration-only
# selection, and paired fresh/OOD evaluation. Synthetic physics, not robot safety.
suppressPackageStartupMessages(library(rpart))
suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3L) {
  stop("Usage: Rscript rokoko-r-train.R DATA.csv OUT_DIR SOURCE_SHA")
}
input <- args[[1]]
output <- args[[2]]
source_sha <- args[[3]]
if (!grepl("^[a-f0-9]{40}$", source_sha) ||
    !identical(source_sha, "59479b42b177c1829a2e6678adfff1fb68aef09c")) {
  stop("Source must be the pre-registered immutable Rokoko simulator")
}
if (!dir.exists(output)) dir.create(output, recursive = TRUE)
stopifnot(dir.exists(output), length(list.files(output)) == 0L)

dataset <- read.csv(input, check.names = FALSE, stringsAsFactors = FALSE)
feature_names <- sprintf("x%02d", 1:18)
required <- c("split", "world_id", "cohort", "policy", "success", "unsafe",
              feature_names)
stopifnot(all(required %in% names(dataset)),
          nrow(dataset) == 440L, !anyNA(dataset[required]),
          all(dataset$success %in% 0:1), all(dataset$unsafe %in% 0:1),
          all(dataset$success + dataset$unsafe <= 1),
          identical(sort(unique(dataset$split)),
                    sort(c("train", "cal", "test", "ood"))),
          setequal(unique(dataset$policy), c("push_medium", "heuristic")))
expected <- c(train = 80L, cal = 40L, test = 60L, ood = 40L)
for (split in names(expected)) {
  d <- dataset[dataset$split == split, , drop = FALSE]
  stopifnot(nrow(d) == 2L * expected[[split]],
            length(unique(d$world_id)) == expected[[split]],
            all(table(d$world_id) == 2L))
}
# World-seed disjointness is checked directly without post-outcome inputs.
ids <- lapply(names(expected),
              function(split) unique(dataset$world_id[dataset$split == split]))
stopifnot(length(unique(unlist(ids))) == sum(expected))
for (name in feature_names) stopifnot(is.numeric(dataset[[name]]))

train <- dataset[dataset$split == "train", , drop = FALSE]
cal <- dataset[dataset$split == "cal", , drop = FALSE]
train$policy <- factor(train$policy, levels = c("push_medium", "heuristic"))
dataset$policy <- factor(dataset$policy, levels = levels(train$policy))
cal$policy <- factor(cal$policy, levels = levels(train$policy))
features <- feature_names[vapply(train[feature_names], function(x)
  is.finite(var(x)) && var(x) > 1e-8, logical(1))]
stopifnot(length(features) >= 3L)
# Train only on initial states. Never use return, options, safety outcome or
# world_id as a feature. Interactions allow contextual policy preferences.
formula <- as.formula(paste0("success ~ policy * (",
                             paste(features, collapse = " + "), ")"))
risk_formula <- update(formula, unsafe ~ .)
# A one-class safety/success target is valid negative scientific evidence.
# rpart 4.3 can fail internally on a forced two-level factor with one observed
# class; use an explicit constant model instead of deleting the cohort.
constant_model <- function(y) structure(
  list(probability = mean(y)), class = "craci_constant_model")
fit_glm <- function(target, model_formula) {
  if (length(unique(train[[target]])) < 2L) return(constant_model(train[[target]]))
  suppressWarnings(glm(model_formula, data = train, family = binomial(),
                       control = glm.control(maxit = 70)))
}
fit_tree <- function(target) {
  if (length(unique(train[[target]])) < 2L) return(constant_model(train[[target]]))
  tree_formula <- as.formula(paste0(
    "factor(", target, ", levels = c(0, 1)) ~ ",
    paste(c("policy", features), collapse = " + ")))
  rpart(tree_formula, data = train, method = "class",
        control = rpart.control(maxdepth = 4, cp = 0.005,
                                minsplit = 20, xval = 0))
}
glm_success <- fit_glm("success", formula)
glm_risk <- fit_glm("unsafe", risk_formula)
tree_success <- fit_tree("success")
tree_risk <- fit_tree("unsafe")

predict_prob <- function(model, data, kind) {
  if (inherits(model, "craci_constant_model")) {
    return(rep(model$probability, nrow(data)))
  }
  if (kind == "glm") {
    p <- suppressWarnings(as.numeric(predict(model, newdata = data,
                                             type = "response")))
  } else {
    raw <- predict(model, newdata = data, type = "prob")
    p <- if ("1" %in% colnames(raw)) raw[, "1"] else rep(0, nrow(data))
  }
  p[!is.finite(p)] <- 0
  pmin(1, pmax(0, p))
}

# Selection occurs only between two policy implementations that independently
# enforce the simulator's safety mask. No learned output can override that mask.
pick <- function(data, model = c("baseline", "glm", "tree")) {
  model <- match.arg(model)
  pushed <- data[data$policy == "push_medium", , drop = FALSE]
  heuristic <- data[data$policy == "heuristic", , drop = FALSE]
  pushed <- pushed[order(pushed$world_id), , drop = FALSE]
  heuristic <- heuristic[order(heuristic$world_id), , drop = FALSE]
  stopifnot(nrow(pushed) == nrow(heuristic),
            identical(pushed$world_id, heuristic$world_id))
  if (model == "baseline") return(pushed)
  s_model <- if (model == "glm") glm_success else tree_success
  u_model <- if (model == "glm") glm_risk else tree_risk
  score <- function(d) {
    predict_prob(s_model, d, model) -
      5 * predict_prob(u_model, d, model)
  }
  select_heuristic <- score(heuristic) > score(pushed) + 1e-9
  pushed[select_heuristic, ] <- heuristic[select_heuristic, ]
  pushed
}

measure <- function(d) {
  list(worlds = nrow(d), success = sum(d$success), unsafe = sum(d$unsafe),
       success_rate = unname(mean(d$success)),
       unsafe_rate = unname(mean(d$unsafe)))
}

baseline_cal <- pick(cal, "baseline")
cal_results <- lapply(c("baseline", "glm", "tree"), function(name)
  c(list(model = name), measure(pick(cal, name))))
names(cal_results) <- c("baseline", "glm", "tree")
admitted <- Filter(function(m)
  m$unsafe <= sum(baseline_cal$unsafe) &&
  (m$success > sum(baseline_cal$success) ||
   (m$success == sum(baseline_cal$success) &&
    m$unsafe < sum(baseline_cal$unsafe))), cal_results[c("glm", "tree")])
winner <- "baseline"
if (length(admitted)) {
  order <- order(vapply(admitted, function(m) -m$success, numeric(1)),
                 vapply(admitted, function(m) m$unsafe, numeric(1)))
  winner <- admitted[[order[[1]]]]$model
}

paired <- function(split, model) {
  d <- dataset[dataset$split == split, , drop = FALSE]
  base <- pick(d, "baseline")
  candidate <- pick(d, model)
  difference <- candidate$success - base$success
  # Deterministic paired bootstrap across worlds; confidence intervals are
  # exploratory because simulator worlds share generation assumptions.
  set.seed(2114 + sum(utf8ToInt(split)))
  sample_n <- length(difference)
  draws <- replicate(1200, mean(sample(difference, sample_n, replace = TRUE)))
  interval <- as.numeric(quantile(draws, c(0.025, 0.975),
                                  names = FALSE, type = 1))
  list(split = split, baseline = measure(base),
       selected = measure(candidate), selected_model = model,
       delta_success = unname(mean(difference)),
       delta_success_95pct_ci = unname(interval),
       unsafe_difference = unname(sum(candidate$unsafe - base$unsafe)),
       synthetic_only = TRUE)
}

report <- list(
  schema = "craci.rokoko.r-policy-tournament.v1",
  simulator_source_sha = source_sha,
  model_families_tested = c("binomial_glm", "rpart_tree"),
  model_fit_status = list(
    success_glm = if (inherits(glm_success, "craci_constant_model")) "single_class_constant" else "fitted",
    unsafe_glm = if (inherits(glm_risk, "craci_constant_model")) "single_class_constant" else "fitted",
    success_tree = if (inherits(tree_success, "craci_constant_model")) "single_class_constant" else "fitted",
    unsafe_tree = if (inherits(tree_risk, "craci_constant_model")) "single_class_constant" else "fitted"
  ),
  training_outcomes = list(
    success_positive = sum(train$success), unsafe_positive = sum(train$unsafe)
  ),
  training_worlds = expected[["train"]],
  calibration_worlds = expected[["cal"]],
  test_worlds = expected[["test"]],
  ood_worlds = expected[["ood"]],
  seed_disjoint = TRUE, post_outcome_predictors = FALSE,
  calibrated_model = winner,
  calibration = cal_results,
  heldout = paired("test", winner),
  ood = paired("ood", winner),
  non_deployment = "Simulated Rokoko world policy selection, no physical robot",
  actual_cost_eur = NULL
)
report$quality_claim <- if (
  winner != "baseline" &&
  report$heldout$selected$success > report$heldout$baseline$success &&
  report$heldout$selected$unsafe <= report$heldout$baseline$unsafe &&
  report$ood$selected$unsafe <= report$ood$baseline$unsafe
) "EXPLORATORY_HELDOUT_GAIN_NOT_HARDWARE_QUALIFIED" else "NO_VERIFIED_GAIN"
jsonlite::write_json(report, file.path(output, "training-report.json"),
                     pretty = TRUE, auto_unbox = TRUE, null = "null")
saveRDS(list(success_glm = glm_success, unsafe_glm = glm_risk,
             success_tree = tree_success, unsafe_tree = tree_risk,
             winner = winner, features = features),
        file.path(output, "trained-models.rds"), compress = "xz")
stopifnot(file.exists(file.path(output, "training-report.json")),
          file.exists(file.path(output, "trained-models.rds")))
cat(jsonlite::toJSON(list(winner = winner, claim = report$quality_claim,
                          heldout = report$heldout, ood = report$ood),
                     auto_unbox = TRUE, null = "null"), "\n")
