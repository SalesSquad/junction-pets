#!/usr/bin/env Rscript
# Three distinct CPU/R methods for Chibi Lens failure analysis.
# Real public BOP YCB-V numeric pixels only; scene-heldout results are POSTHOC
# diagnostics because the same fixed BOP footage has already been examined.
# No production promotion, physical identity verification or consent grant.
suppressPackageStartupMessages(library(nnet))
suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=5L) stop("Usage: Rscript lens-r3-methods.R DATA.csv ADMISSION.json ARM OUTPUT SOURCE_SHA")
allowed_arms <- c("risk-upper","metadata-shield","hard-negative")
arm <- args[[3]]
if (!arm %in% allowed_arms) stop("Unknown R3 method")
pin <- "c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d"
csv_pin <- "a6d1ca17664544645a3fc26a7d8d9caba6c1d85b58bea00afc0125e991b9a015"
if (!identical(args[[5]],pin)) stop("BOP public archive SHA mismatch")
output <- args[[4]]
if (!dir.exists(output)) dir.create(output,recursive=TRUE)
if (length(list.files(output,all.files=FALSE))) stop("Output must be empty, no overwrite")
admission <- jsonlite::read_json(args[[2]],simplifyVector=TRUE)
if (!identical(admission$schema,"chibi.lens.real-contrast-source.v1") ||
    !identical(admission$license,"MIT") ||
    !identical(admission$sourceArchiveSha256,pin) ||
    !identical(admission$csvSha256,csv_pin) ||
    !isTRUE(admission$trainingAllowed) ||
    isTRUE(admission$familyOrUserPhotos) || isTRUE(admission$rawPixelsCloud) ||
    isTRUE(admission$inferenceHasGroundTruthVisibility))
  stop("Unapproved public source / private data risk")
digest <- strsplit(system2("sha256sum",shQuote(args[[1]]),stdout=TRUE),
                   "[[:space:]]+")[[1]][[1]]
if (!identical(digest,csv_pin)) stop("Unpinned numeric feature bytes")
data <- read.csv(args[[1]],stringsAsFactors=FALSE,check.names=FALSE)
class_names <- c("1","3","12")
pix <- sprintf("f%02d",0:47)
color <- sprintf("f%02d",0:23)
quality <- c("brightness","contrast","saturation","edge_strength")
inputs <- c(pix,quality)
fields <- c("source","license","modality","split","scene_id","frame_id",
            "object_id","visible_fraction","bbox_area_fraction",
            "camera_fx","camera_fy",inputs)
if (!all(fields %in% names(data)) || anyNA(data[fields]))
  stop("Feature schema absent or NA")
if (nrow(data)!=975L || !setequal(as.character(unique(data$object_id)),class_names) ||
    any(!data$split %in% c("train","cal","test")) ||
    !all(data$source=="bop-ycbv-mit" & data$license=="MIT" &
         data$modality=="REAL_RGB") ||
    !all(vapply(data[inputs],function(x)is.numeric(x)&&all(is.finite(x)&x>=0&x<=1),logical(1))))
  stop("Untrusted public numeric dataset")
scene_split <- list(train=c(48L,49L,51L,54L),cal=55L,test=c(56L,57L,58L))
for (split in names(scene_split)) {
  sample <- data[data$split==split,,drop=FALSE]
  if (!setequal(as.integer(unique(sample$scene_id)),scene_split[[split]]) ||
      !setequal(as.character(unique(sample$object_id)),class_names))
    stop("Object labels / scene split drift")
}
if (length(unique(unlist(scene_split)))!=8L) stop("Source split overlap")
train <- data[data$split=="train",,drop=FALSE]
cal <- data[data$split=="cal",,drop=FALSE]
test <- data[data$split=="test",,drop=FALSE]
if (nrow(train)!=525L||nrow(cal)!=225L||nrow(test)!=225L)
  stop("Wrong train/cal/test sample counts")

