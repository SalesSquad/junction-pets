#!/usr/bin/env Rscript
# Independent REAL-camera HB scene experiment for Chibi Lens.
# TRAIN objects 12/15 in TWO scenes, CAL scene10, FINAL test scene11.
# Unknown objects 3/22/23 only in calibration/test (open-set challenge).
# Use frozen Apple Vision FeaturePrint v2 (768 dims) vs colour histogram.
# No source scene, label, mask, bbox or private OCR in predictors.
suppressPackageStartupMessages(library(nnet))
suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=5L) {
  stop("Usage: Rscript lens_hb_r_train.R FEATURES.csv ADMISSION.json ARM OUT ARCHIVE_POINTER_SHA")
}
ARM <- args[[3]]
ARMS <- c("color","vision_prototype","vision_pca","vision_guard")
if (!ARM %in% ARMS) stop("Unregistered model family")
ARCHIVE <- "8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
CSV_SHA <- "2540595932867db80e1313dc011640b901c53b16a4f3f897b9d13e32d0c57363"
if (!identical(args[[5]], ARCHIVE)) stop("Unpinned public dataset pointer")
dest <- args[[4]]
if (!dir.exists(dest)) dir.create(dest,recursive=TRUE)
if (length(list.files(dest,all.files=FALSE))) stop("Refuse overwrite existing model evidence")
admission <- jsonlite::read_json(args[[2]],simplifyVector=TRUE)
if (admission$schema!="chibi.lens.hb.real-feature-admission.v1" ||
    admission$sourceLicense!="CC0-1.0" ||
    admission$sourceArchivePointerSHA256!=ARCHIVE ||
    admission$numericCSVsha256!=CSV_SHA ||
    admission$featureExtractor!="VNGenerateImageFeaturePrintRequest" ||
    admission$revision!=2 || admission$vectorDimension!=768 ||
    admission$rawPixelsInCloud!=FALSE ||
    admission$privatePersonalMediaUsed!=FALSE ||
    admission$childOrFamilyMediaUsed!=FALSE ||
    admission$personalOCRUsed!=FALSE ||
    admission$backgroundMaskedBeforeEmbedding!=TRUE ||
    admission$allKnownClassesInAllScenes!=TRUE ||
    admission$realWearableEvaluation!=FALSE ||
    admission$physicalIdentityVerified!=FALSE ||
    admission$actionAuthorized!=FALSE)
  stop("Public/Apple Vision model admission or privacy assertion violated")
source_hash <- strsplit(system2("sha256sum",shQuote(args[[1]]),stdout=TRUE),
                        "[[:space:]]+")[[1]][[1]]
if (!identical(source_hash,CSV_SHA)) stop("Source data changed")

data <- read.csv(args[[1]],stringsAsFactors=FALSE,check.names=FALSE)
COL <- sprintf("c%02d",0:47)
VISION <- sprintf("v%03d",0:767)
required <- c("source","license","modality","split","scene_id","frame_id",
              "object_id","label","known_class",COL,VISION)
if (!all(required %in% colnames(data)) || anyNA(data[required]) ||
    nrow(data)!=655L)
  stop("Source feature data incomplete")
if (!all(data$source=="bop-hb-val-primesense-public-cc0") ||
    !all(data$license=="CC0-1.0") ||
    !all(data$modality=="REAL_RGB_MASKED") ||
    !setequal(unique(data$split),c("train","cal","test")) ||
    !all(vapply(data[c(COL,VISION)],function(x)
         is.numeric(x) && all(is.finite(x)), logical(1))))
  stop("Mixed private, synthetic or malformed feature data")
if (!all(as.matrix(data[,COL,drop=FALSE])>=0 &
         as.matrix(data[,COL,drop=FALSE])<=1))
  stop("Invalid public color histograms")
