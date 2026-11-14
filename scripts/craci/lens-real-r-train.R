#!/usr/bin/env Rscript
# REAL camera object crops from the MIT-licensed BOP YCB-V dataset.
# Source archive is independently SHA-pinned. Internal scene-disjoint
# recognition/abstention trial, NOT a BOP benchmark score or glasses identity.
suppressPackageStartupMessages(library(rpart))
suppressPackageStartupMessages(library(nnet))
suppressPackageStartupMessages(library(jsonlite))

argv <- commandArgs(trailingOnly = TRUE)
if (length(argv) != 5L) {
  stop("Usage: Rscript lens-real-r-train.R FEATURES.csv ADMISSION.json OUT SOURCE_SHA FEATURE_PROFILE")
}
profile <- argv[[5]]
if (!profile %in% c("all", "color", "spatial", "gradient")) {
  stop("Invalid pre-registered feature profile")
}
src <- "c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d"
if (!identical(argv[[4]], src)) stop("Source archive pin mismatch")
if (!file.exists(argv[[1]]) || !file.exists(argv[[2]])) {
  stop("Real source feature CSV or admission record is missing")
}
out <- argv[[3]]
if (!dir.exists(out)) dir.create(out, recursive = TRUE)
stopifnot(length(list.files(out, all.files = FALSE)) == 0L)
metadata <- jsonlite::read_json(argv[[2]], simplifyVector = TRUE)
stopifnot(
  identical(metadata$status, "approved_public_benchmark_only"),
  identical(metadata$sourceLicense, "MIT"),
  identical(metadata$sourceArchiveSha256, src),
  isTRUE(metadata$rawPixelsExported == FALSE),
  isTRUE(metadata$notBopLeaderboardComparable),
  !isTRUE(metadata$physicalIdentityVerified),
  !isTRUE(metadata$actionAuthorized)
)
csv_sha <- strsplit(system2("sha256sum", shQuote(argv[[1]]),
                             stdout = TRUE), "[[:space:]]+")[[1]][[1]]
stopifnot(identical(csv_sha, metadata$csvSha256))

source <- read.csv(argv[[1]], stringsAsFactors = FALSE, check.names = FALSE)
all_features <- sprintf("f%02d", 0:47)
features <- switch(profile,
  all = all_features,
  color = sprintf("f%02d", 0:23),
  spatial = sprintf("f%02d", 24:39),
  gradient = sprintf("f%02d", 40:47))
required <- c("source", "license", "modality", "split", "scene_id",
              "frame_id", "object_id", "visible_fraction", features)
if (!all(required %in% names(source))) stop("Source CSV missing feature schema")
stopifnot(!anyNA(source[required]),
          all(source$source == "bop-ycbv-mit"),
          all(source$license == "MIT"),
          all(source$modality == "REAL_RGB"),
          all(source$object_id %in% c(4, 6, 9, 15)),
          all(is.finite(source$visible_fraction) &
              source$visible_fraction >= 0.2 &
              source$visible_fraction <= 1),
          all(vapply(source[features], function(x)
            is.numeric(x) && all(is.finite(x) & x >= 0 & x <= 1),
            logical(1))))
split_scenes <- list(
  # Scene 58 has no instance of the four pre-registered classes and therefore
  # contributes no crop. It remains recorded in the upstream source manifest.
  train = c(48L, 49L, 50L, 51L, 54L, 55L),
  cal = c(52L, 53L, 56L, 57L),
  test = c(59L)
)
stopifnot(setequal(unique(source$split), names(split_scenes)))
for (split in names(split_scenes)) {
  rows <- source[source$split == split, ]
  stopifnot(setequal(unique(rows$scene_id), split_scenes[[split]]),
            all(rows$scene_id %in% split_scenes[[split]]),
            all(c(4, 6, 9, 15) %in% rows$object_id))
}
# All previews from one physical scene stay in the SAME partition.
stopifnot(length(unique(unlist(split_scenes))) ==
          length(unlist(split_scenes)))
