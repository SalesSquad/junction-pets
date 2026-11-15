#!/usr/bin/env Rscript
# Cluster-resampled fresh, paired synthetic seeds; never real-world Spread evidence.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3L) stop("Usage: bahn-calibrate.R <paired.csv> <out_dir> <bootstrap_draws>")
input <- normalizePath(args[[1]], mustWork = TRUE)
out <- args[[2]]
B <- as.integer(args[[3]])
if (is.na(B) || B != 3000L) stop("Pinned 3000 cluster bootstrap draws required")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
d <- read.csv(input, stringsAsFactors = FALSE)
if (nrow(d) != 10000L || length(unique(d$seed)) != 10000L) stop("Fresh seed coverage must be exact")
if (anyNA(d)) stop("Missing synthetic counts")
for (p in c("baseline", "optimizer")) {
  won <- d[[paste0(p,"_won")]]; on <- d[[paste0(p,"_ontime")]]
  if (any(won < on | on < 0L | won > 40L)) stop("Event count invariant violated")
}
set.seed(20261114L + d$seed[[1L]] %% 10000L)
n <- nrow(d)
score <- function(indices, p) {
  total <- sum(d[[paste0(p,"_won")]][indices])
  if (total <= 0L) stop("Bootstrapped sample has no wins")
  100 * sum(d[[paste0(p,"_ontime")]][indices]) / total
}
observed <- c(baseline = score(seq_len(n),"baseline"), optimizer = score(seq_len(n),"optimizer"))
b <- matrix(NA_real_, nrow=B, ncol=3,
            dimnames=list(NULL,c("baseline","optimizer","paired_delta_pp")))
for (i in seq_len(B)) {
  indices <- sample.int(n, n, replace=TRUE)
  b[i,1] <- score(indices,"baseline")
  b[i,2] <- score(indices,"optimizer")
  b[i,3] <- b[i,2] - b[i,1]
}
summaries <- do.call(rbind,lapply(seq_len(3),function(k) {
  point <- if (k==3L) observed[["optimizer"]]-observed[["baseline"]] else observed[[k]]
  data.frame(metric=colnames(b)[[k]],point=unname(point),
    ci_2_5=unname(quantile(b[,k],.025)),
    ci_97_5=unname(quantile(b[,k],.975)),
    cluster_n=n,bootstrap_draws=B,synthetic_only=TRUE,real_90pct_qualified=FALSE)
}))
write.csv(summaries,file.path(out,"cluster-bootstrap.csv"),row.names=FALSE)
write.csv(as.data.frame(b),file.path(out,"bootstrap-draws.csv"),row.names=FALSE)
if (any(!is.finite(as.matrix(summaries[,2:4])))) stop("Nonfinite clustered CI")
png(file.path(out,"paired-toy-ontime.png"),width=1400,height=800,res=130)
op <- par(mar=c(5,10,5,4))
y <- barplot(observed,col=c("#6B7FA8","#1B9974"),horiz=TRUE,xlim=c(0,100),
 names.arg=c("Baseline","Offline optimiser"),xlab="Observed synthetic on-time (%)",
 main="BAHN offline seed-cluster audit: NOT a real 90% guarantee")
arrows(summaries$ci_2_5[1:2],y,summaries$ci_97_5[1:2],y,
 length=.08,angle=90,code=3,lwd=3)
abline(v=90,lty=2,col="#B84A32",lwd=2)
par(op);dev.off()
cat(sprintf("BAHN_CLUSTER_CALIBRATION toy_baseline_pct=%.4f toy_optimizer_pct=%.4f paired_delta_pp=%.4f seed_clusters=%s bootstrap_draws=%s real_qualified=false\n",
  observed[["baseline"]],observed[["optimizer"]],
  observed[["optimizer"]]-observed[["baseline"]],n,B))
