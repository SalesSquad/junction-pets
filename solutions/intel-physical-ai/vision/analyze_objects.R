# Independent base-R description. Verify artifact integrity separately.
a <- commandArgs(trailingOnly=TRUE)
if (length(a)!=1L) stop('Usage: Rscript analyze_objects.R predictions.csv')
x <- read.csv(a[1], stringsAsFactors=FALSE, na.strings=c('','NA'))
stopifnot(all(c('image','sha256','role','label','score','diagnostic','binary_defect') %in% names(x)),
          !anyDuplicated(x$image),!anyDuplicated(x$sha256),all(x$role %in% c('calibration','evaluation')),
          all(x$label %in% c('normal','anomaly')),all(x$diagnostic %in% c('good','defect','hold')),
          all(is.finite(x$score[!is.na(x$score)])))
b <- tolower(as.character(x$binary_defect))
stopifnot(all(is.na(b) | b %in% c('true','false')))
x$binary <- ifelse(is.na(b),NA,b=='true')
e <- subset(x,role=='evaluation');c <- subset(x,role=='calibration')
stopifnot(nrow(c)==104L,sum(c$label=='anomaly')==40L,sum(c$label=='normal')==64L)
cal_tp <- sum(c$label=='anomaly' & c$binary,na.rm=TRUE)
cal_fp <- sum(c$label=='normal' & c$binary,na.rm=TRUE)
cal_ok <- !anyNA(c$binary) && cal_tp>=38L && cal_fp<=6L
cat('IMAGE-LEVEL DESCRIPTION / NO ROBOT / NO POPULATION QUALIFICATION\n')
cat('Calibration TP',cal_tp,'/40; FP',cal_fp,'/64; feasible',cal_ok,'\n')
if (nrow(e)==0L) {
  cat('CALIBRATION ONLY: zero evaluation images in this input; no heldout result.\n')
} else {
  stopifnot(nrow(e)==110L,sum(e$label=='anomaly')==60L,sum(e$label=='normal')==50L)
  TP <- sum(e$label=='anomaly' & e$binary,na.rm=TRUE)
  FP <- sum(e$label=='normal' & e$binary,na.rm=TRUE)
  TN <- sum(e$label=='normal' & !e$binary,na.rm=TRUE)
  FN <- 60L-TP
  unknown <- sum(is.na(e$binary) | is.na(e$score))
  auc <- if (anyNA(e$score)) NA_real_ else (sum(rank(e$score,ties.method='average')[e$label=='anomaly'])-60*61/2)/(60*50)
  cat('Evaluation TP',TP,'FN',FN,'FP',FP,'TN',TN,'unscorable',unknown,'\n')
  cat('Defect recall',TP/60,'normal false-positive rate',FP/50,'image AUROC',auc,'\n')
  cat('Offline point targets met',cal_ok && unknown==0L && TP/60>=.95 && FP/50<=.10,'\n')
  print(table(label=e$label,decision=factor(e$diagnostic,levels=c('good','hold','defect'))))
  cat('Defect-to-good',sum(e$label=='anomaly' & e$diagnostic=='good')/60,
      'normal-to-defect',sum(e$label=='normal' & e$diagnostic=='defect')/50,
      'hold rate',sum(e$diagnostic=='hold')/110,'\n')
}
cat('Physical object/session identity unknown; HOLD is neither detection nor acceptance.\n')
