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
cat('REAL_DATA_OFFLINE / NO ROBOT\n')
cat('Rows by partition and label:\n'); print(table(x$partition,x$label))
cat('Heldout denominator:', nrow(h), '\n')
print(table(label=h$label,proposal=h$proposal))
cat('Holds:',sum(h$proposal=='hold'),'/',nrow(h),'\n')
cat('Binary disagreements with image labels:',sum(h$binary_defect != (h$label=='anomaly')),'/',nrow(h),'\n')
cat('Binary/proposal disagreements (excluding holds):',
    sum(h$proposal!='hold' & h$binary_defect!=(h$proposal=='defect')),'/',sum(h$proposal!='hold'),'\n')
cat('Physical object/session IDs unknown; file-level description only. No reliability bounds.\n')
