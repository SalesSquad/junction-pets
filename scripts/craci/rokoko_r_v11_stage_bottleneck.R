#!/usr/bin/env Rscript
# Retrospective TRAIN-only stage audit. No simulator, model fit or pilot dispatch.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) stop("Usage: Rscript rokoko_r_v11_stage_bottleneck.R VERIFIED_V11_DIR")
root <- normalizePath(args[[1L]], mustWork = TRUE)
data <- read.csv(file.path(root, "v11-trials.csv"), stringsAsFactors = FALSE)
required <- c("seed","stratum","world_hash","strategy","safe_goal","unsafe",
              "full_transition_sha256","forward_reopened_after_side","contact",
              "lateral25_after_contact","reopen_after_lateral25",
              "full_contact_lateral_reopen_dwell","contacts","dwell_ticks_final","final_error")
stopifnot(all(required %in% names(data)), nrow(data)==800L,
          length(unique(data$seed))==160L, all(table(data$seed)==5L),
          nrow(unique(data[c("seed","strategy")]))==800L,
          nrow(unique(data[c("seed","stratum","world_hash")]))==160L)
binary_cols <- c("safe_goal","unsafe","forward_reopened_after_side","contact",
                 "lateral25_after_contact","reopen_after_lateral25",
                 "full_contact_lateral_reopen_dwell")
stopifnot(all(vapply(data[binary_cols], function(x) all(!is.na(x) & x %in% 0:1),
                     logical(1))),
          all(data$reopen_after_lateral25 <= data$lateral25_after_contact),
          all(data$lateral25_after_contact <= data$contact),
          all(data$full_contact_lateral_reopen_dwell <= data$reopen_after_lateral25),
          all(data$full_contact_lateral_reopen_dwell <= data$safe_goal),
          all(data$safe_goal <= as.integer(data$dwell_ticks_final >= 250)),
          all(data$safe_goal <= as.integer(data$final_error < 0.02)),
          all(data$safe_goal <= as.integer(data$contacts > 0)),
          all(data$safe_goal <= 1L-data$unsafe))
v5 <- subset(data,strategy=="frozen_v5")
v11 <- subset(data,strategy=="v11_goal_preserving")
paired <- merge(v5,v11,by="seed",all=TRUE,sort=TRUE,suffixes=c("_v5","_v11"))
stopifnot(nrow(paired)==160L,!anyNA(paired),
          all(paired$stratum_v5==paired$stratum_v11),
          all(paired$world_hash_v5==paired$world_hash_v11))
paired$changed <- paired$full_transition_sha256_v5 != paired$full_transition_sha256_v11
stopifnot(sum(paired$changed)==62L,all(paired$stratum_v5[paired$changed]=="near"),
          sum(paired$safe_goal_v5)==18L,sum(paired$safe_goal_v11)==18L,
          all(paired$safe_goal_v5==paired$safe_goal_v11))

metrics <- c(contact="contact",
             lateral_after_contact="lateral25_after_contact",
             chronological_forward_after_lateral="reopen_after_lateral25",
             full_contact_lateral_forward_goal="full_contact_lateral_reopen_dwell",
             any_side_forward_proxy="forward_reopened_after_side",
             true_goal250="safe_goal")
groups <- list(all=paired,
               near=paired[paired$stratum_v5=="near",,drop=FALSE],
               clear=paired[paired$stratum_v5=="clear",,drop=FALSE],
               changed_near=paired[paired$changed,,drop=FALSE],
               unchanged_near=paired[paired$stratum_v5=="near" & !paired$changed,,drop=FALSE])
expected_group_n <- c(all=160L,near=128L,clear=32L,changed_near=62L,unchanged_near=66L)
stopifnot(identical(vapply(groups,nrow,0L),expected_group_n))

paired_row <- function(group,key,field) {
  a <- group[[paste0(field,"_v5")]]
  b <- group[[paste0(field,"_v11")]]
  gained <- sum(a==0L & b==1L)
  lost <- sum(a==1L & b==0L)
  discord <- gained+lost
  p <- if (discord==0L) NA_real_ else binom.test(gained,discord,p=0.5)$p.value
  data.frame(group=key,metric=field,worlds=nrow(group),
             v5=sum(a),v11=sum(b),gained=gained,lost=lost,delta=sum(b)-sum(a),
             exact_p=p,stringsAsFactors=FALSE)
}
rows <- list()
for (key in names(groups)) {
  for (metric in names(metrics)) {
    field <- unname(metrics[[metric]])
    x <- paired_row(groups[[key]],key,field)
    x$metric <- metric
    rows[[length(rows)+1L]] <- x
  }
}
result <- do.call(rbind,rows)
stopifnot(nrow(result)==length(groups)*length(metrics))
one <- function(group,metric,col) result[result$group==group & result$metric==metric,col][[1L]]
stopifnot(one("changed_near","contact","gained")==29L,
          one("changed_near","lateral_after_contact","gained")==2L,
          one("changed_near","chronological_forward_after_lateral","gained")==1L,
          one("changed_near","full_contact_lateral_forward_goal","gained")==0L,
          one("changed_near","any_side_forward_proxy","gained")==48L,
          one("changed_near","true_goal250","gained")==0L,
          one("changed_near","true_goal250","v5")==0L,
          one("changed_near","true_goal250","v11")==0L,
          one("near","any_side_forward_proxy","v5")==60L,
          one("near","any_side_forward_proxy","v11")==108L,
          one("near","lateral_after_contact","v5")==11L,
          one("near","lateral_after_contact","v11")==13L,
          one("near","chronological_forward_after_lateral","v5")==2L,
          one("near","chronological_forward_after_lateral","v11")==3L)