train <- source[source$split == "train", , drop = FALSE]
cal <- source[source$split == "cal", , drop = FALSE]
test <- source[source$split == "test", , drop = FALSE]
levels <- as.character(c(4, 6, 9, 15))
for (set in list(train, cal, test)) {
  stopifnot(nrow(set) >= 30L, all(levels %in% as.character(set$object_id)))
}
train$label <- factor(as.character(train$object_id), levels = levels)
cal$label <- factor(as.character(cal$object_id), levels = levels)
test$label <- factor(as.character(test$object_id), levels = levels)
formula <- as.formula(paste("label ~", paste(features, collapse = " + ")))
set.seed(20261114)
multi <- suppressWarnings(nnet::multinom(
  formula, data = train, maxit = 150, MaxNWts = 3000, trace = FALSE,
  decay = 0.003))
tree <- rpart::rpart(formula, data = train, method = "class",
                     control = rpart.control(maxdepth = 6, cp = 0.002,
                                             minsplit = 28, minbucket = 12,
                                             xval = 0))

# FROZEN nearest-centroid reference trained only on train. Transparent and
# intentionally light-weight; the comparison is an internal baseline.
centroids <- vapply(levels, function(label) {
  colMeans(train[train$label == label, features, drop = FALSE])
}, numeric(length(features)))
rownames(centroids) <- features

softmax <- function(raw) {
  shifted <- raw - apply(raw, 1, max)
  ex <- exp(shifted)
  ex / rowSums(ex)
}
pred_prob <- function(name, data) {
  if (name == "centroid") {
    x <- as.matrix(data[, features, drop = FALSE])
    distances <- vapply(seq_along(levels), function(j)
      rowSums(sweep(x, 2, centroids[, j])^2),
      numeric(nrow(x)))
    scores <- softmax(-distances / 0.07)
  } else if (name == "multinom") {
    scores <- predict(multi, newdata = data, type = "probs")
  } else if (name == "tree") {
    scores <- predict(tree, newdata = data, type = "prob")
  } else stop("Unsupported model")
  if (is.vector(scores) || is.null(dim(scores))) {
    stop("Unexpected class probabilities")
  }
  scores <- as.matrix(scores)
  stopifnot(nrow(scores) == nrow(data), all(levels %in% colnames(scores)),
            all(is.finite(scores)), all(scores >= 0))
  scores[, levels, drop = FALSE]
}
metrics <- function(data, scores, threshold) {
  labels <- as.character(data$label)
  choice <- levels[max.col(scores, ties.method = "first")]
  confidence <- apply(scores, 1, max)
  accept <- confidence >= threshold
  correct <- choice == labels
  wrong_accepted <- sum(accept & !correct)
  accepted <- sum(accept)
  by_label <- lapply(levels, function(label) {
    items <- labels == label
    list(total = sum(items),
         acceptedCorrect = sum(accept & correct & items),
         wrongAccepted = sum(accept & !correct & items))
  })
  names(by_label) <- levels
  list(examples = length(labels), accepted = accepted,
       acceptedCorrect = sum(accept & correct),
       wrongAccepted = wrong_accepted,
       correctCoverage = as.numeric(mean(accept & correct)),
       wrongCandidateFraction = as.numeric(mean(accept & !correct)),
       abstained = sum(!accept),
       rawTop1 = as.numeric(mean(correct)),
       acceptedPrecision = if (accepted) sum(accept & correct) / accepted else NULL,
       threshold = threshold, classBreakdown = by_label)
}

# Calibrate to <= 5% WRONG accepted proposals on held-out calibration only,
# NOT using hidden test labels to select model or threshold.
threshold <- function(data, scores) {
  choice <- levels[max.col(scores, ties.method = "first")]
  errors <- sort(apply(scores, 1, max)[
    choice != as.character(data$label)], decreasing = TRUE)
  if (!length(errors)) return(0)
  k <- floor(nrow(data) * 0.05)
  if (length(errors) <= k) return(0)
  cutoff <- errors[[k + 1L]] + 1e-9
  if (cutoff > 1) return(Inf)
  cutoff
}
names <- c("centroid", "multinom", "tree")
cal_prob <- setNames(lapply(names, pred_prob, data = cal), names)
thresholds <- setNames(lapply(names, function(name)
  threshold(cal, cal_prob[[name]])), names)
