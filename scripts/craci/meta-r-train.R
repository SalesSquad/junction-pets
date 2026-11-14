#!/usr/bin/env Rscript
# CRACI Chibi Lens contextual scorer tournament. Synthetic scores only.
# Every model is trained only on train, selected only on calibration,
# and measured only once on shifted holdout; source is an immutable PR SHA.
suppressPackageStartupMessages(library(rpart))
suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3L) {
  stop("Usage: Rscript meta-r-train.R DATA.csv OUTPUT_DIR META_SOURCE_SHA")
}
source_pin <- "634f1e0e6cb2de46bcf0a783532d46c23f513d11"
stopifnot(identical(args[[3]], source_pin))
input <- args[[1]]
out <- args[[2]]
if (!dir.exists(out)) dir.create(out, recursive = TRUE)
stopifnot(length(list.files(out, all.files = FALSE)) == 0L)

receipt <- jsonlite::read_json(file.path(dirname(input), "dataset-receipt.json"),
                               simplifyVector = TRUE)
stopifnot(identical(receipt$source_sha, source_pin),
          isTRUE(receipt$original_baseline_seeds_disjoint),
          !isTRUE(receipt$real_visual_benchmark))
hashed <- strsplit(system2("sha256sum", shQuote(input), stdout = TRUE),
                   "[[:space:]]+")[[1]][[1]]
stopifnot(identical(hashed, receipt$dataset_sha256))

df <- read.csv(input, stringsAsFactors = FALSE, check.names = FALSE)
features <- c("visual", "text", "shape", "quality", "recency")
required <- c("split", "cohort", "row_id", "label", "hard_negative",
              "baseline_probability", features)
stopifnot(all(required %in% names(df)), !anyNA(df[required]),
          nrow(df) == 30000L, length(unique(df$cohort)) == 1L,
          setequal(unique(df$split), c("train", "cal", "shifted")),
          all(df$label %in% 0:1), all(df$hard_negative %in% 0:1),
          !any(df$hard_negative == 1 & df$label == 1),
          all(vapply(df[features], is.numeric, logical(1))),
          all(vapply(df[features], function(x)
            all(is.finite(x) & x >= 0 & x <= 1), logical(1))),
          all(is.finite(df$baseline_probability) &
              df$baseline_probability >= 0 & df$baseline_probability <= 1))
train <- df[df$split == "train", , drop = FALSE]
cal <- df[df$split == "cal", , drop = FALSE]
shifted <- df[df$split == "shifted", , drop = FALSE]
stopifnot(nrow(train) == 20000L, nrow(cal) == 5000L,
          nrow(shifted) == 5000L,
          all(c(0L, 1L) %in% train$label),
          all(c(0L, 1L) %in% cal$label),
          all(c(0L, 1L) %in% shifted$label))
for (subset in list(train, cal, shifted)) {
  stopifnot(!anyDuplicated(subset$row_id),
            identical(sort(subset$row_id), seq_len(nrow(subset)) - 1L))
}

# Training-only, five measured features, never label proxies, unique row ID,
# cohort, split/domain or the frozen checkpoint's prediction as a predictor.
main_formula <- label ~ visual + text + shape + quality + recency
interaction_formula <- label ~ (visual + text + shape + quality + recency)^2
tree_formula <- factor(label, levels = c(0, 1)) ~
  visual + text + shape + quality + recency
glm_main <- suppressWarnings(glm(main_formula, data = train, family = binomial(),
                                 control = glm.control(maxit = 100)))
glm_interaction <- suppressWarnings(glm(interaction_formula, data = train,
                                        family = binomial(),
                                        control = glm.control(maxit = 100)))
tree_d3 <- rpart(tree_formula, data = train, method = "class",
                 control = rpart.control(maxdepth = 3, minbucket = 50,
                                         minsplit = 100, cp = 0.002, xval = 0))
tree_d5 <- rpart(tree_formula, data = train, method = "class",
                 control = rpart.control(maxdepth = 5, minbucket = 40,
                                         minsplit = 80, cp = 0.001, xval = 0))
models <- list(glm_main = glm_main, glm_interaction = glm_interaction,
               tree_d3 = tree_d3, tree_d5 = tree_d5)

score <- function(name, data) {
  if (name == "baseline_frozen" || name == "baseline_calibrated") {
    return(data$baseline_probability)
  }
  model <- models[[name]]
  if (inherits(model, "glm")) {
    values <- suppressWarnings(as.numeric(predict(model, newdata = data,
                                                  type = "response")))
  } else {
    prob <- predict(model, newdata = data, type = "prob")
    values <- if ("1" %in% colnames(prob)) as.numeric(prob[, "1"]) else
      rep(0, nrow(data))
  }
  stopifnot(length(values) == nrow(data), all(is.finite(values)))
  pmax(0, pmin(1, values))
}