SCENES <- list(train=c(5L,9L),cal=10L,test=11L)
for (split in names(SCENES)) {
  items <- data[data$split==split,,drop=FALSE]
  if (!setequal(as.integer(unique(items$scene_id)),SCENES[[split]]))
    stop("Physical scene mismatch / leakage")
}
if (!setequal(unique(data$label),c("12","15","UNKNOWN")) ||
    !setequal(unique(data$object_id),c(3L,12L,15L,22L,23L)))
  stop("Object/hard-negative labels changed")
known_truth <- function(x) x %in% c("12","15")
if (any(tolower(as.character(data$known_class)) !=
         ifelse(known_truth(data$label),"true","false")) ||
    any(data$split=="train" & !known_truth(data$label)))
  stop("Unknown objects leaked into known-class training")
train <- data[data$split=="train",,drop=FALSE]
cal <- data[data$split=="cal",,drop=FALSE]
test <- data[data$split=="test",,drop=FALSE]
if (nrow(train)!=186L || nrow(cal)!=234L || nrow(test)!=235L)
  stop("Exact class and scene sample sizes changed")
if (!setequal(unique(train$label),c("12","15")) ||
    !setequal(unique(cal$label),c("12","15","UNKNOWN")) ||
    !setequal(unique(test$label),c("12","15","UNKNOWN")))
  stop("Ground truth missing from one partition")
if (nrow(unique(data.frame(scene=data$scene_id,frame=data$frame_id)))==0)
  stop("Missing real camera frames")
for (sc in c(5L,9L,10L,11L)) {
  if (length(unique(data$frame_id[data$scene_id==sc]))!=48L)
    stop("Incorrect independent source group count")
}
# Prevent reuse of same frame/crop between scenes and partitions.
if (anyDuplicated(data$row_id) ||
    !all(c(5L,9L)%in%train$scene_id) ||
    !all(cal$scene_id==10L) || !all(test$scene_id==11L))
  stop("Source split IDs inconsistent")

train_color <- as.matrix(train[,COL,drop=FALSE])
train_v <- as.matrix(train[,VISION,drop=FALSE])
cal_color <- as.matrix(cal[,COL,drop=FALSE])
test_color <- as.matrix(test[,COL,drop=FALSE])
cal_v <- as.matrix(cal[,VISION,drop=FALSE])
test_v <- as.matrix(test[,VISION,drop=FALSE])
# Apple Vision representation is L2-normalized by source producer.
for (x in list(train_v,cal_v,test_v)) {
  norm <- sqrt(rowSums(x*x))
  if (any(abs(norm-1)>0.0003)) stop("Vision vector is not L2-normalized")
}
set.seed(20261114L)
classes <- c("12","15")

# Train-only scaling for low-dimensional color; no scenes/metadata labels.
fit_scaler <- function(x) {
  center <- colMeans(x)
  std <- apply(x,2,sd)
  std[!is.finite(std)|std<1e-8] <- 1
  list(center=center,scale=std)
}
scale_x <- function(x,f) sweep(sweep(x,2,f$center,"-"),2,f$scale,"/")
color_scaler <- fit_scaler(train_color)
make_df <- function(x,label=NULL) {
  ans<-as.data.frame(x)
  names(ans)<-sprintf("x%03d",seq_len(ncol(x)))
  if (!is.null(label))
    ans$label<-factor(label,levels=classes)
  ans
}
fit_multinom <- function(training_x,decay) {
  if (nrow(training_x)!=nrow(train)) stop("Training feature row count changed")
  model<-suppressWarnings(nnet::multinom(label~.,
    data=make_df(training_x,train$label),maxit=160,
    MaxNWts=20000,decay=decay,trace=FALSE))
  model
}
predict_prob15 <- function(model,x) {
  raw<-predict(model,newdata=make_df(x),type="probs")
  if (is.matrix(raw)) {
    if (!("15" %in% colnames(raw)))stop("Binary model class order mismatch")
    p<-as.numeric(raw[,"15"])
  } else p<-as.numeric(raw)
  if (length(p)!=nrow(x) || any(!is.finite(p)) || any(p<0 | p>1))
    stop("Model probability invalid")
  p
}
# Reference baseline fixed across all four hosted cells.
baseline_model <- fit_multinom(scale_x(train_color,color_scaler),.05)
baseline_cal <- predict_prob15(baseline_model,scale_x(cal_color,color_scaler))
baseline_test <- predict_prob15(baseline_model,scale_x(test_color,color_scaler))