set.seed(20261114L+match(arm,allowed_arms)*101L)
# Train-only normalization; no scene/GT/camera/visibility features allowed.
train_model <- function(rows, predictors, decay, weights=NULL, seed=271828L) {
  forbidden <- c("source","license","split","scene_id","frame_id","object_id",
                 "visible_fraction","bbox_area_fraction","camera_fx","camera_fy")
  if (!all(predictors %in% inputs) || any(predictors %in% forbidden))
    stop("Metadata target leakage")
  center <- vapply(rows[predictors],mean,numeric(1))
  scale <- vapply(rows[predictors],sd,numeric(1))
  scale[!is.finite(scale)|scale<1e-6]<-1
  normalized <- sweep(sweep(as.matrix(rows[,predictors,drop=FALSE]),
                            2,center,"-"),2,scale,"/")
  design <- as.data.frame(normalized)
  names(design)<-sprintf("x%02d",seq_len(ncol(design)))
  design$label <- factor(as.character(rows$object_id),levels=class_names)
  if (!setequal(as.character(unique(rows$object_id)),class_names))
    stop("Fold does not represent every object class")
  if (is.null(weights)) weights <- rep(1,nrow(rows))
  if (length(weights)!=nrow(rows) || any(!is.finite(weights)|weights<=0))
    stop("Invalid training weights")
  model <- suppressWarnings(nnet::multinom(label~.,data=design,
      weights=weights,decay=decay,maxit=150,MaxNWts=8000,trace=FALSE))
  list(model=model,predictors=predictors,center=center,scale=scale,
       trainingSeed=seed,decay=decay)
}
score <- function(fitted, rows) {
  x<-sweep(sweep(as.matrix(rows[,fitted$predictors,drop=FALSE]),
                  2,fitted$center,"-"),2,fitted$scale,"/")
  newdata<-as.data.frame(x)
  names(newdata)<-sprintf("x%02d",seq_len(ncol(newdata)))
  y<-as.matrix(predict(fitted$model,newdata=newdata,type="probs"))
  if (nrow(y)!=nrow(rows)||ncol(y)!=length(class_names)||
      !setequal(colnames(y),class_names)||any(!is.finite(y))||any(y<0)||
      any(rowSums(y)<=0))
    stop("Untrustworthy model class order or prediction probabilities")
  y <- y[,class_names,drop=FALSE]
  y/rowSums(y)
}
which_class <- function(probs) class_names[max.col(probs,ties.method="first")]
confidence <- function(probs) apply(probs,1,max)
summarize <- function(rows,probs,accept) {
  truth <- as.character(rows$object_id)
  proposed <- which_class(probs)
  wrong <- accept & proposed!=truth
  correct <- accept & proposed==truth
  list(cases=nrow(rows),accepted=sum(accept),wrongAccepted=sum(wrong),
       correctAccepted=sum(correct),abstained=sum(!accept),
       wrongRate=as.numeric(mean(wrong)),coverage=as.numeric(mean(correct)),
       rawTop1=as.numeric(mean(proposed==truth)),
       acceptedPrecision=if(any(accept))sum(correct)/sum(accept) else NULL)
}
calibrate_empirical <- function(rows,probs,allowed=rep(TRUE,nrow(rows))) {
  preds<-which_class(probs)
  conf<-confidence(probs)
  incorrect<-preds!=as.character(rows$object_id) & allowed
  errors<-sort(conf[incorrect],decreasing=TRUE)
  k<-floor(.05*nrow(rows))
  threshold<-if(length(errors)<=k) 0 else errors[[k+1L]]+1e-10
  if(threshold>1) threshold<-Inf
  threshold
}
# Same frozen train-only color model in all three experiments: no test-driven
# baseline retraining. Baseline threshold from calibration ONLY.
baseline<-train_model(train,color,0.015)
base_cal_probs<-score(baseline,cal)
base_test_probs<-score(baseline,test)
base_threshold<-calibrate_empirical(cal,base_cal_probs)
base_cal_accept<-confidence(base_cal_probs)>=base_threshold
base_test_accept<-confidence(base_test_probs)>=base_threshold
baseline_cal<-summarize(cal,base_cal_probs,base_cal_accept)
baseline_test<-summarize(test,base_test_probs,base_test_accept)
if (baseline_cal$wrongRate > .0500001) stop("Base calibration gate invalid")
parameters<-list()
notes<-list()
fitted<-NULL
cal_probs<-NULL
test_probs<-NULL
cal_accept<-NULL
test_accept<-NULL