cal_results <- setNames(lapply(names, function(name)
  metrics(cal, cal_prob[[name]], thresholds[[name]])), names)
stopifnot(all(vapply(cal_results, function(m)
  m$wrongCandidateFraction <= 0.05 + 1e-10, logical(1))))
# No improvement without a real heldout calibration advantage.
winner <- "centroid"
for (name in c("multinom", "tree")) {
  if (cal_results[[name]]$correctCoverage >
      cal_results[[winner]]$correctCoverage + 1e-5) winner <- name
}

# Reveal test scene exactly once after selection. No test-set retuning.
test_prob <- setNames(lapply(names, pred_prob, data = test), names)
test_results <- setNames(lapply(names, function(name)
  metrics(test, test_prob[[name]], thresholds[[name]])), names)
selected <- test_results[[winner]]
baseline <- test_results[["centroid"]]
report <- list(
  schema = "chibi.lens.real-visual-classifier-eval.v1",
  sourceKind = "real_ycbv_mit_rgb_pixels",
  sourceArchiveSha256 = src,
  featureCSVsha256 = csv_sha,
  scenes = split_scenes, licensed = "MIT",
  trainingFrames = length(unique(paste(train$scene_id, train$frame_id))),
  calibrationFrames = length(unique(paste(cal$scene_id, cal$frame_id))),
  independentTestFrames = length(unique(paste(test$scene_id, test$frame_id))),
  trainExamples = nrow(train), calExamples = nrow(cal), testExamples = nrow(test),
  modeledClasses = as.integer(levels),
  featureProfile = profile,
  featureCount = length(features),
  modelFamilies = names,
  targetCalibrationWrongCandidateFraction = 0.05,
  calibration = cal_results, heldoutTest = test_results,
  selected = winner,
  gainVsCentroidCorrectCoverage = selected$correctCoverage -
      baseline$correctCoverage,
  gainVsCentroidWrongCandidateFraction = selected$wrongCandidateFraction -
      baseline$wrongCandidateFraction,
  qualityClaim = if (winner != "centroid" &&
                     selected$correctCoverage > baseline$correctCoverage &&
                     selected$wrongCandidateFraction <=
                       baseline$wrongCandidateFraction) {
    "EXPLORATORY_REAL_HELDOUT_GAIN"
  } else "NOT_QUALIFIED_FOR_MODEL_PROMOTION",
  limitations = c("Not official BOP benchmark: test images are repurposed for private training + scene split",
                  "Only four YCB object classes, one scene in test split",
                  "Simplified 48 pixel features, no camera glasses data",
                  "Class label is not a unique object identity or access grant"),
  physicalIdentityVerified = FALSE, actionAuthorized = FALSE,
  actualProviderCostEur = NULL, providerAttested = FALSE
)
jsonlite::write_json(report, file.path(out, "training-report.json"),
                     pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 8)
saveRDS(list(multinom = multi, tree = tree, centroids = centroids,
             thresholds = thresholds, selected = winner, features = features,
             sourceArchiveSha256 = src, featureCSVsha256 = csv_sha),
        file.path(out, "trained-models.rds"), compress = "xz")
stopifnot(file.size(file.path(out, "training-report.json")) > 100,
          file.size(file.path(out, "trained-models.rds")) > 100)
cat(jsonlite::toJSON(list(selected = winner, train = nrow(train),
  calibration = nrow(cal), test = nrow(test),
  calibratedWrongCandidate = cal_results[[winner]]$wrongCandidateFraction,
  heldoutCoverage = selected$correctCoverage,
  heldoutWrongCandidate = selected$wrongCandidateFraction,
  baselineCoverage = baseline$correctCoverage,
  quality = report$qualityClaim), auto_unbox = TRUE, null = "null"), "\n")
