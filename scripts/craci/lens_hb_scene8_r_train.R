#!/usr/bin/env Rscript
# Frozen Pareto-safe calibration correction + fresh, never-used real HB scene8.
# Training only on public known 12/15 objects from source scenes 5 and 9.
# Calibration only scene10; scene11 is never used in this experiment.
# New test scene8 tests known15 and unknown classes 11/22/24/31/32 only.
suppressPackageStartupMessages(library(nnet))
suppressPackageStartupMessages(library(jsonlite))

argv<-commandArgs(trailingOnly=TRUE)
if(length(argv)!=6L)
 stop("Usage: Rscript lens_hb_scene8_r_train.R OLD_CSV NEW_CSV NEW_ADMISSION.json OUT SOURCE_HEAD BASE_SOURCE_SHA")
old_csv<-argv[[1]];fresh_csv<-argv[[2]];new_admission<-argv[[3]]
dest<-argv[[4]];source_head<-argv[[5]];prior_head<-argv[[6]]
if(!grepl("^[a-f0-9]{40}$",source_head) ||
   !identical(prior_head,"3f8d57cbd47e07be97137e03121205248e88d56f"))
 stop("Exact reviewed source SHA required")
if(!dir.exists(dest))dir.create(dest,recursive=TRUE)
stopifnot(length(list.files(dest,all.files=FALSE))==0L)

original_sha<-"2540595932867db80e1313dc011640b901c53b16a4f3f897b9d13e32d0c57363"
fixture_sha<-"4c29e622d2dd4f709792ef0c41e7a09d28f16020ef941b5b64a1cc8469ae464d"
hash_file<-function(path) {
 stdout<-system2("sha256sum",shQuote(path),stdout=TRUE)
 strsplit(stdout,"[[:space:]]+")[[1]][[1]]
}
stopifnot(file.exists(old_csv),file.exists(fresh_csv),file.exists(new_admission),
          identical(hash_file(old_csv),original_sha),
          identical(hash_file(fresh_csv),fixture_sha))
admission<-jsonlite::read_json(new_admission,simplifyVector=TRUE)
stopifnot(identical(admission$schema,"junction.lens.hb.scene8.public-ood-numeric.v1"),
          identical(admission$sourceParentSHA,prior_head),
          identical(admission$sourceTrainingCSVsha256,original_sha),
          identical(admission$csvSha256,fixture_sha),
          identical(admission$sourceLicense,"CC0-1.0"),
          identical(as.integer(admission$scene),8L),
          identical(admission$knownClassPresent,15L),
          identical(admission$knownClassAbsent,12L),
          identical(as.integer(admission$rowCount),282L),
          identical(as.integer(admission$frameGroups),48L),
          identical(admission$rawPixelsUploaded,FALSE),
          identical(admission$privateOwnerData,FALSE),
          identical(admission$modelTrainingFromScene8Allowed,FALSE))

source<-read.csv(old_csv,check.names=FALSE,stringsAsFactors=FALSE)
fresh<-read.csv(fresh_csv,check.names=FALSE,stringsAsFactors=FALSE)
color_cols<-sprintf("c%02d",0:47)
vision_cols<-sprintf("v%03d",0:767)
fields<-c("source","license","modality","split","scene_id","frame_id",
          "object_id","label","known_class",color_cols,vision_cols)
if(!all(fields%in%names(source))||!all(fields%in%names(fresh)))
 stop("Feature schema mismatch")
# Source was already used for a prior study. Ignore all previously opened test
# rows at every training/threshold/calibration stage; only *fresh* scene8
# contributes test labels. No mixing classes with a scene identity predictor.
train<-source[source$split=="train",,drop=FALSE]
cal<-source[source$split=="cal",,drop=FALSE]
test<-fresh[fresh$split=="fresh_ood",,drop=FALSE]
stopifnot(nrow(train)==186L,nrow(cal)==234L,nrow(test)==282L,
          setequal(unique(train$scene_id),c(5L,9L)),
          setequal(unique(cal$scene_id),10L),
          setequal(unique(test$scene_id),8L),
          setequal(unique(train$label),c("12","15")),
          setequal(unique(cal$label),c("12","15","UNKNOWN")),
          setequal(unique(test$label),c("15","UNKNOWN")),
          sum(test$label=="15")==42L,
          sum(test$label=="UNKNOWN")==240L,
          !any(c(8L,11L)%in%train$scene_id),
          !any(c(8L,11L)%in%cal$scene_id))
