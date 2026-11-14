#!/usr/bin/env Rscript
# Independent R analysis of ACTUAL MuJoCo episode CSVs.
# Bootstrap resamples are statistical draws, not additional physics episodes.
library(stats)
library(graphics)
library(grDevices)
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=3L) stop("Usage: Rscript analyze.R episodes.csv out_dir B")
input <- normalizePath(args[[1]],mustWork=TRUE)
output <- args[[2]]
B <- as.integer(args[[3]])
if (is.na(B)||B<100||B>50000) stop("B must be 100..50000")
dir.create(output,showWarnings=FALSE,recursive=TRUE)
d <- read.csv(input,stringsAsFactors=FALSE)
required <- c("split","seed","method","complete","success","unsafe",
              "abstained","options","physics_steps","return_value")
if (!all(required %in% names(d))) stop("Incomplete raw episode schema")
yes <- function(x) {
  if (is.logical(x)) return(x)
  if (!all(x %in% c("True","False","true","false"))) stop("Bad Boolean")
  tolower(x)=="true"
}
for (field in c("complete","success","unsafe","abstained")) {
  d[[field]] <- yes(d[[field]])
}
if (anyNA(d[,required])||any(!d$complete)||any(d$success&d$unsafe)||
    anyDuplicated(d[,c("split","seed","method")])) {
  stop("Invalid/incomplete/duplicate or unsafe success episodes")
}
methods <- c("dqn","heuristic","abstain")
splits <- c("cal","test","ood")
for (split in splits) {
  x <- d[d$split==split,]
  if (!nrow(x)||!identical(sort(unique(x$method)),sort(methods))) {
    stop(paste("Missing split/method:",split))
  }
  for (seed in unique(x$seed)) {
    if (!identical(sort(x$method[x$seed==seed]),sort(methods))) {
      stop(paste("Unpaired split/seed:",split,seed))
    }
  }
}
d$strict_success <- as.integer(d$success & !d$unsafe)
d$risk <- as.integer(d$unsafe)
d$abstain <- as.integer(d$abstained)
wilson <- function(k,n) {
  z <- qnorm(.975)
  p <- k/n
  v <- 1+z*z/n
  mid <- (p+z*z/(2*n))/v
  err <- z*sqrt(p*(1-p)/n+z*z/(4*n*n))/v
  c(low=max(0,mid-err),high=min(1,mid+err))
}
summary <- do.call(rbind,lapply(c("train",splits),function(split) {
  do.call(rbind,lapply(methods,function(method) {
    x <- d[d$split==split&d$method==method,]
    if (!nrow(x)) return(NULL)
    ci <- wilson(sum(x$strict_success),nrow(x))
    data.frame(split=split,method=method,episodes=nrow(x),
      strict_successes=sum(x$strict_success),
      success_rate=mean(x$strict_success),wilson_low=unname(ci[1]),wilson_high=unname(ci[2]),
      unsafe_episodes=sum(x$risk),unsafe_rate=mean(x$risk),
      abstain_episodes=sum(x$abstain),mean_options=mean(x$options),
      mean_reward=mean(x$return_value),
      physics_steps=sum(x$physics_steps))
  }))
}))
rownames(summary) <- NULL
write.csv(summary,file.path(output,"policy_summary.csv"),row.names=FALSE)
set.seed(20261114)
compare <- function(split,candidate,outcome) {
  a <- d[d$split==split&d$method==candidate,c("seed",outcome)]
  b <- d[d$split==split&d$method=="heuristic",c("seed",outcome)]
  names(a) <- c("seed","candidate")
  names(b) <- c("seed","baseline")
  pairs <- merge(a,b,by="seed")
  if (nrow(pairs)!=nrow(a)||nrow(pairs)!=nrow(b)) stop("Incomplete pairing")
  delta <- if(outcome=="risk") pairs$baseline-pairs$candidate else
                                 pairs$candidate-pairs$baseline
  n <- length(delta)
  draws <- replicate(B,mean(sample(delta,n,replace=TRUE)))
  exact <- if(outcome=="strict_success") {
    n01 <- sum(pairs$baseline==0 & pairs$candidate==1)
    n10 <- sum(pairs$baseline==1 & pairs$candidate==0)
    if(n01+n10) binom.test(min(n01,n10),n01+n10,p=.5)$p.value else 1
  } else NA_real_
  data.frame(split=split,candidate=candidate,outcome=outcome,
    n_paired=n,improvement_pp=100*mean(delta),
    ci_low_pp=100*unname(quantile(draws,.025)),
    ci_high_pp=100*unname(quantile(draws,.975)),paired_exact_p=exact)
}
paired <- do.call(rbind,lapply(c("test","ood"),function(split) {
  do.call(rbind,lapply(c("dqn","abstain"),function(method) {
    rbind(compare(split,method,"strict_success"),compare(split,method,"risk"))
  }))
}))
write.csv(paired,file.path(output,"paired_bootstrap.csv"),row.names=FALSE)
for (metric in c("success_rate","unsafe_rate")) {
  x <- summary[summary$split %in% splits,]
  m <- xtabs(as.formula(paste(metric,"~split+method")),x)
  png(file.path(output,paste0(metric,".png")),width=1500,height=980,res=150)
  barplot(t(m)*100,beside=TRUE,
    col=c("#4D82C5","#32A78B","#A3A3A3"),ylab="Actual MuJoCo episode rate (%)",
    main=paste("Rokoko learned vs scripted:",metric),
    legend.text=colnames(m),args.legend=list(x="topright",bty="n"))
  dev.off()
}
report <- c("# Rokoko Double-DQN — source-bound MuJoCo evaluation","",
  sprintf("Recorded actual physics episodes: %d",nrow(d)),
  sprintf("Recorded actual solver steps: %s",
          format(sum(d$physics_steps),big.mark=",",scientific=FALSE)),
  sprintf("R bootstrap samples: %d (statistical resampling, NOT physics)",B),"")
for (split in splits) {
  report <- c(report,paste("##",split),"")
  for(method in methods) {
    x <- summary[summary$split==split&summary$method==method,]
    report <- c(report,sprintf(
      "%s: %d/%d safe (%.1f%%, Wilson 95%% %.1f–%.1f%%); %d unsafe and %d abstained.",
      method,x$strict_successes,x$episodes,100*x$success_rate,
      100*x$wilson_low,100*x$wilson_high,x$unsafe_episodes,x$abstain_episodes))
  }
}
report <- c(report,"","## Paired bootstrap vs same-world heuristic","")
for(i in seq_len(nrow(paired))) {
  x <- paired[i,]
  report <- c(report,sprintf(
    "%s %s, %s: %.2f pp (95%% interval %.2f to %.2f pp)",
    x$split,x$candidate,x$outcome,x$improvement_pp,x$ci_low_pp,x$ci_high_pp))
}
report <- c(report,"",
  "All successes and unsafe events are SYNTHETIC MuJoCo observations.",
  "One training seed does NOT prove broad RL generalization or hardware safety.",
  "Model, CUDA gradient, source and frozen-test integrity require separate",
  "Python/Git/SHA256 verification. No real Rokoko device or Isaac training.")
writeLines(report,file.path(output,"REPORT.md"),useBytes=TRUE)
cat(sprintf("R_DONE episodes=%d physics_steps=%d bootstrap_resamples=%d\n",
            nrow(d),sum(d$physics_steps),B))
print(summary[summary$split %in% c("test","ood"),
              c("split","method","strict_successes","episodes","unsafe_episodes")],
      row.names=FALSE)
