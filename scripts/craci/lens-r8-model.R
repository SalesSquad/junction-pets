#!/usr/bin/env Rscript
# Eight independent CRACI CPU/R experiments on REAL licensed YCB-V crops.
# GT scene, labels, visibility and BOP camera are strictly EVALUATION-ONLY.
# This is internal research, not an official BOP leaderboard or wearable model.
suppressPackageStartupMessages(library(nnet))
suppressPackageStartupMessages(library(rpart))
suppressPackageStartupMessages(library(jsonlite))
argv <- commandArgs(trailingOnly = TRUE)
if (length(argv) != 5L) stop("Usage: Rscript lens-r8-model.R DATA.csv ADMISSION.json LANE OUTPUT SOURCE_SHA")
lanes <- c("color-logit","color-balanced","fusion-logit","fusion-balanced",
           "texture-tree","quality-logit","centroid-shrink","consensus-ensemble")
lane <- argv[[3]]
if (!lane %in% lanes) stop("Lane is not preregistered")
pin <- "c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d"
if (!identical(argv[[5]], pin)) stop("Public source ZIP digest mismatch")
out <- argv[[4]]
if (!dir.exists(out)) dir.create(out, recursive=TRUE)
if (length(list.files(out,all.files=FALSE))) stop("Refuse to overwrite model evidence")
admission <- jsonlite::read_json(argv[[2]], simplifyVector=TRUE)
if (!identical(admission$schema,"chibi.lens.real-contrast-source.v1") ||
    !identical(admission$sourceArchiveSha256,pin) ||
    !identical(admission$license,"MIT") ||
    !isTRUE(admission$trainingAllowed) ||
    isTRUE(admission$rawPixelsCloud) ||
    isTRUE(admission$familyOrUserPhotos) ||
    isTRUE(admission$inferenceHasGroundTruthVisibility) ||
    !identical(admission$sourceCropCount,975L)) stop("Source permission or data contract rejected")
csv_hash <- strsplit(system2("sha256sum",shQuote(argv[[1]]),stdout=TRUE),
                     "[[:space:]]+")[[1]][[1]]
if (!identical(csv_hash,admission$csvSha256)) stop("Feature payload source hash mismatch")
data <- read.csv(argv[[1]],stringsAsFactors=FALSE,check.names=FALSE)
fixed_classes <- c("1","3","12")
splits <- list(train=c(48L,49L,51L,54L),cal=55L,test=c(56L,57L,58L))
features_all <- sprintf("f%02d",0:47)
quality_features <- c("brightness","contrast","saturation","edge_strength")
required <- c("source","license","modality","split","scene_id","frame_id",
              "object_id","visible_fraction","bbox_area_fraction",
              "camera_fx","camera_fy",features_all,quality_features)
if (!all(required %in% names(data)) || anyNA(data[required]))
  stop("Missing or NA feature / metadata source")
if (!setequal(unique(data$split),names(splits)) ||
    !all(data$source=="bop-ycbv-mit" & data$license=="MIT" &
         data$modality=="REAL_RGB") ||
    !setequal(unique(as.character(data$object_id)),fixed_classes) ||
    nrow(data)!=975L) stop("Unexpected real image dataset or object classes")
for (s in names(splits)) {
  subset <- data[data$split==s,,drop=FALSE]
  if (!setequal(unique(as.integer(subset$scene_id)),splits[[s]]))
    stop("Scene split provenance drift")
  if (!all(fixed_classes %in% as.character(subset$object_id)))
    stop("Class absent from declared split")
}
if (length(unique(unlist(splits)))!=8) stop("Scene leakage")
stopifnot(all(vapply(data[c(features_all,quality_features)],function(x)
  is.numeric(x) && all(is.finite(x) & x>=0 & x<=1), logical(1))))
if (!all(data$visible_fraction>=0 & data$visible_fraction<=1))
  stop("Ground-truth visibility values malformed")
training <- data[data$split=="train",,drop=FALSE]
calibration <- data[data$split=="cal",,drop=FALSE]
test <- data[data$split=="test",,drop=FALSE]
if (nrow(training)!=525L || nrow(calibration)!=225L || nrow(test)!=225L)
  stop("Expected exact non-overlapping 525/225/225 sample sizes")