# A training-only prototype family can refuse unknown objects using an
# absolute cosine similarity gate, not just an overconfident softmax margin.
proto <- vapply(classes,function(label)colMeans(train_v[train$label==label,,drop=FALSE]),
                numeric(ncol(train_v)))
proto <- sweep(proto,2,sqrt(colSums(proto*proto)),"/")
colnames(proto)<-classes
cosine <- function(v) {
  z<-v%*%proto
  colnames(z)<-classes
  if (!all(is.finite(z)))stop("Invalid featurePrint cosine")
  z
}
train_cos<-cosine(train_v)
cal_cos<-cosine(cal_v)
test_cos<-cosine(test_v)
max_similarity<-function(z) apply(z,1,max)
min_train_sim <- quantile(max_similarity(train_cos),probs=c(.03,.12,.25),
                           names=FALSE,type=1)
if (any(!is.finite(min_train_sim))) stop("Train-only OOD reference invalid")
pca <- NULL
if (ARM %in% c("vision_pca","vision_guard")) {
  pca<-prcomp(train_v,center=TRUE,scale.=FALSE,rank.=32)
  if (ncol(pca$rotation)<32)stop("Vision train-only PCA insufficient rank")
}
pca_x <- function(data,k) {
  if (is.null(pca))stop("PCA was not fitted")
  centered<-sweep(data,2,pca$center,"-")
  centered%*%pca$rotation[,seq_len(k),drop=FALSE]
}
# Model alternatives defined BEFORE any test is used. All 3 train-only fits
# per method are selected/calibrated from the SAME held-out CAL scene 10.
candidates<-list()
if (ARM=="color") {
  for (decay in c(.005,.05,.5)) {
    fit<-fit_multinom(scale_x(train_color,color_scaler),decay)
    candidates[[length(candidates)+1]]<-list(
      name=paste0("color_decay_",decay),model=fit,params=list(decay=decay),
      pcal=predict_prob15(fit,scale_x(cal_color,color_scaler)),
      ptest=NULL,gate_cal=rep(TRUE,nrow(cal)),gate_test=NULL)
  }
} else if (ARM=="vision_prototype") {
  for (j in seq_along(min_train_sim)) {
    temperature<-c(10,25,50)[[j]]
    logit_cal<-(cal_cos[,"15"]-cal_cos[,"12"])*temperature
    candidates[[length(candidates)+1]]<-list(
      name=paste0("prototype_temp_",temperature),model=proto,
      params=list(temperature=temperature,minSimilarity=min_train_sim[[j]]),
      pcal=plogis(logit_cal),ptest=NULL,
      gate_cal=max_similarity(cal_cos)>=min_train_sim[[j]],gate_test=NULL)
  }
} else if (ARM=="vision_pca") {
  for (j in 1:3) {
    k<-c(8,16,32)[[j]]
    decay<-c(.05,.15,.50)[[j]]
    fit<-fit_multinom(pca_x(train_v,k),decay)
    candidates[[length(candidates)+1]]<-list(
      name=paste0("vision_pca_",k),model=fit,params=list(pcCount=k,decay=decay),
      pcal=predict_prob15(fit,pca_x(cal_v,k)),ptest=NULL,
      gate_cal=rep(TRUE,nrow(cal)),gate_test=NULL)
  }
} else if (ARM=="vision_guard") {
  for (j in 1:3) {
    k<-c(8,16,32)[[j]]
    sim_threshold<-min_train_sim[[j]]
    fit<-fit_multinom(pca_x(train_v,k),.12)
    candidates[[length(candidates)+1]]<-list(
      name=paste0("vision_ood_guard_",k),model=fit,
      params=list(pcCount=k,decay=.12,minSimilarity=sim_threshold),
      pcal=predict_prob15(fit,pca_x(cal_v,k)),ptest=NULL,
      gate_cal=max_similarity(cal_cos)>=sim_threshold,gate_test=NULL)
  }
}
if (length(candidates)!=3L)stop("Three source hypothesis variants required")

