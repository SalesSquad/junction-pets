#!/usr/bin/env Rscript
# Reproduce historical HB Vision selector defect without running expensive ML.
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==1L)
source(args[[1]],local=TRUE)
m <- function(correct,wrong) list(metrics=list(
  correctKnown=correct,wrongTotal=wrong,knownCoverage=correct/91))
cand <- function(correct,wrong) list(calibration=m(correct,wrong))
base <- m(0,0)
# The previous selection logic returned baseline if the highest recall
# candidate had any errors, ignoring a lower-ranked 0-error competitor.
candidates <- list(cand(80,6),cand(56,0),cand(43,0))
chosen <- select_hb_candidate(candidates,base,234,91)
stopifnot(chosen$index==2L,chosen$status=="SAFE_PARETO_CANDIDATE",
          identical(chosen$eligibleIndices,c(2L,3L)),
          chosen$calibrationWrongBudget==11)
# The other observed Vision arm has the same failure mode: 81/3 vs 56/0.
chosen2 <- select_hb_candidate(list(cand(81,3),cand(56,0),cand(43,0)),
                               base,234,91)
stopifnot(chosen2$index==2L)
# All unsafe -> preserve original baseline, never waive fail-closed.
all_unsafe <- select_hb_candidate(list(cand(80,12),cand(50,2)),base,234,91)
stopifnot(all_unsafe$index==0L,
          all_unsafe$status=="STRICT_BASELINE_FALLBACK")
# Safe but *useless* <20% correct coverage -> no candidate.
zero_utility <- select_hb_candidate(list(cand(0,0),cand(18,0)),base,234,91)
stopifnot(zero_utility$index==0L)
# Nonzero baseline can be strictly dominated without additional risk.
prev <- m(36,2)
next_good <- select_hb_candidate(list(cand(60,3),cand(54,2),cand(49,1)),
                                 prev,234,91)
stopifnot(next_good$index==2L)
# A metric rate inconsistent with its numerator is rejected.
bad <- list(calibration=list(metrics=list(
  correctKnown=56,wrongTotal=0,knownCoverage=1)))
stopifnot(inherits(try(select_hb_candidate(list(bad),base,234,91),
                       silent=TRUE),"try-error"))
cat("HB_SELECTOR_6_SOURCE_BOUND_REGRESSIONS_PASS\n")