for (d in list(training,calibration,test)) {
  if (!setequal(unique(as.character(d$object_id)),fixed_classes)) stop("Unbalanced classes")
}
training$label <- factor(as.character(training$object_id), levels=fixed_classes)
calibration$label <- factor(as.character(calibration$object_id), levels=fixed_classes)
test$label <- factor(as.character(test$object_id), levels=fixed_classes)

color <- sprintf("f%02d",0:23)
texture <- sprintf("f%02d",24:47)
full <- features_all
allowed <- c(features_all,quality_features)
predictors <- switch(lane,
  "color-logit"=color,
  "color-balanced"=color,
  "fusion-logit"=full,
  "fusion-balanced"=full,
  "texture-tree"=texture,
  "quality-logit"=c(full,quality_features),
  "centroid-shrink"=color,
  "consensus-ensemble"=color)
if (!all(predictors %in% allowed) || length(intersect(predictors,
  c("scene_id","object_id","visible_fraction","bbox_area_fraction",
    "camera_fx","camera_fy","frame_id","split")))) {
  stop("Evaluation metadata leaked into predictor set")
}
# Fit normalization on TRAIN only: no camera scene/test lookup or label hint.
transformer <- function(cols) {
  mu <- vapply(training[cols],mean,numeric(1))
  sigma <- vapply(training[cols],sd,numeric(1))
  sigma[!is.finite(sigma) | sigma<1e-6] <- 1
  list(fields=cols,center=mu,scale=sigma)
}
apply_transform <- function(d, norm) {
  values <- as.matrix(d[,norm$fields,drop=FALSE])
  sweep(sweep(values,2,norm$center,"-"),2,norm$scale,"/")
}
norm <- transformer(predictors)
train_x <- apply_transform(training,norm)
cal_x <- apply_transform(calibration,norm)
test_x <- apply_transform(test,norm)
make_df <- function(mat,labels=NULL) {
  df <- as.data.frame(mat)
  names(df) <- paste0("x",seq_len(ncol(mat)))
  if (!is.null(labels)) df$label <- labels
  df
}
train_df <- make_df(train_x,training$label)
cal_df <- make_df(cal_x)
test_df <- make_df(test_x)
set.seed(20261114L + match(lane,lanes)*1009L)

# Same train-only 24-bin centroid reference in every lane. Exact class order.
norm_base <- transformer(color)
baseline_centers <- vapply(fixed_classes,function(label)
  colMeans(apply_transform(training[as.character(training$object_id)==label,,drop=FALSE],
                            norm_base)),numeric(length(color)))
rownames(baseline_centers) <- color
as_prob <- function(scores,expected_n) {
  scores <- as.matrix(scores)
  if (nrow(scores)!=expected_n || ncol(scores)!=length(fixed_classes) ||
      !all(fixed_classes %in% colnames(scores)) ||
      any(!is.finite(scores)) || any(scores<0)) stop("Model class order/shape not trustworthy")
  scores <- scores[,fixed_classes,drop=FALSE]
  if (any(rowSums(scores)<=0)) stop("No probability mass")
  scores/rowSums(scores)
}
softmax <- function(scores) {
  scores <- sweep(scores,1,apply(scores,1,max),"-")
  p <- exp(scores)
  p/rowSums(p)
}
centroid_prob <- function(d, centers,trans,temperature) {
  x <- apply_transform(d,trans)
  distances <- vapply(seq_along(fixed_classes),function(j)
    rowSums(sweep(x,2,centers[,j],"-")^2),numeric(nrow(x)))
  scores <- softmax(-distances/max(temperature,1e-6))
  colnames(scores) <- fixed_classes
  as_prob(scores,nrow(d))
}
base_cal <- centroid_prob(calibration,baseline_centers,norm_base,10)
base_test <- centroid_prob(test,baseline_centers,norm_base,10)