# Holm correction is exploratory, conditional on already selected source TRAIN worlds.
subset <- result$group=="near" & result$metric %in%
          c("contact","lateral_after_contact","chronological_forward_after_lateral",
            "any_side_forward_proxy")
result$holm_near_exploratory <- NA_real_
result$holm_near_exploratory[subset] <- p.adjust(result$exact_p[subset],method="holm")
write.csv(result,file.path(root,"v11-stage-pairs.csv"),row.names=FALSE,na="")
# Pilot sizing is a mathematical scenario, NOT a recommendation to spend/dispatch.
pilot_worlds <- 48L
pilot_near <- 40L
unsafe_rate_upper_95 <- 1-0.05^(1/pilot_worlds)
hypothetical_near_goal_rates <- c(.01,.02,.05)
pilot_detection <- 1-(1-hypothetical_near_goal_rates)^pilot_near
scenario <- data.frame(hypothetical_true_goal_rate_near=hypothetical_near_goal_rates,
                       probability_at_least_one_near_goal=pilot_detection,
                       independently_selected_near_worlds=pilot_near)
write.csv(scenario,file.path(root,"v12-pilot-sensitivity-illustration.csv"),
          row.names=FALSE)
fmt <- function(x) ifelse(is.na(x),"not informative",sprintf("%.5g",x))
tab <- result[result$group %in% c("near","changed_near"),]
lines <- sprintf("| %s | %s | %d | %d | %d | %d | %d | %s |",
                 tab$group,tab$metric,tab$worlds,tab$v5,tab$v11,
                 tab$gained,tab$lost,fmt(tab$exact_p))
report <- c(
 "# CRACI V11: chronological bottleneck and V12 pilot sensitivity (source-bound R)",
 "",
 "2026-11-15. Independent retrospective **TRAIN-only** comparison of original MuJoCo run 43653579339.",
 "Original archive SHA256 bbf94c662fab3ac0efab3448c9e917dcce473a2644efc82a3f4835dd85792bae.",
 "Product ab6df4054ef6ed350b479469590a48046a0c0a68; harness b1938bee9dbca482f645b5dde3359de38e6c125e.",
 "R requires the SHA-pinned Python extractor and checks 800 source rows; no physics, model training, provider signature or model promotion.",
 "",
 "## Chronological stage counts, V5 and V11 paired on same TRAIN world",
 "",
 "| World subset | Event | Worlds | V5 | V11 | New | Lost | Exploratory exact paired p |",
 "|---|---|---:|---:|---:|---:|---:|---:|",
 lines,
 "",
 "**Key failure localization:** 62/160 changed full trajectories were all in the 128 near-corridor worlds. Among those 62,",
 "29 new contacts and 48 new non-chronological forward reopenings translated into only",
 "**2** new safe 25-mm lateral movements after contact and **1** new forward reopening after that lateral.",
 "No changed world obtained actual terminal 250-tick safe-goal dwell, and zero completed the full contact–lateral–reopen–dwell path.",
 "All 18 original V5 successful worlds remained unchanged by V11.",
 "",
 "The event counts and exploratory paired tests reuse the same already evaluated TRAIN cohort;",
 "they do not establish causal motor improvement or prospective generalization.",
 "The ordered stage definitions are stricter than the non-chronological forward-opening proxy.",
 "Chronological stage completion is NOT universally required to reach a clear-world goal;",
 "this analysis does not change the original physical-goal definition.",
 "",
 "## V12 48-world source-only pilot sensitivity (hypothetical, never executed here)",
 "",
 "The already proposed 144 episodes are 3 paired policies on only **48 distinct worlds** (40 near, 8 clear).",
 "If candidate unsafe counts are 0 on all 48 and world outcomes were independent random draws,",
 paste0("a one-sided 95% binomial upper bound on unsafe-*world* risk would still be ",
        sprintf("%.2f%%",100*unsafe_rate_upper_95),
        ". That conditional illustration is NOT a physical or source-sampling safety qualification."),
 paste0("For hypothetical independent near-world novel goal rates 1%, 2%, 5%,",
        " the probability of at least one observed new goal in 40 near worlds is ",
        paste0(sprintf("%.1f%%",100*pilot_detection),collapse=", "),", respectively."),
 "These are mathematical design examples, not V12 predictions; no observed V12 effectiveness is claimed.",
 "A single pilot novelty is only an exploration signal; original full 250-tick success,",
 "baseline non-regression, shield correctness, independent physics replay and distinct future-world evidence",
 "remain required before any promotion claim.",
 "",
 "**No action authorized:** do not rerun V10/V11 original source worlds, spend CRACI credits,",
 "relax goal/safety guards, open locked dev/test/OOD or claim model/robot deployment.",
 "Current V12 product PR #226, harness PR #229 and P1 fix PR #230 remain under their existing owners."
)
writeLines(report,file.path(root,"ROKOKO_R_V11_STAGE_BOTTLENECK.md"))
cat("STAGE_AUDIT_OK\n")
print(result[result$group=="changed_near",c("metric","v5","v11","gained","lost","exact_p")],
      row.names=FALSE)
cat("V12 hypothetical 48-world unsafe upper (%)=",sprintf("%.2f",100*unsafe_rate_upper_95),"\n")