measure <- function(rows,p,admit) {
  proposal<-ifelse(p>=.5,"15","12")
  truth<-rows$label
  correct<-admit & proposal==truth
  wrong<-admit & proposal!=truth
  unknown<-truth=="UNKNOWN"
  list(n=nrow(rows),accepted=sum(admit),abstained=sum(!admit),
       correctKnown=sum(correct),wrongKnown=sum(wrong & !unknown),
       unknownAccepted=sum(admit & unknown),
       wrongTotal=sum(wrong),wrongFraction=mean(wrong),
       knownCount=sum(!unknown),unknownCount=sum(unknown),
       knownCoverage=if(any(!unknown))sum(correct)/sum(!unknown) else NULL,
       unknownFalseAcceptance=if(any(unknown))sum(admit & unknown)/sum(unknown) else NULL,
       acceptedPrecision=if(any(admit))sum(correct)/sum(admit) else NULL)
}
# Exact empirical calibration objective: <= floor(5% of all CAL rows) wrong
# admitted proposals, including both misclassified knowns AND unknown objects.
# NOT a distribution-free guarantee across physical scenes.
calibrate <- function(rows,p,gate) {
  if (length(p)!=nrow(rows) || length(gate)!=nrow(rows))
    stop("Calibration shape mismatch")
  confidence<-pmax(p,1-p)
  truths<-rows$label
  proposal<-ifelse(p>=.5,"15","12")
  wrong<-proposal!=truths
  candidate_thresholds<-unique(c(.50,sort(confidence[gate],decreasing=TRUE)+1e-11,Inf))
  budget<-floor(.05*nrow(rows))
  best<-list(threshold=Inf,correct=-1L,wrong=Inf)
  for (t in candidate_thresholds) {
    accept<-gate & confidence>=t
    error_n<-sum(accept & wrong)
    correct_n<-sum(accept & !wrong)
    if (error_n<=budget &&
        (correct_n>best$correct ||
          (correct_n==best$correct && error_n<best$wrong) ||
          (correct_n==best$correct && error_n==best$wrong && t>best$threshold))) {
        best<-list(threshold=t,correct=correct_n,wrong=error_n)
    }
  }
  if (best$correct<0)stop("Unable to find bounded calibration threshold")
  best$metrics<-measure(rows,p,gate & confidence>=best$threshold)
  if (best$metrics$wrongTotal>budget)stop("Calibration error budget broken")
  best
}
baseline_calibration<-calibrate(cal,baseline_cal,rep(TRUE,nrow(cal)))
baseline_test_admit<-pmax(baseline_test,1-baseline_test)>=baseline_calibration$threshold
baseline_test_metrics<-measure(test,baseline_test,baseline_test_admit)

for (j in seq_along(candidates)) {
  candidates[[j]]$calibration<-calibrate(cal,candidates[[j]]$pcal,
                                        candidates[[j]]$gate_cal)
}
order_indices<-order(
  -vapply(candidates,function(c)c$calibration$metrics$correctKnown,numeric(1)),
  vapply(candidates,function(c)c$calibration$metrics$wrongTotal,numeric(1)),
  seq_along(candidates))
