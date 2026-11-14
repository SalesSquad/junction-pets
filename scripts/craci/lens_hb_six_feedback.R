#!/usr/bin/env Rscript
# Six sequential source-pinned train-only candidate learning stages per fold.
# SIX disjoint frame-blocked development folds, one CRACI job per fold.
# No scene8/11 labels or features are present in this source fixture.
# Selection sees cal-dev training portion only; withheld cal-dev fold opened
# exactly once after all six corrective stages have frozen their incumbent.
suppressPackageStartupMessages(library(nnet))
suppressPackageStartupMessages(library(jsonlite))

argv <- commandArgs(trailingOnly=TRUE)
if (length(argv)!=5L) stop("Usage: Rscript hb-six.R TRAIN_CAL.csv ADMISSION.json FOLD OUT SOURCE_SHA")
src <- argv[[1]]; manifest <- argv[[2]]; fold <- suppressWarnings(as.integer(argv[[3]]))
dest <- argv[[4]]; source_sha <- argv[[5]]
CSV_SHA <- "4deb97cbb98d37bc09f2a47e5a24d298cf3ccfe760166fc089a73a6e8ab60863"
PARENT_SHA <- "ad29e80353145d9ac62b7a9bc52111acb0504c07"
OLD_SHA <- "2540595932867db80e1313dc011640b901c53b16a4f3f897b9d13e32d0c57363"
if (is.na(fold)||!fold %in% 0:5||!grepl("^[a-f0-9]{40}$",source_sha))
 stop("Full immutable source SHA and fold 0..5 required")
if (!file.exists(src)||!file.exists(manifest)||file.exists(dest))
 stop("Source admission or exclusive model output missing")
j <- jsonlite::fromJSON(manifest,simplifyVector=FALSE)
if (!identical(j$schema,"junction.craci.hb.six-dev-source.v1") ||
    !identical(j$sourceCSVsha256,CSV_SHA) ||
    !identical(j$sourceFileSHA256,OLD_SHA) ||
    !identical(j$datasetLicense,"CC0-1.0") ||
    !isTRUE(j$excludedAllTestRowsBeforeFeatureExtraction) ||
    !isTRUE(j$noScene8Or11FeatureRows) ||
    !identical(j$trainRows,186L) || !identical(j$calDevRows,234L) ||
    !identical(j$modelPromotionAllowed,FALSE) ||
    length(j$folds)!=6L)
 stop("Public numeric-only train-cal preregistration changed")
hashfile <- function(path) strsplit(system2("sha256sum",shQuote(path),
                                   stdout=TRUE),"[[:space:]]+")[[1]][[1]]
if (!identical(hashfile(src),CSV_SHA))stop("Public original source digest mismatch")
data <- read.csv(src,stringsAsFactors=FALSE,check.names=FALSE)
color <- sprintf("c%02d",0:47)
vision <- sprintf("v%03d",0:767)
required <- c("source","license","modality","split","scene_id","frame_id",
              "label","object_id","known_class",color,vision)
if (nrow(data)!=420L||!all(required%in%names(data))||
    anyNA(data[,required])||!all(data$split%in%c("train","cal"))||
    any(data$scene_id%in%c(8L,11L))||
    any(data$source!="bop-hb-val-primesense-public-cc0")||
    any(data$license!="CC0-1.0")||
    any(data$modality!="REAL_RGB_MASKED"))
 stop("Invalid public data/source/split; no old test scene allowed")
train <- data[data$split=="train",,drop=FALSE]
cal <- data[data$split=="cal",,drop=FALSE]
if (nrow(train)!=186L||nrow(cal)!=234L||
    !setequal(unique(train$scene_id),c(5L,9L))||
    !setequal(unique(cal$scene_id),10L)||
    !setequal(unique(train$label),c("12","15"))||
    !setequal(unique(cal$label),c("12","15","UNKNOWN")))
 stop("Scene or known/unknown development labels changed")
heldout_frames <- as.integer(unlist(j$folds[[fold+1L]]$devFrames))
all_frames <- sort(unique(cal$frame_id))
if (length(all_frames)!=48L||length(heldout_frames)!=8L||
    !all(heldout_frames%in%all_frames) ||
    !identical(as.integer(unlist(j$folds[[fold+1L]]$fold)),fold))
 stop("Frame blocked holdout mismatch")
a <- cal[!cal$frame_id%in%heldout_frames,,drop=FALSE]
b <- cal[cal$frame_id%in%heldout_frames,,drop=FALSE]
if (length(unique(a$frame_id))!=40L||length(unique(b$frame_id))!=8L||
    !setequal(unique(c(a$frame_id,b$frame_id)),all_frames)||
    nrow(a)<30L||nrow(b)<10L)
 stop("Missing disjoint physical frame groups")