quality_cutoffs <- as.numeric(quantile(training$brightness,c(1/3,2/3),names=FALSE))
quality_bin <- function(data) {
  ifelse(data$brightness<=quality_cutoffs[[1]],"dark",
    ifelse(data$brightness<=quality_cutoffs[[2]],"mid","bright"))
}
calibration_group <- function(scores,d) {
  policy <- if (lane %in% c("color-balanced","fusion-balanced","consensus-ensemble"))
    "class" else if (lane=="quality-logit") "brightness_bin" else "global"
  if (policy=="global") return(rep("all",nrow(scores)))
  if (policy=="brightness_bin") return(quality_bin(d))
  fixed_classes[max.col(scores,ties.method="first")]
}
# Exact empirical risk bound, computed on calibration only and per disjoint
# group. Each group's wrong quota is floor(.05*group_size).
calibrate <- function(scores,data,group) {
  confidence <- apply(scores,1,max)
  predicted <- fixed_classes[max.col(scores,ties.method="first")]
  wrong <- predicted!=as.character(data$label)
  thresholds <- list()
  for (g in sort(unique(group))) {
    where <- group==g
    n <- sum(where)
    errors <- sort(confidence[where & wrong],decreasing=TRUE)
    budget <- floor(.05*n)
    t <- if (length(errors)<=budget) 0 else errors[[budget+1L]]+1e-9
    thresholds[[g]] <- as.numeric(t)
  }
  accepted <- confidence>=vapply(group,function(g) thresholds[[g]],numeric(1))
  if (sum(accepted & wrong)>floor(.05*nrow(scores)))
    stop("Calibration risk budget violated")
  list(thresholds=thresholds,policy=if (length(unique(group))>1) "grouped" else "global",
       accepted=accepted,wrong=wrong,proposed=predicted,confidence=confidence)
}
apply_calibration <- function(scores,data,cal,policy_group) {
  predicted <- fixed_classes[max.col(scores,ties.method="first")]
  confidence <- apply(scores,1,max)
  group <- policy_group(scores,data)
  # Unseen class/quality bin at calibration is NOT permission to predict.
  # Conservative fallback to Inf: fail-closed abstention, no silent sharing.
  accepted <- confidence>=vapply(group,function(g)
    if (g %in% names(cal$thresholds)) cal$thresholds[[g]] else Inf,
    numeric(1))
  list(accepted=accepted,predicted=predicted,confidence=confidence,groups=group)
}
measure <- function(data,policy) {
  truth <- as.character(data$label)
  correct <- policy$predicted==truth
  accepted <- policy$accepted
  wrong <- accepted & !correct
  list(n=nrow(data),accepted=sum(accepted),correctAccepted=sum(accepted & correct),
    wrongAccepted=sum(wrong),abstained=sum(!accepted),
    coverage=as.numeric(mean(accepted & correct)),
    wrongRate=as.numeric(mean(wrong)),
    acceptedPrecision=if (any(accepted)) sum(accepted & correct)/sum(accepted) else NULL,
    top1Accuracy=as.numeric(mean(correct)))
}
base_groups <- function(scores,d) rep("all",nrow(scores))
base_meta <- calibrate(base_cal,calibration,base_groups(base_cal,calibration))
base_cal_policy <- apply_calibration(base_cal,calibration,base_meta,base_groups)
base_test_policy <- apply_calibration(base_test,test,base_meta,base_groups)
base_cal_result <- measure(calibration,base_cal_policy)
base_test_result <- measure(test,base_test_policy)

decays <- c(0.001,0.015,0.075)
parameters <- if (lane=="texture-tree") c(0.001,0.008,0.03) else if (
  lane=="centroid-shrink") c(4,10,20) else if (lane=="consensus-ensemble")
  c(0.25,0.50,0.75) else decays
trained <- list(); candidates <- list()
class_counts <- table(training$label)
balanced_weights <- 1/as.numeric(class_counts[as.character(training$label)])
balanced_weights <- balanced_weights/mean(balanced_weights)

