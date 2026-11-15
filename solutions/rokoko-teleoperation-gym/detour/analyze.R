#!/usr/bin/env Rscript
# Honest paired statistics for actual synthetic MuJoCo detour scenarios.
# Resamples are NOT additional physics simulations.
args <- commandArgs(trailingOnly=TRUE)
if(length(args)!=3L) stop("Rscript analyze.R episodes.csv report_dir bootstrap_B")
src <- normalizePath(args[[1]],mustWork=TRUE)
out <- args[[2]]
B <- as.integer(args[[3]])
if(is.na(B)||B<200L||B>30000L) stop("B must be 200..30000")
dir.create(out,recursive=TRUE,showWarnings=FALSE)
data <- read.csv(src,stringsAsFactors=FALSE,check.names=FALSE)
required <- c("seed","method","success","unsafe","abstained","damage",
              "collision","workspace","error","refusals","physics_steps")
if(!all(required %in% names(data))) stop("Incomplete actual MuJoCo schema")
if(anyNA(data[,required])||anyDuplicated(data[,c("seed","method")])) {
  stop("NA/duplicate scenario-policy units")
}
methods <- c("original","detour","abstain")
if(!identical(sort(unique(data$method)),sort(methods))) {
  stop("Unexpected comparative methods")
}
for(seed in unique(data$seed)) {
  if(!identical(sort(data$method[data$seed==seed]),sort(methods))) {
    stop("Invalid scenario pairing")
  }
}
for(field in c("success","unsafe","abstained","damage","collision","workspace")) {
  if (!is.logical(data[[field]])) {
    x <- tolower(as.character(data[[field]]))
    if (!all(x %in% c("true","false"))) {
      stop(paste("Invalid Boolean data in",field))
    }
    data[[field]] <- x == "true"
  }
}
if(any(data$success & data$unsafe)) stop("Success in unsafe episode")
data$safe <- as.integer(data$success & !data$unsafe)
data$unsafe_b <- as.integer(data$unsafe)
data$abstain_b <- as.integer(data$abstained)
data$incomplete_b <- as.integer(!(data$success | data$unsafe | data$abstained))
wilson <- function(k,n) {
  z <- qnorm(.975);p<-k/n
  denom<-1+z*z/n
  m<-(p+z*z/(2*n))/denom
  a<-z*sqrt(p*(1-p)/n+z*z/(4*n*n))/denom
  c(max(0,m-a),min(1,m+a))
}
rows <- do.call(rbind,lapply(methods,function(method) {
  x <- data[data$method==method,]
  n<-nrow(x);ci<-wilson(sum(x$safe),n)
  data.frame(method=method,cases=n,safe=sum(x$safe),
    rate=mean(x$safe),wilson_low=ci[1],wilson_high=ci[2],
    unsafe=sum(x$unsafe_b),abstained=sum(x$abstain_b),
    incomplete=sum(x$incomplete_b),
    mean_error_m=mean(x$error),
    mean_refusals=mean(x$refusals),physics_steps=sum(x$physics_steps))
}))
write.csv(rows,file.path(out,"summary.csv"),row.names=FALSE)
a <- data[data$method=="original",]
b <- data[data$method=="detour",]
pair <- merge(a[,c("seed","safe","abstain_b","incomplete_b","unsafe_b")],
              b[,c("seed","safe","abstain_b","incomplete_b","unsafe_b")],
              by="seed",suffixes=c("_original","_detour"))
if(nrow(pair)!=length(unique(data$seed))) stop("Missing pair")
set.seed(20261114)
paired_stats <- do.call(rbind,lapply(c("safe","abstain_b","incomplete_b","unsafe_b"),
function(variable){
 diff <- pair[[paste0(variable,"_detour")]]-pair[[paste0(variable,"_original")]]
 n <- length(diff)
 draws <- replicate(B,mean(sample(diff,n,replace=TRUE)))
 b01 <- sum(diff==1);b10<-sum(diff== -1)
 p <- if((b01+b10)>0) binom.test(min(b01,b10),b01+b10,.5)$p.value else 1
 data.frame(outcome=variable,n_paired=n,difference_pp=100*mean(diff),
            ci_lower_pp=100*unname(quantile(draws,.025)),
            ci_upper_pp=100*unname(quantile(draws,.975)),
            exact_discordance_p=p,
            n_detour_better=b01,n_original_better=b10)
}))
write.csv(paired_stats,file.path(out,"paired_bootstrap.csv"),row.names=FALSE)
png(file.path(out,"safety_completion_frontier.png"),width=1350,height=850,res=135)
mat <- rbind(safe=rows$safe,abstained=rows$abstained,
             incomplete=rows$incomplete,unsafe=rows$unsafe)
colnames(mat) <- rows$method
barplot(mat,beside=FALSE,legend.text=rownames(mat),
        args.legend=list(x="topright",bty="n"),
        col=c("#29866d","#788ea6","#d5ac49","#b74848"),
        main="MuJoCo detour — success, abstention, timeout and unsafe",
        ylab="Actual scenarios",xlab="Paired policy (same seeds)")
dev.off()
main <- paired_stats[paired_stats$outcome=="safe",]
report <- c("# Rokoko per-action shield — paired MuJoCo evidence","",
            paste("Source CSV:",basename(src)),
            paste("Actual independent seeds:",length(unique(data$seed))),
            paste("Actually executed physics episodes:",nrow(data)),
            paste("Actual 2ms MuJoCo steps:",format(sum(data$physics_steps),scientific=FALSE,big.mark=",")),
            paste("R paired bootstrap resamples, NOT physics:",B),"",
            "## Per-policy outcomes","")
for(i in seq_len(nrow(rows))) {
  x<-rows[i,]
  report<-c(report,sprintf(
   "%s: %d/%d safe (%.1f%%, Wilson 95%% %.1f–%.1f%%), unsafe=%d, abstain=%d, incomplete/timeouts=%d",
   x$method,x$safe,x$cases,100*x$rate,100*x$wilson_low,
   100*x$wilson_high,x$unsafe,x$abstained,x$incomplete))
}
report<-c(report,"",sprintf(
 "Paired safe-success delta detour minus original: %.1fpp, 95%% bootstrap %.1f..%.1fpp.",
 main$difference_pp,main$ci_lower_pp,main$ci_upper_pp),
 "",
 "**Interpretation:** fewer abstentions can simply become timeouts, not success.",
 "Do not relax hard deadman/collision checks. Report all unsafe and unresolved.",
 "This is synthetic MuJoCo with uncalibrated object/obstacle dimensions and",
 "no physical Rokoko hardware or real human intervention. No learned RL claim.",
 "The 95% interval is conditional on this synthetic seed distribution.")
writeLines(report,file.path(out,"REPORT.md"))
cat(sprintf("R_DETOUR_ANALYSIS_DONE scenarios=%d physics_episodes=%d bootstrap=%d\n",
            length(unique(data$seed)),nrow(data),B))
print(rows[,c("method","safe","unsafe","abstained","incomplete")],row.names=FALSE)
print(paired_stats[,c("outcome","difference_pp","ci_lower_pp","ci_upper_pp")],row.names=FALSE)