classes <- c("12","15")
as_x <- function(rows,fields) {
 x <- as.matrix(rows[,fields,drop=FALSE])
 if (!is.numeric(x)||any(!is.finite(x)))stop("Invalid numerical feature")
 x
}
train_v <- as_x(train,vision);a_v <- as_x(a,vision);b_v <- as_x(b,vision)
train_c <- as_x(train,color);a_c <- as_x(a,color);b_c <- as_x(b,color)
for (v in list(train_v,a_v,b_v)) {
 norms <- sqrt(rowSums(v*v))
 if (any(abs(norms-1)>0.0003))stop("Apple Vision norms differ from source-bound method")
}
center <- colMeans(train_c)
std <- apply(train_c,2,sd)
std[!is.finite(std)|std<1e-8] <- 1
color_scale <- function(x) sweep(sweep(x,2,center,"-"),2,std,"/")
as_data <- function(x,label=NULL) {
 frame <- as.data.frame(x)
 names(frame) <- sprintf("x%03d",seq_len(ncol(x)))
 if (!is.null(label))frame$label <- factor(label,levels=classes)
 frame
}
set.seed(20261114L)
baseline <- suppressWarnings(nnet::multinom(label~.,
    data=as_data(color_scale(train_c),train$label),
    maxit=160,MaxNWts=20000,decay=.05,trace=FALSE))
prob_class15 <- function(model,x) {
 raw <- predict(model,newdata=as_data(x),type="probs")
 p <- if (is.matrix(raw)) as.numeric(raw[,"15"]) else as.numeric(raw)
 if (length(p)!=nrow(x)||any(!is.finite(p))||any(p<0|p>1))
  stop("Invalid binary class probabilities")
 p
}
base_a <- prob_class15(baseline,color_scale(a_c))
base_b <- prob_class15(baseline,color_scale(b_c))
proto <- vapply(classes,function(label) colMeans(train_v[train$label==label,,drop=FALSE]),
                numeric(ncol(train_v)))
proto <- sweep(proto,2,sqrt(colSums(proto*proto)),"/")
colnames(proto) <- classes
cosine <- function(x) {
 z <- x %*% proto
 colnames(z)<-classes
 if (any(!is.finite(z)))stop("Invalid training-only cosine")
 z
}
cos_train <- cosine(train_v)
cos_a <- cosine(a_v);cos_b <- cosine(b_v)
sim_train <- apply(cos_train,1,max)
q <- as.numeric(quantile(sim_train,c(.03,.12,.25),
                         type=1,names=FALSE))
if(any(!is.finite(q))||any(diff(q)<0))stop("Invalid frozen similarity quantiles")
scores <- function(z,temp) plogis(temp*(z[,"15"]-z[,"12"]))
pca <- prcomp(train_v,center=TRUE,scale.=FALSE,rank.=16)
if(ncol(pca$rotation)!=16L)stop("Insufficient known train-only PCA rank")
projection <- function(x) sweep(x,2,pca$center,"-") %*%
   pca$rotation[,seq_len(16),drop=FALSE]
pca_model <- suppressWarnings(nnet::multinom(label~.,
    data=as_data(projection(train_v),train$label),
    maxit=150,MaxNWts=3000,decay=.12,trace=FALSE))
pca_a <- prob_class15(pca_model,projection(a_v))
pca_b <- prob_class15(pca_model,projection(b_v))