for (index in seq_along(parameters)) {
  value <- parameters[[index]]
  model_name <- paste0("candidate",index)
  model <- NULL
  score_predict <- NULL
  if (lane=="centroid-shrink") {
    centers <- vapply(fixed_classes,function(label)
      colMeans(train_x[as.character(training$label)==label,,drop=FALSE]),
      numeric(ncol(train_x)))
    rownames(centers) <- predictors
    model <- list(kind="trained_prototypes",centers=centers,temperature=value,
                  normalization=norm)
    score_predict <- function(data) centroid_prob(data,centers,norm,value)
  } else if (lane=="texture-tree") {
    f <- as.formula(paste("label ~",paste(names(train_df)[names(train_df)!="label"],collapse="+")))
    model <- rpart::rpart(f,data=train_df,method="class",
      control=rpart.control(cp=value,maxdepth=7,minsplit=20,minbucket=8,xval=0))
    score_predict <- function(data) {
      design <- make_df(apply_transform(data,norm))
      as_prob(predict(model,newdata=design,type="prob"),nrow(data))
    }
  } else {
    multinom_data <- train_df
    f <- as.formula(paste("label ~",paste(names(train_df)[names(train_df)!="label"],collapse="+")))
    decay <- if (lane=="consensus-ensemble") 0.015 else value
    model <- suppressWarnings(nnet::multinom(f,data=multinom_data,
      weights=if (grepl("balanced",lane)) balanced_weights else rep(1,nrow(training)),
      decay=decay,maxit=130,MaxNWts=8000,trace=FALSE))
    score_predict <- function(data) {
      design <- make_df(apply_transform(data,norm))
      probs <- as_prob(predict(model,newdata=design,type="probs"),nrow(data))
      if (lane=="consensus-ensemble")
        probs <- as_prob(value*probs+(1-value)*centroid_prob(data,baseline_centers,norm_base,10),
                         nrow(data))
      probs
    }
  }
  score_cal <- score_predict(calibration)
  group <- function(scores,d) calibration_group(scores,d)
  cal_meta <- calibrate(score_cal,calibration,group(score_cal,calibration))
  cal_policy <- apply_calibration(score_cal,calibration,cal_meta,group)
  m <- measure(calibration,cal_policy)
  if (m$wrongRate>.05+1e-10) stop("Model calibration exceeds pre-registered risk")
  candidates[[index]] <- list(index=index,parameter=value,
    calibrated=m,thresholds=cal_meta$thresholds)
  trained[[index]] <- list(model=model,normalization=norm,parameter=value,
                          thresholdPolicy=cal_meta$policy,calibratedThresholds=cal_meta$thresholds)
}
cal_cover <- vapply(candidates,function(c) c$calibrated$coverage,numeric(1))
cal_risk <- vapply(candidates,function(c) c$calibrated$wrongRate,numeric(1))
which_best <- order(-cal_cover,cal_risk,seq_along(candidates))[[1]]
# Freeze model and its calibrated thresholds before reading the separate test
# (all candidate variants have been selected using calibration ONLY).
chosen <- trained[[which_best]]
chosen_index <- which_best
chosen_parameter <- chosen$parameter
selected_scores <- NULL
if (lane=="centroid-shrink") {
  selected_scores <- centroid_prob(test,chosen$model$centers,norm,chosen_parameter)
} else if (lane=="texture-tree") {
  selected_scores <- as_prob(predict(chosen$model,
    newdata=test_df,type="prob"),nrow(test))
} else {
  scores <- as_prob(predict(chosen$model,newdata=test_df,type="probs"),nrow(test))
  selected_scores <- if(lane=="consensus-ensemble") as_prob(
    chosen_parameter*scores+(1-chosen_parameter)*base_test,nrow(test)) else scores
}
test_policy <- apply_calibration(selected_scores,test,
  list(thresholds=chosen$calibratedThresholds),calibration_group)
test_result <- measure(test,test_policy)
baseline_delta <- test_result$coverage-base_test_result$coverage

