# Base R descriptive analysis only. No physical reliability inference.
args <- commandArgs(trailingOnly=TRUE)
if (length(args) != 1L) stop('Usage: Rscript analyze.R /absolute/path/predictions.csv')
x <- read.csv(args[1], stringsAsFactors=FALSE)
stopifnot(all(c('partition','label','score','proposal','binary_defect') %in% names(x)))
stopifnot(all(is.finite(x$score)), all(x$label %in% c('normal','anomaly')),
          all(x$proposal %in% c('good','hold','defect')),
          all(x$partition %in% c('calibration','heldout')))
stopifnot(all(tolower(as.character(x$binary_defect)) %in% c('true','false')))
x$binary_defect <- tolower(as.character(x$binary_defect)) == 'true'
h <- subset(x, partition == 'heldout')
cat('DESCRIPTIVE_CSV_ANALYSIS / NO ROBOT / verify source bundle separately\n')
stopifnot(all(c('image','sha256') %in% names(x)), !anyDuplicated(x$image), !anyDuplicated(x$sha256))
n_pos <- sum(h$label == 'anomaly'); n_neg <- sum(h$label == 'normal')
if (n_pos > 0L && n_neg > 0L) {
  auc <- (sum(rank(h$score, ties.method='average')[h$label == 'anomaly']) - n_pos*(n_pos+1)/2) / (as.double(n_pos)*n_neg)
  cat('Independent rank-based image AUROC:', format(auc, digits=8), '\n')
}
cat('Rows by partition and label:\n'); print(table(x$partition,x$label))
cat('Heldout denominator:', nrow(h), '\n')
print(table(label=h$label,proposal=h$proposal))
cat('Holds:',sum(h$proposal=='hold'),'/',nrow(h),'\n')
cat('Binary disagreements with image labels:',sum(h$binary_defect != (h$label=='anomaly')),'/',nrow(h),'\n')
cat('Binary/proposal disagreements (excluding holds):',
    sum(h$proposal!='hold' & h$binary_defect!=(h$proposal=='defect')),'/',sum(h$proposal!='hold'),'\n')
cat('Physical object/session IDs unknown; file-level description only. No reliability bounds.\n')