best_idx<-order_indices[[1]]
chosen<-candidates[[best_idx]]
# Pick baseline on calibration if no actual improvement in correct known
# proposals without worsening calibration wrong count. No model promotion
# is allowed from calibration or a single independent physical scene alone.
winner_is_baseline <- (
  chosen$calibration$metrics$correctKnown <= baseline_calibration$metrics$correctKnown ||
  chosen$calibration$metrics$wrongTotal > baseline_calibration$metrics$wrongTotal
)
if (winner_is_baseline) {
  test_probs<-baseline_test
  gate_test<-rep(TRUE,nrow(test))
  threshold<-baseline_calibration$threshold
  fitted_name<-"baseline_color_calibrated"
  selected_calibration<-baseline_calibration
} else {
  if (ARM=="color") {
    test_probs<-predict_prob15(chosen$model,scale_x(test_color,color_scaler))
    gate_test<-rep(TRUE,nrow(test))
  } else if (ARM=="vision_prototype") {
    temp<-chosen$params$temperature
    test_probs<-plogis((test_cos[,"15"]-test_cos[,"12"])*temp)
    gate_test<-max_similarity(test_cos)>=chosen$params$minSimilarity
  } else {
    test_probs<-predict_prob15(chosen$model,pca_x(test_v,chosen$params$pcCount))
    gate_test<-if (ARM=="vision_guard") max_similarity(test_cos)>=chosen$params$minSimilarity
      else rep(TRUE,nrow(test))
  }
  threshold<-chosen$calibration$threshold
  fitted_name<-chosen$name
  selected_calibration<-chosen$calibration
}
test_admit<-gate_test & pmax(test_probs,1-test_probs)>=threshold
selected_test_metrics<-measure(test,test_probs,test_admit)
if (selected_calibration$metrics$wrongTotal>floor(.05*nrow(cal)))
  stop("Selection corrupted empirical safety gate")

# Report every test source object (known 12/15 and unknown 3/22/23).
per_object<-list()
for (obj in sort(unique(test$object_id))) {
  ix<-which(test$object_id==obj)
  per_object[[as.character(obj)]]<-measure(test[ix,,drop=FALSE],
                                          test_probs[ix],test_admit[ix])
}