for(f in list(train,cal,test)) {
 stopifnot(all(f$source=="bop-hb-val-primesense-public-cc0"),
           all(f$license=="CC0-1.0"),
           all(f$modality=="REAL_RGB_MASKED"),
           !anyNA(f[c(color_cols,vision_cols)]))
}
classes<-c("12","15")
T<-function(df,cols) {
 x<-as.matrix(df[,cols,drop=FALSE])
 stopifnot(is.numeric(x),all(is.finite(x)))
 x
}
train_v<-T(train,vision_cols);cal_v<-T(cal,vision_cols);test_v<-T(test,vision_cols)
train_c<-T(train,color_cols);cal_c<-T(cal,color_cols);test_c<-T(test,color_cols)
for(v in list(train_v,cal_v,test_v)) {
 norms<-sqrt(rowSums(v*v))
 stopifnot(all(is.finite(norms)),all(abs(norms-1)<0.0003))
}
means<-colMeans(train_c)
devs<-apply(train_c,2,sd)
devs[!is.finite(devs)|devs<1e-8]<-1
scaled<-function(x)sweep(sweep(x,2,means,"-"),2,devs,"/")
make_data<-function(x,labels=NULL) {
 out<-as.data.frame(x)
 names(out)<-sprintf("x%03d",seq_len(ncol(x)))
 if(!is.null(labels)) out$label<-factor(labels,levels=classes)
 out
}
baseline<-suppressWarnings(nnet::multinom(label~.,
    data=make_data(scaled(train_c),train$label),
    decay=.05,maxit=160,MaxNWts=20000,trace=FALSE))
predict15<-function(x) {
 p<-predict(baseline,newdata=make_data(scaled(x)),type="probs")
 if(is.matrix(p))p<-p[,"15"]
 p<-as.numeric(p)
 stopifnot(all(is.finite(p)),all(p>=0&p<=1))
 p
}
pbase_cal<-predict15(cal_c)
pbase_test<-predict15(test_c)

# New supervised model: class prototypes fit ONLY from train, same pre-registered
# temp25 and train-only .12 similarity quantile from original public study.
proto<-vapply(classes,function(label)
    colMeans(train_v[train$label==label,,drop=FALSE]),
    numeric(ncol(train_v)))
proto<-sweep(proto,2,sqrt(colSums(proto*proto)),"/")
colnames(proto)<-classes
cosine<-function(x){
 z<-x%*%proto
 colnames(z)<-classes
 stopifnot(all(is.finite(z)))
 z
}
train_cos<-cosine(train_v)
cal_cos<-cosine(cal_v)
test_cos<-cosine(test_v)
min_sim<-as.numeric(quantile(apply(train_cos,1,max),.12,
                            names=FALSE,type=1))
stopifnot(abs(min_sim-0.82641441)<0.00001) # source-bound train-only reference
p_cal<-plogis(25*(cal_cos[,"15"]-cal_cos[,"12"]))
p_test<-plogis(25*(test_cos[,"15"]-test_cos[,"12"]))
gate_cal<-apply(cal_cos,1,max)>=min_sim
gate_test<-apply(test_cos,1,max)>=min_sim