if (arm=="risk-upper") {
  # Idea 1: learn one model, then class-conditional *exact* one-sided 95%
  # Clopper-Pearson bound on misaccepted candidates; not an IID guarantee
  # under camera/scene distribution shift.
  fitted<-baseline
  cal_probs<-base_cal_probs
  test_probs<-base_test_probs
  fit_thresholds<-list()
  diagnostics<-list()
  for (cl in class_names) {
    ix<-which(which_class(cal_probs)==cl)
    if (!length(ix)) {
      fit_thresholds[[cl]]<-Inf
      diagnostics[[cl]]<-list(calAccepted=0,calWrong=0,upper95=1)
      next
    }
    conf<-confidence(cal_probs)[ix]
    truth<-as.character(cal$object_id)[ix]
    candidates<-sort(unique(c(0,seq(.50,.99,by=.01),1,Inf)))
    selected_t<-Inf
    best_correct<--1L
    best_wrong<-Inf
    best_ub<-1
    for(t in candidates) {
      admitted<-conf>=t
      n<-sum(admitted)
      wrong<-sum(admitted & truth!=cl)
      # 0 accepted is never scientific evidence of low error.
      upper<-if(n==0 || wrong==n) 1 else qbeta(.95,wrong+1,n-wrong)
      if(upper<=.05 && (sum(admitted & truth==cl)>best_correct ||
         (sum(admitted & truth==cl)==best_correct && wrong<best_wrong))) {
        selected_t<-t
        best_correct<-sum(admitted & truth==cl)
        best_wrong<-wrong
        best_ub<-upper
      }
    }
    fit_thresholds[[cl]]<-selected_t
    diagnostics[[cl]]<-list(calAccepted=if(is.finite(selected_t))
       sum(conf>=selected_t) else 0,
       calWrong=if(is.finite(selected_t))sum(conf>=selected_t & truth!=cl) else 0,
       upper95=best_ub)
  }
  accept_with_bounds<-function(probs){
    cl<-which_class(probs); conf<-confidence(probs)
    conf>=vapply(cl,function(x) fit_thresholds[[x]],numeric(1))
  }
  cal_accept<-accept_with_bounds(cal_probs)
  test_accept<-accept_with_bounds(test_probs)
  parameters<-list(perClassThresholds=fit_thresholds,
                   exactOneSided95CalibrationBound=diagnostics,
                   alpha=.05,targetIncorrect=.05)
  notes<-list(method="Class-conditional exact binomial upper-confidence risk shield",
              limitation="Exact bound is valid only under IID calibration, not scene shift")
} else if (arm=="metadata-shield") {
  # Idea 2: use ONLY camera-observable pixel quality for a train-only robust
  # quadratic-distance drift detector, cutoff learned on calibration (unlabeled).
  fields<-c(color,quality)
  fitted<-train_model(train,fields,.015)
  cal_probs<-score(fitted,cal)
  test_probs<-score(fitted,test)
  qtrain<-as.matrix(train[,quality,drop=FALSE])
  mu<-colMeans(qtrain)
  sdq<-apply(qtrain,2,sd)
  sdq[sdq<1e-6]<-1
  ztrain<-sweep(sweep(qtrain,2,mu,"-"),2,sdq,"/")
  covariance<-cov(ztrain)+diag(.25,ncol(ztrain))
  inv_cov<-solve(covariance)
  ood<-function(rows){
    q<-as.matrix(rows[,quality,drop=FALSE])
    z<-sweep(sweep(q,2,mu,"-"),2,sdq,"/")
    as.numeric(rowSums((z%*%inv_cov)*z))
  }
  cal_distance<-ood(cal)
  limit<-as.numeric(quantile(cal_distance,.90,names=FALSE,type=1))
  if(!is.finite(limit)) stop("OOD drift cutoff invalid")
  keep_cal<-cal_distance<=limit
  threshold<-calibrate_empirical(cal,cal_probs,keep_cal)
  cal_accept<-(confidence(cal_probs)>=threshold)&keep_cal
  test_distance<-ood(test)
  keep_test<-test_distance<=limit
  test_accept<-(confidence(test_probs)>=threshold)&keep_test
  parameters<-list(
    qualityOnlyPredictors=quality,trainMean=as.list(mu),trainSD=as.list(sdq),
    trainCovarianceRidge=.25,unlabeledCalibrationQuantile=.90,
    calibrationOODThreshold=limit,calibrationConfidenceThreshold=threshold,
    calibrationBlockedOOD=sum(!keep_cal),testBlockedOOD=sum(!keep_test),
    testBlockedOriginalBaselineErrors=sum(!keep_test &
      base_test_accept & which_class(base_test_probs)!=as.character(test$object_id)))
  notes<-list(method="Train-only Mahalanobis pixel-quality drift shield",
              limitation="Histogram and quality drift cannot establish true object identity")
} else if (arm=="hard-negative") {
  # Idea 3: four *scene-heldout* OOF models within TRAIN only, mine their
  # confidently mistaken proposals, weight them in a final robust R classifier.
  # Never use calibration/test labels to decide hardness.
  predict_oof<-matrix(NA_real_,nrow(train),length(class_names))
  colnames(predict_oof)<-class_names
  fold_reports<-list()
  for(scene in sort(unique(train$scene_id))){
    withheld<-which(train$scene_id==scene)
    other<-which(train$scene_id!=scene)
    heldfit<-train_model(train[other,,drop=FALSE],color,.015)
    predict_oof[withheld,]<-score(heldfit,train[withheld,,drop=FALSE])
    fold_reports[[as.character(scene)]]<-list(
      heldoutScene=as.integer(scene),cases=length(withheld),
      trainClasses=sort(unique(as.character(train$object_id[other]))))
  }
  if(anyNA(predict_oof)) stop("Train-only scene folds incomplete")
  pred<-which_class(predict_oof)
  conf<-confidence(predict_oof)
  truth<-as.character(train$object_id)
  hard<-(pred!=truth & conf>=.50)
  ambiguous<-(pred==truth & conf<.70)
  hard_weight<-ifelse(hard,4,ifelse(ambiguous,2,1))
  # Cap empirical weighting; don't manufacture minority-class labels.
  hard_weight<-hard_weight/mean(hard_weight)
  candidate_params<-c(.003,.015,.06)
  fits<-lapply(candidate_params,function(decay)
    train_model(train,color,decay,weights=hard_weight))
  cals<-lapply(fits,function(m)score(m,cal))
  cal_mets<-lapply(cals,function(p){
    t<-calibrate_empirical(cal,p)
    summarize(cal,p,confidence(p)>=t)
  })
  # Validation ONLY selection, no test use for candidate tuning:
  # baseline remains selected if none beats its calibration coverage at
  # equal/lower wrong accepted rate.
  admitted<-which(vapply(cal_mets,function(m)
    m$coverage>baseline_cal$coverage+1e-9 &&
    m$wrongAccepted<=baseline_cal$wrongAccepted,logical(1)))
  choice<-if(length(admitted)) admitted[[order(
    -vapply(cal_mets[admitted],function(m)m$coverage,numeric(1)),
    vapply(cal_mets[admitted],function(m)m$wrongAccepted,numeric(1))) [[1]]]] else 0L
  fitted<-if(choice)fits[[choice]] else baseline
  cal_probs<-if(choice)cals[[choice]] else base_cal_probs
  test_probs<-score(fitted,test)
  threshold<-calibrate_empirical(cal,cal_probs)
  cal_accept<-confidence(cal_probs)>=threshold
  test_accept<-confidence(test_probs)>=threshold
  parameters<-list(trainOnlyFoldReports=fold_reports,
       hardIncorrectCount=sum(hard),ambiguousCount=sum(ambiguous),
       trainOnlyHardnessWeightMax=4,
       candidateDecays=candidate_params,chosenVariant=choice,
       validationCandidates=cal_mets,globalCalibrationThreshold=threshold)
  notes<-list(method="Train-scene cross-fit hard-negative mining with bounded upweight",
              limitation="Teacher already predicts full train labels; hard mining label truth never crosses train split")
}
selected_cal<-summarize(cal,cal_probs,cal_accept)
selected_test<-summarize(test,test_probs,test_accept)
if(selected_cal$wrongRate>.05000001) stop("Selected calibration violated 5% empirical constraint")

