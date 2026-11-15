#!/usr/bin/env Rscript
# CALIBRATION-ONLY source-bound Pareto regression.
# Deliberately synthetic labels; never opens HB scene8 or historic scene11.
args<-commandArgs(trailingOnly=TRUE)
if(length(args)!=1L)stop("Expected source R file to inspect")
lines<-readLines(args[[1]],warn=FALSE)
start<-grep("^measure<-function\\(",lines)
first<-grep("^calibrate<-function\\(",lines)
last<-grep("^bcal<-calibrate\\(",lines)
stopifnot(length(start)==1L,length(first)==1L,length(last)==1L,
          start<first,first<last)
scope<-new.env(parent=baseenv())
eval(parse(text=paste(lines[start:(last-1)],collapse="\n")),envir=scope)
# In the source regression, a 5%-only optimizer picks 60 good, 5 bad.
# A second safe candidate (40 good, 0 bad) must remain available when the
# actual baseline has zero wrong accepts. Do NOT filter only afterwards.
cal<-data.frame(label=c(rep("15",60),rep("UNKNOWN",40)))
probs<-c(rep(.98,40),rep(.70,20),rep(.88,5),rep(.52,35))
gate<-rep(TRUE,100)
legacy<-scope$calibrate(cal,probs,gate)
safe<-scope$calibrate(cal,probs,gate,max_wrong=0)
baseline<-scope$calibrate(cal,rep(.5,100),gate)
rebound<-scope$calibrate(cal,probs,gate,
                        max_wrong=baseline$metrics$wrongTotal)
stopifnot(legacy$metrics$correctKnown==60L,legacy$metrics$wrongTotal==5L)
stopifnot(safe$metrics$correctKnown==40L,safe$metrics$wrongTotal==0L)
stopifnot(baseline$metrics$correctKnown==0L,baseline$metrics$wrongTotal==0L)
stopifnot(rebound$metrics$correctKnown==40L,rebound$metrics$wrongTotal==0L)
bad<-try(scope$calibrate(cal,probs,gate,max_wrong=-1),silent=TRUE)
stopifnot(inherits(bad,"try-error"))
cat("HB8_CAL_PARETO_PASS old=60/5 safe=40/0",
    " zero-baseline-safe=TRUE bad-budget-refused=TRUE\n")