measure<-function(rows,p,allow){
 proposal<-ifelse(p>=.5,"15","12")
 known<-rows$label!="UNKNOWN"
 correct<-allow&known&proposal==rows$label
 wrong<-allow&!correct
 list(examples=nrow(rows),accepted=sum(allow),abstained=sum(!allow),
      correctKnown=sum(correct),
      wrongKnown=sum(wrong&known),
      unknownAccepted=sum(wrong&!known),
      wrongTotal=sum(wrong),
      wrongFraction=mean(wrong),
      knownCount=sum(known),unknownCount=sum(!known),
      knownCoverage=if(sum(known))sum(correct)/sum(known) else NULL,
      unknownFalseAcceptance=if(sum(!known))sum(wrong&!known)/sum(!known) else NULL,
      acceptedPrecision=if(sum(allow))sum(correct)/sum(allow) else NULL)
}
calibrate<-function(rows,p,gate){
 if(length(p)!=nrow(rows)||length(gate)!=nrow(rows))
  stop("Calibrator row mismatch")
 conf<-pmax(p,1-p)
 wrong<-ifelse(p>=.5,"15","12")!=rows$label
 thresholds<-unique(c(.5,sort(conf[gate],decreasing=TRUE)+1e-11,Inf))
 budget<-floor(.05*nrow(rows))
 best<-list(threshold=Inf,correct=-1L,wrong=Inf)
 for(t in thresholds){
  accept<-gate&conf>=t
  wrong_n<-sum(accept&wrong)
  correct_n<-sum(accept&!wrong)
  if(wrong_n<=budget&&
     (correct_n>best$correct ||
     (correct_n==best$correct&&wrong_n<best$wrong) ||
     (correct_n==best$correct&&wrong_n==best$wrong&&t>best$threshold))) {
   best<-list(threshold=t,correct=correct_n,wrong=wrong_n)
  }
 }
 if(best$correct<0)stop("Calibration failed closed")
 best$metrics<-measure(rows,p,gate&pmax(p,1-p)>=best$threshold)
 stopifnot(best$metrics$wrongTotal<=budget)
 best
}
bcal<-calibrate(cal,pbase_cal,rep(TRUE,nrow(cal)))
ccal<-calibrate(cal,p_cal,gate_cal)
# Repair the old Pareto-selector bug: choose among FEASIBLE safe candidates
# BEFORE ranking correct-known successes, never choose best-coverage but unsafe
# then blindly revert to the abstain-all baseline.
eligible<-(ccal$metrics$wrongTotal<=bcal$metrics$wrongTotal &&
           ccal$metrics$correctKnown>bcal$metrics$correctKnown)
selected<-if(eligible)"vision_prototype_temp25_safe_frontier" else "baseline_color_calibrated"
chosen_p<-if(eligible)p_test else pbase_test
chosen_gate<-if(eligible)gate_test else rep(TRUE,nrow(test))
chosen_threshold<-if(eligible)ccal$threshold else bcal$threshold
selected_accept<-chosen_gate&pmax(chosen_p,1-chosen_p)>=chosen_threshold
baseline_accept<-pmax(pbase_test,1-pbase_test)>=bcal$threshold
selected_metrics<-measure(test,chosen_p,selected_accept)
baseline_metrics<-measure(test,pbase_test,baseline_accept)
stopifnot(ccal$metrics$wrongTotal<=floor(.05*nrow(cal)),
          bcal$metrics$wrongTotal<=floor(.05*nrow(cal)),
          if(eligible)ccal$metrics$wrongTotal<=bcal$metrics$wrongTotal else TRUE)

# One preregistered fresh physical scene, 48 correlated frame groups.
# Bootstrap ONLY class15 known-correct coverage and unknown object acceptance
# within this one scene; not a general two-class performance bound.
frames<-sort(unique(test$frame_id))
stopifnot(length(frames)==48L)
chosen_right<-as.integer(selected_accept & test$label=="15" & chosen_p>=.5)
base_right<-as.integer(baseline_accept & test$label=="15" & pbase_test>=.5)
set.seed(20261114L+8L)
paired<-replicate(2000,{
 sample_frames<-sample(frames,length(frames),replace=TRUE)
 ix<-unlist(lapply(sample_frames,function(f)which(test$frame_id==f)))
 known<-sum(test$label[ix]=="15")
 if(!known)0 else sum(chosen_right[ix]-base_right[ix])/known
})
ci<-as.numeric(quantile(paired,c(.025,.975),names=FALSE,type=1))
science_positive<-eligible&&
  selected_metrics$correctKnown>baseline_metrics$correctKnown&&
  selected_metrics$wrongTotal<=baseline_metrics$wrongTotal&&
  selected_metrics$unknownFalseAcceptance<=.05&&ci[1]>0