posthoc_slices<-function(dim, values) {
  out<-list()
  for(group in sort(unique(values))){
    ix<-which(values==group)
    out[[as.character(group)]]<-summarize(test[ix,,drop=FALSE],
           test_probs[ix,,drop=FALSE],test_accept[ix])
  }
  list(dimension=dim,groups=out)
}
scene_slices<-posthoc_slices("source_scene",test$scene_id)
class_slices<-posthoc_slices("ground_truth_class_evaluation_only",test$object_id)
quality_bins<-ifelse(test$brightness<.33,"dark",
                     ifelse(test$brightness<.67,"mid","bright"))
quality_slices<-posthoc_slices("observable_brightness",quality_bins)
worst_scene_wrong<-max(vapply(scene_slices$groups,function(m)m$wrongRate,numeric(1)))
strict_candidate <- selected_test$wrongRate<=.05 &&
                    worst_scene_wrong<=.05 &&
                    selected_test$wrongAccepted<=baseline_test$wrongAccepted &&
                    selected_test$coverage>baseline_test$coverage
# A posthoc revisit on already-seen fixed scene cannot promote a model,
# even if the descriptive strict metrics happen to be met.
report<-list(schema="chibi.lens.r3.improvement-study.v1",
    workId="CHIBI-LENS-R3-IMPROVEMENTS-20261114",method=arm,
    sourceArchiveSHA256=pin,featureCSVsha256=csv_pin,
    dataKind="PUBLIC_REAL_YCBV_RGB_DERIVED_NUMERIC",
    objectClasses=as.integer(class_names),trainScenes=scene_split$train,
    calibrationScenes=scene_split$cal,testScenes=scene_split$test,
    trainCases=nrow(train),calibrationCases=nrow(cal),testCases=nrow(test),
    calibrationWrongTarget=.05,modelFitted=TRUE,
    baselineCalibration=baseline_cal,baselineHeldout=baseline_test,
    selectedCalibration=selected_cal,selectedHeldout=selected_test,
    metadataSlices=list(scene=scene_slices,sourceClass=class_slices,
                        brightness=quality_slices),
    methodDetails=parameters,methodNotes=notes,
    wouldPassDescriptiveStrictGate=strict_candidate,
    qualifiesForDeployment=FALSE,
    scientificQualification="POSTHOC_EXPLORATORY_ONLY_SAME_PRIOR_BOP_SCENES",
    learningLeakageControls="No test labels in training or calibration; source scene/GT visibility are audit-only",
    correctCoverageDifference=selected_test$coverage-baseline_test$coverage,
    wrongRateDifference=selected_test$wrongRate-baseline_test$wrongRate,
    realWearableGlassesTrained=FALSE,physicalIdentityVerified=FALSE,
    toolAuthorizationGranted=FALSE,
    actualProviderBilling=NULL,providerSignedAttestation=FALSE)
jsonlite::write_json(report,file.path(output,"training-report.json"),
   pretty=TRUE,auto_unbox=TRUE,null="null",digits=8)
saveRDS(list(method=arm,model=fitted,modelDetails=parameters,
             baseline=baseline,sourceArchive=pin,featureCSVsha=csv_pin),
        file.path(output,"trained-models.rds"),compress="xz")
stopifnot(file.size(file.path(output,"training-report.json"))>100,
          file.size(file.path(output,"trained-models.rds"))>100)
cat(jsonlite::toJSON(list(method=arm,selectedCorrect=selected_test$correctAccepted,
   selectedWrong=selected_test$wrongAccepted,selectedAbstained=selected_test$abstained,
   baselineWrong=baseline_test$wrongAccepted,baselineCorrect=baseline_test$correctAccepted,
   posthocStrictGate=strict_candidate,deployable=FALSE),
   auto_unbox=TRUE,null="null"),"\n")