measure <- function(rows,p,accept) {
 if (length(p)!=nrow(rows)||length(accept)!=nrow(rows))
  stop("Metric input shapes mismatch")
 truth <- rows$label
 guess <- ifelse(p>=.5,"15","12")
 known <- truth!="UNKNOWN"
 right <- accept & known & guess==truth
 wrong <- accept & !right
 list(n=nrow(rows),knownCount=sum(known),unknownCount=sum(!known),
      accepted=sum(accept),abstained=sum(!accept),
      correctKnown=sum(right),wrongKnown=sum(wrong&known),
      unknownAccepted=sum(wrong&!known),wrongTotal=sum(wrong),
      knownCoverage=if(any(known))sum(right)/sum(known) else NULL,
      unknownFalseAcceptance=if(any(!known))sum(wrong&!known)/sum(!known) else NULL)
}
calibrate <- function(rows,p,gate,maxWrong=Inf) {
 if (length(p)!=nrow(rows)||length(gate)!=nrow(rows) ||
     length(maxWrong)!=1L||is.na(maxWrong)||maxWrong<0)
  stop("Calibration input invalid")
 budget <- min(floor(.05*nrow(rows)),maxWrong)
 conf <- pmax(p,1-p)
 options <- unique(c(.5,sort(conf[gate],decreasing=TRUE)+1e-11,Inf))
 best <- list(threshold=Inf,correct=-1L,wrong=Inf)
 for(t in options) {
  admitted <- gate & conf>=t
  m <- measure(rows,p,admitted)
  if (m$wrongTotal<=budget &&
      (m$correctKnown>best$correct ||
       (m$correctKnown==best$correct && m$wrongTotal<best$wrong) ||
       (m$correctKnown==best$correct&&m$wrongTotal==best$wrong&&t>best$threshold))) {
    best <- list(threshold=t,correct=m$correctKnown,wrong=m$wrongTotal)
  }
 }
 if(best$correct<0)stop("No valid calibration threshold including abstention")
 best$metrics <- measure(rows,p,gate & conf>=best$threshold)
 if(best$metrics$wrongTotal>budget)stop("Calibration failed closed")
 best
}
base_cal <- calibrate(a,base_a,rep(TRUE,nrow(a)))
champ <- list(stage=0L,method="baseline_color_calibrated",
              p_a=base_a,p_b=base_b,
              gate_a=rep(TRUE,nrow(a)),gate_b=rep(TRUE,nrow(b)),
              threshold=base_cal$threshold,metrics=base_cal$metrics)
if(base_cal$metrics$wrongTotal>floor(.05*nrow(a)))
 stop("Baseline empirical risk bound invalid")
risk <- list()
recipes <- c("proto_q12_t25","proto_q25_t50","proto_q03_t10",
             "pca16_ridge","color_prototype_consensus",
             "prototype_pca_dual_abstention")
for (stage in seq_along(recipes)) {
 method <- recipes[[stage]]
 if(stage==1L) {
  p_a<-scores(cos_a,25);p_b<-scores(cos_b,25)
  gate_a<-apply(cos_a,1,max)>=q[[2]]
  gate_b<-apply(cos_b,1,max)>=q[[2]]
 } else if(stage==2L) {
  p_a<-scores(cos_a,50);p_b<-scores(cos_b,50)
  gate_a<-apply(cos_a,1,max)>=q[[3]]
  gate_b<-apply(cos_b,1,max)>=q[[3]]
 } else if(stage==3L) {
  p_a<-scores(cos_a,10);p_b<-scores(cos_b,10)
  gate_a<-apply(cos_a,1,max)>=q[[1]]
  gate_b<-apply(cos_b,1,max)>=q[[1]]
 } else if(stage==4L) {
  p_a<-pca_a;p_b<-pca_b
  gate_a<-rep(TRUE,nrow(a));gate_b<-rep(TRUE,nrow(b))
 } else if(stage==5L) {
  pp_a<-scores(cos_a,25);pp_b<-scores(cos_b,25)
  p_a<-(pp_a+base_a)/2;p_b<-(pp_b+base_b)/2
  gate_a<-(pp_a>=.5)==(base_a>=.5) & apply(cos_a,1,max)>=q[[2]]
  gate_b<-(pp_b>=.5)==(base_b>=.5) & apply(cos_b,1,max)>=q[[2]]
 } else {
  pp_a<-scores(cos_a,25);pp_b<-scores(cos_b,25)
  p_a<-pp_a;p_b<-pp_b
  gate_a<-(pp_a>=.5)==(pca_a>=.5) & apply(cos_a,1,max)>=q[[3]]
  gate_b<-(pp_b>=.5)==(pca_b>=.5) & apply(cos_b,1,max)>=q[[3]]
 }
 if(any(!is.finite(p_a))||any(!is.finite(p_b)))
   stop("Non-finite new candidate prediction")
 # Each next correction learns from the *previous* champion's error budget
 # and cannot increase previous false admissions, even within empirical 5%.
 previous_wrong <- champ$metrics$wrongTotal
 cal <- calibrate(a,p_a,gate_a,maxWrong=previous_wrong)
 cand <- cal$metrics
 improving <- cand$correctKnown>champ$metrics$correctKnown &&
    cand$wrongTotal<=champ$metrics$wrongTotal &&
    cand$knownCoverage>=.20
 if(improving) {
  champ<-list(stage=stage,method=method,p_a=p_a,p_b=p_b,
      gate_a=gate_a,gate_b=gate_b,
      threshold=cal$threshold,metrics=cand)
 }
 risk[[stage]]<-list(stage=stage,method=method,
   source="frozen_train5_9_corrective_cal10",
   candidateCal=cand,previousWrongBudget=previous_wrong,
   candidateImprovedPrevious=improving,
   selectedIncumbent=champ$method,
   selectedCalibration=champ$metrics,
   negativeStatus=if(improving)"CAL_DEV_CORRECTIVE_STEP" else "NO_CAL_DEV_IMPROVEMENT")
 if(champ$metrics$wrongTotal>base_cal$metrics$wrongTotal ||
    champ$metrics$wrongTotal>floor(.05*nrow(a)))
   stop("Adaptive step relaxed a true fail-closed risk gate")
}
# The remaining 8 frame groups were NOT used to select or fit any stage.
# Open only after all six stages are frozen; this is same-scene development CV,
# not an independent new physical-scene qualification or wearable validation.
selected_dev<-measure(b,champ$p_b,
        champ$gate_b & pmax(champ$p_b,1-champ$p_b)>=champ$threshold)