report<-list(
 schema="junction.lens.hb.scene8.prototype-frontier.v1",
 exactTrainingSourceHEAD=source_head,priorSourceHEAD=prior_head,
 publicArchivePointerSHA256="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f",
 oldTrainingCSVsha256=original_sha,freshOODcsvSHA256=fixture_sha,
 trainingScenes=c(5,9),calibrationScene=10,freshOODscene=8,
 excludedPreviouslyViewedTestScene=11,
 knownTrainingLabels=c(12,15),knownHeldoutLabel=15,
 absentKnownHeldoutLabel=12,
 unknownOODlabels=c(11,22,24,31,32),
 trainRows=nrow(train),calibrationRows=nrow(cal),freshOODrows=nrow(test),
 sourceLicense="CC0-1.0",
 candidate="vision_prototype_temp25",
 trainOnlyMinSimilarity=min_sim,
 prototypeCalibratedWrongBudget=floor(.05*nrow(cal)),
 prototypeCalibration=ccal$metrics,colorCalibration=bcal$metrics,
 paretoFeasible=eligible,selectedModel=selected,
 freshOODselected=selected_metrics,freshOODbaseline=baseline_metrics,
 withinScene48FramePairedBootstrap95pct=ci,
 scienceExploratoryPositive=science_positive,
 qualityClaim=if(science_positive)"EXPLORATORY_KNOWN15_ONLY_OOD_GAIN"
     else "NO_QUALIFIED_SCENE8_GAIN",
 limitations=c(
  "Single previously-unseen physical HB scene8, not official BOP benchmark or device validation",
  "Known class 12 ABSENT from new OOD scene, so cannot validate both-class recognition",
  "Unknown classes have different prevalence; observed false-accept risk is dataset-specific",
  "Frozen class threshold and model chosen from previously exposed calibration scene10",
  "No real Meta glasses identity, consent, authorization, private camera data or hardware safety"
 ),
 realDeviceQualified=FALSE,physicalIdentityVerified=FALSE,
 agentActionAuthorized=FALSE,privateMediaUsed=FALSE,
 rawPixelsInCloud=FALSE,providerAttested=FALSE,actualProviderBillEUR=NULL
)
jsonlite::write_json(report,file.path(dest,"evaluation.json"),
                     pretty=TRUE,auto_unbox=TRUE,null="null",digits=8)
saveRDS(list(family="vision_prototype_temp25_safe_frontier",
             prototype=proto,colorBaseline=baseline,
             colorScaler=list(center=means,scale=devs),
             sourceHEAD=source_head,trainingCSVsha256=original_sha,
             testCSVsha256=fixture_sha,trainOnlySimilarityThreshold=min_sim,
             selectedCalibrationThreshold=chosen_threshold,
             usedFallbackBaseline=!eligible),
        file.path(dest,"trained-model.rds"),compress="xz")
stopifnot(file.size(file.path(dest,"evaluation.json"))>500,
          file.size(file.path(dest,"trained-model.rds"))>100)
cat(jsonlite::toJSON(list(model=selected,
  calPrototypeCorrect=ccal$metrics$correctKnown,
  calPrototypeWrong=ccal$metrics$wrongTotal,
  calBaselineCorrect=bcal$metrics$correctKnown,
  calBaselineWrong=bcal$metrics$wrongTotal,
  freshScene8Known15Right=selected_metrics$correctKnown,
  freshScene8UnknownAccepted=selected_metrics$unknownAccepted,
  freshScene8UnknownCount=selected_metrics$unknownCount,
  freshScene8BaselineRight=baseline_metrics$correctKnown,
  freshScene8BaselineWrong=baseline_metrics$wrongTotal,
  knownCoverageCI=ci,quality=report$qualityClaim),
  auto_unbox=TRUE,null="null"),"\n")