group_report <- function(category,group_values) {
  groups <- split(seq_len(nrow(test)),group_values)
  lapply(names(groups),function(g) {
    rows <- groups[[g]]
    m <- measure(test[rows,,drop=FALSE],list(
      predicted=test_policy$predicted[rows],accepted=test_policy$accepted[rows]))
    list(category=category,group=g,metrics=m)
  })
}
metadata_slices <- c(
  group_report("scene",as.character(test$scene_id)),
  group_report("object_class",as.character(test$object_id)),
  group_report("pixel_brightness",quality_bin(test)),
  group_report("GT_visibility_evaluation_only",
    ifelse(test$visible_fraction<.8,"occluded","mostly_visible")),
  group_report("GT_box_size_evaluation_only",
    ifelse(test$bbox_area_fraction<.02,"small","large")))
by_scene <- Filter(function(x)x$category=="scene",metadata_slices)
scene_safe <- all(vapply(by_scene,function(x)x$metrics$wrongRate<=.05+1e-10,logical(1)))
claim <- if (test_result$coverage>base_test_result$coverage &&
             test_result$wrongRate<=.05+1e-10 &&
             test_result$wrongRate<=base_test_result$wrongRate+1e-10 &&
             scene_safe) "EXPLORATORY_SCENE_CONSTRAINED_GAIN" else "NO_SAFE_PROMOTION"
report <- list(
  schema="chibi.lens.r8.meta-tournament.v1",arm=lane,
  dataArchiveSHA256=pin,dataCSVSHA256=csv_hash,
  realObjectClasses=as.integer(fixed_classes),
  sourceKind="REAL_RGB_PUBLIC_YCBV_MIT",
  predictorNames=predictors,predictorCount=length(predictors),
  metadataGuard="scene/camera/GT visibility/GT box annotations used for audit only",
  modelVariantsTrained=length(trained),selectedVariant=chosen_index,
  selectedParameter=chosen_parameter,
  trainExamples=nrow(training),calibrationExamples=nrow(calibration),
  testExamples=nrow(test),trainScenes=splits$train,calibrationScenes=splits$cal,
  testScenes=splits$test,
  calibrationTrials=candidates,
  baselineCalibration=base_cal_result,
  baselineHeldout=base_test_result,
  selectedCalibration=candidates[[which_best]]$calibrated,
  selectedHeldout=test_result,
  heldoutCorrectCoverageDelta=baseline_delta,
  heldoutMetadataSlices=metadata_slices,
  worstSceneWrongRate=max(vapply(by_scene,function(x)x$metrics$wrongRate,numeric(1))),
  qualifiedSourceScoped=claim,
  multipleHypotheses="Eight pre-registered arms; no multiple-testing-adjusted winner selected",
  heldoutAlreadyPublicBenchmark=TRUE,
  priorSourceContextOverlap=TRUE,
  officialBOPLeaderboardScore=FALSE,
  actualWearableCamera=FALSE,physicalIdentityVerified=FALSE,
  toolAuthorizationGranted=FALSE,actualCRACIBillingEUR=NULL,
  risks=c("Only three labels, classes confounded with each final test scene",
    "Initial annotated boxes are not a detector; no real-user camera capture",
    "Empirical calibration on one physical scene is not a distribution-free FPR guarantee",
    "No product deployment without more independent scenes and verified field review")
)
jsonlite::write_json(report,file.path(out,"training-report.json"),
  auto_unbox=TRUE,pretty=TRUE,null="null",digits=8)
saveRDS(list(arm=lane,classes=fixed_classes,selected=chosen,
    candidates=trained,baselineCenters=baseline_centers,
    baselineNormalizer=norm_base,predictorNames=predictors,
    actualDataSHA256=csv_hash,qualityCutoffs=quality_cutoffs),
    file.path(out,"trained-models.rds"),compress="xz")
stopifnot(file.size(file.path(out,"training-report.json"))>100,
          file.size(file.path(out,"trained-models.rds"))>100)
cat(jsonlite::toJSON(list(arm=lane,selectedVariant=which_best,
  calCoverage=candidates[[which_best]]$calibrated$coverage,
  testCoverage=test_result$coverage,testWrong=test_result$wrongAccepted,
  baselineCoverage=base_test_result$coverage,
  qualified=claim),auto_unbox=TRUE,null="null"),"\n")