base_dev<-measure(b,base_b,
        pmax(base_b,1-base_b)>=base_cal$threshold)
dev_result<-list(selected=selected_dev,baseline=base_dev,
  deltaCorrectKnown=selected_dev$correctKnown-base_dev$correctKnown,
  deltaWrongAccepted=selected_dev$wrongTotal-base_dev$wrongTotal,
  sourcePhysicalScene=10,
  independentPhysicalScene=FALSE)
report<-list(
 schema="junction.craci.hb.six-feedback-fold.v1",
 sourceHead=source_sha,originalIntegratedMain=PARENT_SHA,
 fixtureSHA256=CSV_SHA,originalPublicHBsha256=OLD_SHA,
 fold=fold,trainSceneIds=c(5,9),developmentSceneId=10,
 trainingExamples=nrow(train),trainCalGroupFrames=40,
 internalDevFrameGroups=8,
 internalDevFrameIds=heldout_frames,
 calibrationExamples=nrow(a),
 internalDevExamples=nrow(b),
 allPreviouslyOpenedTestScenesExcluded=c(8,11),
 knownLabels=c(12,15),unknownDevelopmentLabels=c(3,22,23),
 calibrationBaseline=base_cal$metrics,
 sixStageSequentialFeedback=risk,
 finalChampion=champ$method,
 finalChampionStage=champ$stage,
 finalCal=champ$metrics,
 internalDevelopmentOnly=dev_result,
 modelAcceptedForProduct=FALSE,
 safetyThresholdsRelaxed=FALSE,
 scientificConclusion="DEVELOPMENT_ONLY_NO_BLIND_FIELD_QUALIFICATION",
 rawPixelsIncluded=FALSE,privateMediaIncluded=FALSE,
 physicalIdentityVerified=FALSE,agentActionAuthorized=FALSE,
 providerSignedAttestation=FALSE,actualProviderBillEur=NULL,
 limitations=c("Six nonindependent model-selection methods per one fold, all from same CC0 physical scene10",
   "Holdout 8 frame groups are disjoint inside each fold, not independent scenes",
   "Six folds together are cross-validation, not a new field acceptance or product promotion",
   "No used-up scene8 or scene11 used for selection, train or model evaluation",
   "Known class12/15 and unknowns use labels on scene10; real glasses/identity/auth unqualified"))
if(dir.exists(dest) || file.exists(dest))stop("Model destination exists, no overwrite")
dir.create(dest,recursive=TRUE,showWarnings=FALSE)
jsonlite::write_json(report,file.path(dest,"training-report.json"),
   pretty=TRUE,auto_unbox=TRUE,null="null",digits=8)
saveRDS(list(finalChampion=champ$method,finalStage=champ$stage,
             calibrationThreshold=champ$threshold,
             calibratedWrong=champ$metrics$wrongTotal,
             baselineColorModel=baseline,
             prototype=proto,
             trainOnlyCosineQuantiles=q,
             pcaTrain=pca,pcaModel=pca_model,
             colorNormalizer=list(center=center,scale=std),
             sourceHead=source_sha,fixtureSHA256=CSV_SHA,fold=fold),
  file.path(dest,"trained-models.rds"),compress="xz")
if(file.size(file.path(dest,"training-report.json"))<1000 ||
   file.size(file.path(dest,"trained-models.rds"))<1000)
 stop("Missing model or evaluation output")
cat(jsonlite::toJSON(list(fold=fold,corrections=length(risk),
    final=champ$method,
    calKnownCorrect=champ$metrics$correctKnown,
    calWrong=champ$metrics$wrongTotal,
    devKnownCorrect=selected_dev$correctKnown,
    devWrong=selected_dev$wrongTotal,
    devBaseCorrect=base_dev$correctKnown,
    devBaseWrong=base_dev$wrongTotal,
    quality=report$scientificConclusion),
    auto_unbox=TRUE,null="null"),"\n")