# Frame-cluster bootstrap: correlated crops from the SAME video frame are NOT
# independent images. This interval remains within one heldout scene only.
set.seed(21114)
ids<-unique(test$frame_id)
selected_right<-as.integer(test_admit & ifelse(test_probs>=.5,"15","12")==test$label)
base_right<-as.integer(baseline_test_admit & ifelse(baseline_test>=.5,"15","12")==test$label)
bootstrap<-replicate(1000,{
  sampled<-sample(ids,length(ids),replace=TRUE)
  group<-unlist(lapply(sampled,function(id) which(test$frame_id==id)))
  known<-sum(test$label[group]!="UNKNOWN")
  if (!known) 0 else sum(selected_right[group]-base_right[group])/known
})
cluster_ci<-as.numeric(quantile(bootstrap,c(.025,.975),names=FALSE,type=1))
safe_diagnostic <- (
  selected_test_metrics$wrongTotal<=floor(.05*nrow(test)) &&
  selected_test_metrics$unknownFalseAcceptance<=.05 &&
  selected_test_metrics$knownCoverage>=.20 &&
  selected_test_metrics$correctKnown>=baseline_test_metrics$correctKnown &&
  selected_test_metrics$wrongTotal<=baseline_test_metrics$wrongTotal
)
result<-list(
 schema="chibi.lens.hb.scene-heldout-open-set.v1",
 sourceArchivePointerSha256=ARCHIVE,sourceNumericCSVsha256=CSV_SHA,
 sourceLicense="CC0-1.0",publicRealImageCrops=655,
 featureExtractor="AppleVisionFeaturePrintRevision2",
 pretrainedAppleVisionWeightsModified=FALSE,
 modelFamily=ARM,calibrationCandidates=lapply(candidates,function(x)
   list(name=x$name,params=x$params,correctKnown=x$calibration$metrics$correctKnown,
        wrongTotal=x$calibration$metrics$wrongTotal,
        threshold=x$calibration$threshold)),
 selectedCandidate=fitted_name,
 selectedCandidateIndex=if(winner_is_baseline)NULL else best_idx,
 trainSceneIds=c(5,9),calibrationSceneIds=10,testSceneIds=11,
 trainExamples=nrow(train),calibrationExamples=nrow(cal),testExamples=nrow(test),
 knownClasses=c(12,15),unknownObjectClasses=c(3,22,23),
 allClassesPresentInEveryRequiredScene=TRUE,
 originalRGBBackgroundMasked=TRUE,
 modelUsesSceneOrGTMetadata=FALSE,
 calibrationMaxWrongAllowed=floor(.05*nrow(cal)),
 calibrationSelected=selected_calibration$metrics,
 calibrationBaseline=baseline_calibration$metrics,
 heldoutSelected=selected_test_metrics,
 heldoutBaseline=baseline_test_metrics,
 heldoutPerObject=per_object,
 withinSceneFrameClusterBootstrapDeltaKnownCoverage95pct=cluster_ci,
 selectedMinusBaselineCorrectKnown=selected_test_metrics$correctKnown-
                                      baseline_test_metrics$correctKnown,
 selectedMinusBaselineWrongTotal=selected_test_metrics$wrongTotal-
                                      baseline_test_metrics$wrongTotal,
 descriptiveSafetyCriteriaMet=safe_diagnostic,
 deploymentAllowed=FALSE,
 scientificClaim=if(safe_diagnostic)
     "EXPLORATORY_SINGLE_PHYSICAL_SCENE_BENEFIT_NOT_FIELD_QUALIFIED"
     else "NO_QUALIFIED_OPEN_SET_GAIN",
 limitations=c("Only one physical heldout scene with 48 correlated frames",
   "Class 12/15 recognizable in 4 scenes, not broad object identification",
   "Unknown class IDs 3/22/23 shared by calibration and test, still hard negatives",
   "Accepted false rate <=5% calibration is not scene-robust guarantee",
   "No live Meta glasses, no model integration, no auth or parent consent"),
 sourceEvidence="HF official archive pointer plus per-member ZIP CRC; complete 2.35GB archive not locally rehashed",
 actualCRACIBillingEUR=NULL,providerAttested=FALSE,
 physicalIdentityVerified=FALSE,agentActionAuthorized=FALSE)
jsonlite::write_json(result,file.path(dest,"training-report.json"),
   pretty=TRUE,auto_unbox=TRUE,null="null",digits=8)
saveRDS(list(
   family=ARM,selectedCandidate=fitted_name,
   selectedModel=if(winner_is_baseline)baseline_model else chosen$model,
   baseline=baseline_model,colorScaler=color_scaler,
   PCA=pca,visionPrototypes=proto,
   trainOnlySimilarityThresholds=min_train_sim,
   selectedCalibrationThreshold=threshold,
   selectedOODThreshold=if(winner_is_baseline)NULL else chosen$params$minSimilarity,
   realNumericSHA256=CSV_SHA,
   classes=classes),
   file.path(dest,"trained-models.rds"),compress="xz")
if (file.size(file.path(dest,"training-report.json"))<100 ||
    file.size(file.path(dest,"trained-models.rds"))<100)
  stop("Model archive incomplete")
cat(jsonlite::toJSON(list(arm=ARM,selected=fitted_name,
    baselineRight=baseline_test_metrics$correctKnown,
    baselineWrong=baseline_test_metrics$wrongTotal,
    selectedRight=selected_test_metrics$correctKnown,
    selectedWrong=selected_test_metrics$wrongTotal,
    selectedUnknownAccepted=selected_test_metrics$unknownAccepted,
    selectedUnknownCount=selected_test_metrics$unknownCount,
    safeDescriptiveCriteria=safe_diagnostic,
    selectedKnownCoverage=selected_test_metrics$knownCoverage,
    sourceRoot=ARCHIVE),
    auto_unbox=TRUE,null="null"),"\n")