target_fpr <- 0.05
threshold_at_fpr <- function(prob, label) {
  negatives <- sort(prob[label == 0L], decreasing = TRUE)
  stopifnot(length(negatives) > 0L)
  k <- floor(target_fpr * length(negatives))
  # Reject the (k+1)-st highest negative even when ties straddle the boundary.
  # Calibration may abstain more, never quietly violate the requested FPR.
  threshold <- negatives[[k + 1L]] + 1e-10
  stopifnot(mean(negatives >= threshold) <= target_fpr)
  threshold
}
summary_metrics <- function(data, prob, threshold) {
  chosen <- prob >= threshold
  positive <- data$label == 1L
  hard <- data$hard_negative == 1L
  tp <- sum(chosen & positive)
  fp <- sum(chosen & !positive)
  tn <- sum(!chosen & !positive)
  fn <- sum(!chosen & positive)
  stopifnot(tp + fp + tn + fn == nrow(data))
  list(rows = nrow(data), positives = sum(positive), negatives = sum(!positive),
       tp = tp, fp = fp, tn = tn, fn = fn,
       recall = as.numeric(tp / sum(positive)),
       fpr = as.numeric(fp / sum(!positive)),
       hard_negative_fpr = if (any(hard)) as.numeric(
         sum(chosen & hard) / sum(hard)) else NULL,
       precision = if (tp + fp > 0) as.numeric(tp / (tp + fp)) else NULL,
       abstention = as.numeric(mean(!chosen)),
       brier = as.numeric(mean((prob - data$label)^2)),
       threshold = as.numeric(threshold),
       identityVerified = FALSE, actionAuthorized = FALSE)
}

model_names <- c("baseline_frozen", "baseline_calibrated", names(models))
cal_probs <- setNames(lapply(model_names, score, data = cal), model_names)
thresholds <- setNames(lapply(model_names, function(name) {
  if (name == "baseline_frozen") return(as.numeric(receipt$baseline_threshold))
  threshold_at_fpr(cal_probs[[name]], cal$label)
}), model_names)
cal_metrics <- setNames(lapply(model_names, function(name) {
  summary_metrics(cal, cal_probs[[name]], thresholds[[name]])
}), model_names)
anchor <- cal_metrics[["baseline_calibrated"]]
admitted <- Filter(function(name) {
  m <- cal_metrics[[name]]
  m$fpr <= min(target_fpr, anchor$fpr) + 1e-12 &&
    m$recall > anchor$recall + 1e-4
}, names(models))
winner <- "baseline_calibrated"
if (length(admitted)) {
  # Selection is validation-only and deterministic. FPR is primary safety gate.
  scores <- vapply(admitted, function(nm) cal_metrics[[nm]]$recall, numeric(1))
  false_rates <- vapply(admitted, function(nm) cal_metrics[[nm]]$fpr, numeric(1))
  winner <- admitted[order(-scores, false_rates, admitted)][[1]]
}

set.seed(20261114L + as.integer(unique(df$cohort)))
shifted_probs <- setNames(lapply(model_names, score, data = shifted), model_names)
shifted_metrics <- setNames(lapply(model_names, function(name) {
  summary_metrics(shifted, shifted_probs[[name]], thresholds[[name]])
}), model_names)
# Paired bootstrap on identical shifted-positive observations. The baseline
# remains the re-calibrated frozen score, not a weaker uncalibrated reference.
positive <- which(shifted$label == 1L)
delta <- as.integer(shifted_probs[[winner]][positive] >= thresholds[[winner]]) -
  as.integer(shifted_probs[["baseline_calibrated"]][positive] >=
               thresholds[["baseline_calibrated"]])
draws <- replicate(1200, mean(sample(delta, length(delta), replace = TRUE)))
ci <- as.numeric(quantile(draws, c(0.025, 0.975), names = FALSE, type = 1))
selected <- shifted_metrics[[winner]]
baseline <- shifted_metrics[["baseline_calibrated"]]
quality <- if (winner != "baseline_calibrated" &&
               selected$fpr <= baseline$fpr &&
               selected$recall > baseline$recall &&
               ci[[1]] > 0) {
  "EXPLORATORY_SYNTHETIC_HELDOUT_GAIN"
} else "NO_RELIABLE_SHIFTED_GAIN"

report <- list(
  schema = "craci.meta-r-candidate-tournament.v1",
  sourceCommit = source_pin, cohort = as.integer(unique(df$cohort)),
  datasetSha256 = receipt$dataset_sha256,
  modelFamiliesTrained = names(models),
  candidateCount = length(models),
  trainingCases = nrow(train), calibrationCases = nrow(cal),
  independentShiftedCases = nrow(shifted),
  calibrationTargetFpr = target_fpr,
  frozenBaselineThreshold = receipt$baseline_threshold,
  calibratedBaselineMethod = "FPR-matched on calibration negatives",
  calibratedCandidate = winner,
  calibration = cal_metrics,
  shiftedHoldout = shifted_metrics,
  selectedMinusCalibratedBaselineShiftedRecall = as.numeric(mean(delta)),
  pairedBootstrap95pct = ci,
  selectedMinusBaselineShiftedFalseCandidates = selected$fp - baseline$fp,
  qualityClaim = quality,
  syntheticScoreModelOnly = TRUE, realCameraModel = FALSE,
  identityVerified = FALSE, actionAuthorized = FALSE,
  actualProviderCostEur = NULL
)
jsonlite::write_json(report, file.path(out, "training-report.json"),
                     pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 8)
saveRDS(list(models = models, calibrationThresholds = thresholds,
             selected = winner, feature_names = features,
             sourceCommit = source_pin, datasetSha256 = receipt$dataset_sha256),
        file.path(out, "trained-models.rds"), compress = "xz")
stopifnot(file.size(file.path(out, "training-report.json")) > 100L,
          file.size(file.path(out, "trained-models.rds")) > 100L)
cat(jsonlite::toJSON(list(
  cohort = as.integer(unique(df$cohort)), selected = winner,
  quality = quality, testRecall = selected$recall,
  baselineRecall = baseline$recall, testFpr = selected$fpr,
  baselineFpr = baseline$fpr, deltaBootstrap95pct = ci),
  auto_unbox = TRUE, null = "null"), "\n")
