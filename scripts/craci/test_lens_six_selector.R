#!/usr/bin/env Rscript
# Six distinct boundary/selection tests against the source-exact public HB
# model-selector used by PR #190 (already integrated to main via PR #201).
# No train/dev/test images, no model fitting, no scoring or production decisions.
args<-commandArgs(trailingOnly=TRUE)
if(length(args)!=4L)stop("Usage: SELECTOR.R EXPECTED_BLOB ROUND OUT.json")
selector<-args[[1]]
expected_blob<-args[[2]]
round<-suppressWarnings(as.integer(args[[3]]))
out<-args[[4]]
if(is.na(round)||!round%in%1:6||!grepl("^[a-f0-9]{40}$",expected_blob))
 stop("Only six source-verified rounds")
actual_blob<-system2("git",c("hash-object",shQuote(selector)),stdout=TRUE)
if(length(actual_blob)!=1L || actual_blob[[1]]!=expected_blob)
 stop("HB selector Git blob changed")
if(file.exists(out))stop("Do not overwrite previous source-bound receipt")
scope<-new.env(parent=baseenv())
sys.source(selector,envir=scope)
if(!is.function(scope$select_hb_candidate))
 stop("Missing selector from expected source")
kcal<-100L;ncal<-250L
m<-function(correct,wrong,reported=NULL) list(
 correctKnown=as.numeric(correct),wrongTotal=as.numeric(wrong),
 knownCoverage=if(is.null(reported))as.numeric(correct/kcal) else as.numeric(reported))
base<-function(correct,wrong)list(metrics=m(correct,wrong))
cand<-function(correct,wrong,reported=NULL)list(calibration=list(metrics=m(correct,wrong,reported)))
expected_index<-NA_integer_;expected_status<-""
if(round==1L) {
 # The highest-recall unsafe contender must not hide feasible second choice.
 candidates<-list(cand(60,3),cand(45,2),cand(35,1))
 prior<-base(20,2);expected_index<-2L
 expected_status<-"SAFE_PARETO_CANDIDATE"
} else if(round==2L) {
 # Equal correct-known coverage: choose candidate with fewer wrong accepts.
 candidates<-list(cand(41,2),cand(41,1),cand(39,0))
 prior<-base(20,2);expected_index<-2L
 expected_status<-"SAFE_PARETO_CANDIDATE"
} else if(round==3L) {
 # Deterministic stable tie-break (source order, not nondeterministic).
 candidates<-list(cand(41,1),cand(41,1),cand(39,0))
 prior<-base(20,2);expected_index<-1L
 expected_status<-"SAFE_PARETO_CANDIDATE"
} else if(round==4L) {
 # Zero-utility/under-20% methods must NOT beat abstain baseline.
 candidates<-list(cand(19,0),cand(0,0))
 prior<-base(0,0);expected_index<-0L
 expected_status<-"STRICT_BASELINE_FALLBACK"
} else if(round==5L) {
 # Never relax baseline wrong-accept cap even if below global 5%.
 candidates<-list(cand(50,13),cand(38,3))
 prior<-base(20,2);expected_index<-0L
 expected_status<-"STRICT_BASELINE_FALLBACK"
} else {
 # Internally contradictory rates must be rejected before any selection.
 candidates<-list(cand(40,1,.99))
 prior<-base(20,2);expected_status<-"INVALID_METRIC_REFUSED"
}
if(round==6L) {
 result<-try(scope$select_hb_candidate(candidates,prior,ncal,kcal),silent=TRUE)
 if(!inherits(result,"try-error"))stop("FAIL OPEN: rate contradiction")
 actual_index<-NA_integer_
} else {
 result<-scope$select_hb_candidate(candidates,prior,ncal,kcal)
 actual_index<-as.integer(result$index)
 if(actual_index!=expected_index || result$status!=expected_status)
  stop("Selector failed safety property round ",round)
 if(actual_index!=0L) {
   selected<-candidates[[actual_index]]$calibration$metrics
   b<-prior$metrics
   if(selected$wrongTotal>b$wrongTotal ||
      selected$wrongTotal>floor(.05*ncal) ||
      selected$correctKnown<=b$correctKnown ||
      selected$knownCoverage<.20)stop("FAIL OPEN: selected unsafe/zero-utility")
 }
}
record<-list(
 schema="junction.chibi-lens.six-selector-boundary.v1",
 workId="CHIBI-LENS-SIX-SELECTOR-20261115",
 round=round,selectorSourceGitBlob=expected_blob,
 testFamily=c("unsafe_top_vs_safe_second","tie_lower_wrong","stable_tie",
              "zero_utility","strict_baseline_wrong_bound",
              "contradictory_known_coverage")[[round]],
 expectedStatus=expected_status,actualStatus=expected_status,
 expectedIndex=if(is.na(expected_index))NULL else expected_index,
 selectedIndex=if(is.na(actual_index))NULL else actual_index,
 syntheticCalibrationOnly=TRUE,realFieldQualified=FALSE,
 privateDataUsed=FALSE,modelWeightsFitted=FALSE,
 historicalTrainingTestScenesReopened=FALSE)
dir.create(dirname(out),recursive=TRUE,showWarnings=FALSE)
jsonlite::write_json(record,out,pretty=TRUE,auto_unbox=TRUE,null="null")
cat(jsonlite::toJSON(list(round=round,status="PASS",
     family=record$testFamily,fieldQualified=FALSE),
     auto_unbox=TRUE),"\n")
