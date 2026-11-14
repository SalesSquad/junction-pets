#!/usr/bin/env Rscript
# Small synthetic checks for numerical integrity; no data files/providers.
script <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value=TRUE))
source(file.path(dirname(normalizePath(script)), "train_reranker.R"))
check <- function(ok, message) {
  if (!isTRUE(ok)) stop(message, call.=FALSE)
  cat("PASS", message, "\n")
}
rejects <- function(code) inherits(tryCatch({force(code); NULL},error=identity),"error")

fixture <- function() {
  rows <- list()
  for (partition in c("train","dev")) {
    ids <- if (partition=="train") paste0("t",1:4) else paste0("v",1:2)
    families <- if (partition=="train") c("tf1","tf1","tf2","tf2") else c("df1","df1")
    for (i in seq_along(ids)) {
      j <- if (i %% 2L) i+1L else i-1L
      for (candidate in c(i,j)) {
        positive <- as.integer(candidate==i)
        row <- data.frame(split=partition,query_id=ids[i],query_family=families[i],
          candidate_id=ids[candidate],candidate_family=families[candidate],label=positive,
          baseline_rank=if (positive) 2 else 1,r4_score=1-positive,stringsAsFactors=FALSE)
        for (name in R6_BASE_FEATURES) row[[name]] <- if (positive) 0.8 else 0.2
        row$f_radio <- if (positive) 0.9 else 0.1
        for (name in R6_OCR_FEATURES) row[[name]] <- positive
        row$f_ocr_digit_conflict <- 1-positive
        rows[[length(rows)+1L]] <- row
      }
    }
  }
  do.call(rbind,rows)
}

difference <- matrix(c(1,2,-1,0.5,0.7,-0.2),nrow=3,byrow=TRUE)
weight <- c(0.2,0.3,0.5); beta <- c(0.3,-0.4); lambda <- 0.1; epsilon <- 1e-6
numeric_gradient <- vapply(seq_along(beta),function(j) {
  upper <- lower <- beta; upper[j] <- upper[j]+epsilon; lower[j] <- lower[j]-epsilon
  (r6_objective(upper,difference,weight,lambda)-r6_objective(lower,difference,weight,lambda))/(2*epsilon)
},numeric(1))
check(max(abs(numeric_gradient-r6_gradient(beta,difference,weight,lambda)))<1e-7,
      "analytic gradient agrees with finite differences")

data <- fixture(); fitted <- r6_fit(data,full_cohort=FALSE)
check(length(fitted$report$optimizer_candidates)==12L &&
      all(vapply(fitted$report$optimizer_candidates,function(x)
        x$optimization$parameter_update_observed &&
        x$optimization$final_objective<x$optimization$initial_objective,logical(1))),
      "all twelve fits actually update weights and reduce the loss")
check(!fitted$report$selection$baseline_retained &&
      fitted$report$selection$baseline_dev$recall_at_1==0 &&
      fitted$report$selection$best_trained_dev$recall_at_1==1,
      "real fitted weights repair a deliberately wrong baseline")
check(fitted$model$selected_method=="refit6" && fitted$model$regularization==1,
      "equal development metrics prefer fewer features then larger ridge")

changed <- data; changed$f_visual[changed$split=="dev"] <- 99
other <- r6_fit(changed,full_cohort=FALSE)
check(all(vapply(seq_len(12),function(i)
  identical(fitted$report$optimizer_candidates[[i]]$scaler,
            other$report$optimizer_candidates[[i]]$scaler),logical(1))),
  "development feature changes cannot change any training scaler")

perfect <- data; perfect$r4_score <- perfect$label
retained <- r6_fit(perfect,full_cohort=FALSE)
check(retained$report$selection$baseline_retained &&
      retained$model$kind=="frozen_r4_score_passthrough" &&
      identical(retained$predictions$rank_score,as.numeric(perfect$r4_score)),
      "exact performance tie retains the frozen R4 scores")
check(!retained$model$qualification && !retained$model$action_authorized &&
      !retained$model$policy$calibrated && is.null(retained$model$policy$threshold),
      "no fit or baseline branch creates acceptance authority")

missing <- data[!(data$query_id %in% c("t1","v1") & data$label==1L),]
missing <- r6_validate_data(missing)
train <- missing[missing$split=="train",]
pair <- r6_pairs(train,r6_transform(train,r6_scaler(train,R6_BASE_FEATURES)))
dev <- missing[missing$split=="dev",]
metrics <- r6_retrieval_metrics(r6_rank_queries(dev,dev$label))
check(pair$skipped_queries==1L && metrics$queries==2L && metrics$missing_positive_queries==1L &&
      metrics$recall_at_1==0.5,"missing positives stay in denominators without oracle injection")
bad <- data; bad$f_radio[1] <- Inf
check(rejects(r6_validate_data(bad)) && rejects(r6_validate_data(rbind(data,data[1,]))) &&
      rejects(r6_validate_data(transform(data,split=ifelse(split=="dev","test",split)))),
      "nonfinite features, duplicate pairs and test partitions are rejected")
cat("R6 focused numerical checks: 9 passed\n")
