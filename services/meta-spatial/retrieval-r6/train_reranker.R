#!/usr/bin/env Rscript
# R6 actual train/dev-only optimization. This never calibrates or authorizes.
R6_BASE_FEATURES <- c("f_visual", "f_adapted", "f_text", "f_reverse_rank", "f_density", "f_gap")
R6_OCR_FEATURES <- c("f_ocr_visual_match", "f_ocr_catalog_match", "f_ocr_digit_match", "f_ocr_digit_conflict")
R6_FEATURES <- c(R6_BASE_FEATURES, "f_radio", R6_OCR_FEATURES)
R6_SPLITS <- c("train", "dev")
R6_REGULARIZATION <- c(0.01, 0.1, 1)
R6_ABLATIONS <- list(refit6 = R6_BASE_FEATURES,
  plus_radio = c(R6_BASE_FEATURES, "f_radio"),
  plus_ocr = c(R6_BASE_FEATURES, R6_OCR_FEATURES), plus_both = R6_FEATURES)
R6_BASELINE_MODEL_SHA256 <- "4f6db7b937a244b2a6cdf5298d6087bcd84d01445219882c2b7d041986a3a0b6"

r6_abort <- function(message) stop(message, call. = FALSE)

r6_json_string <- function(value) {
  chars <- utf8ToInt(enc2utf8(value))
  escaped <- vapply(chars, function(ch) {
    if (ch == 34L) return("\\\"")
    if (ch == 92L) return("\\\\")
    if (ch < 32L) return(sprintf("\\u%04x", ch))
    intToUtf8(ch)
  }, character(1))
  paste0('"', paste0(escaped, collapse = ""), '"')
}

r6_json <- function(value) {
  if (is.null(value)) return("null")
  if (is.data.frame(value)) {
    return(r6_json(lapply(seq_len(nrow(value)), function(i) as.list(value[i, ]))))
  }
  if (is.list(value)) {
    keys <- names(value)
    if (!is.null(keys) && length(keys) > 0L && all(nzchar(keys))) {
      entries <- vapply(seq_along(value), function(i) {
        paste0(r6_json_string(keys[i]), ":", r6_json(value[[i]]))
      }, character(1))
      return(paste0("{", paste0(entries, collapse = ","), "}"))
    }
    return(paste0("[", paste0(vapply(value, r6_json, character(1)), collapse = ","), "]"))
  }
  if (length(value) != 1L) return(r6_json(unname(as.list(value))))
  if (is.na(value)) return("null")
  if (is.logical(value)) return(if (value) "true" else "false")
  if (is.numeric(value)) {
    if (!is.finite(value)) r6_abort("Nonfinite numeric value cannot be exported as JSON")
    return(sprintf("%.17g", value))
  }
  if (is.character(value)) return(r6_json_string(value))
  r6_abort("Unsupported JSON value")
}

r6_write_json <- function(value, path) {
  # Always use the same serializer so optional packages cannot change artifacts.
  writeLines(r6_json(value), path, useBytes = TRUE)
}

r6_python <- function(code, args = character()) {
  python <- Sys.which("python3")
  if (!nzchar(python)) r6_abort("Python 3 is required for input admission")
  result <- suppressWarnings(system2(python,
    c("-I", "-c", shQuote(code), vapply(args, shQuote, character(1))),
    stdout = TRUE, stderr = TRUE))
  status <- attr(result, "status")
  if (!is.null(status) && status != 0L) {
    r6_abort(paste("Python admission failed:", paste(result, collapse = "\n")))
  }
  result
}

r6_sha256 <- function(path) {
  code <- paste(
    "import hashlib,sys",
    "h=hashlib.sha256()",
    "with open(sys.argv[1], 'rb') as f:",
    "    for block in iter(lambda:f.read(1048576),b''):h.update(block)",
    "print(h.hexdigest())", sep = "\n")
  result <- r6_python(code, path)
  if (length(result) != 1L || !grepl("^[a-f0-9]{64}$", result)) {
    r6_abort("Invalid file hash result")
  }
  result
}

r6_validate_manifest <- function(path, input) {
  code <- paste(
    "import json,hashlib,sys,re",
    "def pairs(items):",
    "    out={}",
    "    for k,v in items:",
    "        if k in out: raise ValueError('duplicate manifest key')",
    "        out[k]=v",
    "    return out",
    "def bad(x): raise ValueError('nonfinite JSON constant')",
    "def require(ok,why):",
    "    if not ok: raise ValueError(why)",
    "raw=open(sys.argv[1],'rb').read()",
    "m=json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)",
    "require(m.get('schema_version')==1 and m.get('kind')=='meta.r6.actual_candidate_features','manifest kind')",
    "require(m.get('feature_names')==sys.argv[3].split(','),'feature allowlist/order')",
    "require(m.get('counts')=={'train':3313,'dev':727},'full train/dev cohort required')",
    "require(all(m.get('admission',{}).get(k) is True for k in ('family_disjoint','image_hash_disjoint','product_disjoint')),'split admission')",
    "require(m.get('baseline_model_sha256')==sys.argv[4],'frozen baseline model mismatch')",
    "require(re.fullmatch('[a-f0-9]{40}',m.get('source_commit','')) is not None,'feature source commit')",
    "h=hashlib.sha256()",
    "with open(sys.argv[2],'rb') as f:",
    "    for b in iter(lambda:f.read(1048576),b''): h.update(b)",
    "require(h.hexdigest()==m.get('input_sha256'),'candidate CSV hash mismatch')",
    "print(h.hexdigest());print(hashlib.sha256(raw).hexdigest());print(m['source_commit'])", sep="\n")
  values <- r6_python(code, c(path, input, paste(R6_FEATURES, collapse=","), R6_BASELINE_MODEL_SHA256))
  if (length(values) != 3L || any(!grepl("^[a-f0-9]{64}$", values[1:2])) ||
      !grepl("^[a-f0-9]{40}$", values[3])) r6_abort("Invalid manifest admission output")
  list(input_sha256=values[1], manifest_sha256=values[2], feature_source_commit=values[3],
       baseline_model_sha256=R6_BASELINE_MODEL_SHA256,
       consumed_partitions=R6_SPLITS, family_disjoint=TRUE, product_disjoint=TRUE,
       image_hash_disjoint=TRUE, image_admission="source builder; R does not reopen pixels")
}

r6_source_binding <- function(script, commit) {
  code <- paste(
    "import pathlib,hashlib,subprocess,sys",
    "p=pathlib.Path(sys.argv[1]).resolve();commit=sys.argv[2]",
    "def git(*args): return subprocess.check_output(['git','-C',str(p.parent),*args])",
    "assert git('rev-parse','HEAD').decode().strip()==commit, 'source HEAD mismatch'",
    "assert not git('status','--porcelain','--untracked-files=all'), 'clean source required'",
    "root=pathlib.Path(git('rev-parse','--show-toplevel').decode().strip())",
    "raw=p.read_bytes(); assert raw==git('show',commit+':'+p.relative_to(root).as_posix()), 'script bytes differ from commit'",
    "print(hashlib.sha256(raw).hexdigest())", sep="\n")
  result <- r6_python(code, c(script, commit))
  if (length(result) != 1L || !grepl("^[a-f0-9]{64}$", result)) r6_abort("Invalid source binding")
  result
}

r6_query_keys <- function(data) paste(data$split, data$query_id, sep = "\037")

r6_validate_data <- function(data, require_all_splits = TRUE) {
  required <- c("split", "query_id", "query_family", "candidate_id", "candidate_family",
                "label", R6_FEATURES, "baseline_rank", "r4_score")
  if (!is.data.frame(data) || nrow(data) == 0L) r6_abort("Candidate data must be nonempty")
  if (anyDuplicated(names(data))) r6_abort("Duplicate column names")
  missing <- setdiff(required, names(data))
  if (length(missing)) r6_abort(paste("Missing columns:", paste(missing, collapse = ",")))
  for (name in c("split", "query_id", "query_family", "candidate_id", "candidate_family")) {
    data[[name]] <- as.character(data[[name]])
    if (anyNA(data[[name]]) || any(!nzchar(data[[name]])) ||
        any(grepl("[\r\n\t\037]", data[[name]]))) {
      r6_abort(paste("Invalid identifier column", name))
    }
  }
  if (any(!data$split %in% R6_SPLITS)) r6_abort("Unknown split")
  if (require_all_splits && !setequal(unique(data$split), R6_SPLITS)) {
    r6_abort("Both train and dev splits are required")
  }
  for (name in c("label", R6_FEATURES, "baseline_rank", "r4_score")) {
    values <- suppressWarnings(as.numeric(as.character(data[[name]])))
    if (anyNA(values) || any(!is.finite(values))) r6_abort(paste("Nonfinite or nonnumeric", name))
    data[[name]] <- values
  }
  if (any(!data$label %in% c(0, 1))) r6_abort("Labels must be binary")
  if (any(data$label != as.integer(data$query_id == data$candidate_id))) {
    r6_abort("Label disagrees with exact product identity")
  }
  if (any(data$baseline_rank < 1 | data$baseline_rank != floor(data$baseline_rank))) {
    r6_abort("Baseline ranks must be positive integers")
  }
  keys <- r6_query_keys(data)
  if (anyDuplicated(paste(keys, data$candidate_id, sep = "\037"))) {
    r6_abort("Duplicate query/candidate pair")
  }
  groups <- split(seq_len(nrow(data)), keys)
  for (ids in groups) {
    if (length(unique(data$query_family[ids])) != 1L) r6_abort("Query family changes within query")
    if (sum(data$label[ids]) > 1) r6_abort("Multiple exact positives within a query")
    if (length(ids) > 100L) r6_abort("Candidate bound exceeds contract top100")
    if (anyDuplicated(data$baseline_rank[ids])) r6_abort("Duplicate baseline rank within query")
  }
  families <- unique(rbind(
    data.frame(family = data$query_family, split = data$split),
    data.frame(family = data$candidate_family, split = data$split)))
  if (anyDuplicated(families$family)) r6_abort("Family leakage across splits")
  products <- unique(rbind(
    data.frame(product = data$query_id, split = data$split),
    data.frame(product = data$candidate_id, split = data$split)))
  if (anyDuplicated(products$product)) r6_abort("Product identifier leakage across splits")
  identity_families <- unique(rbind(
    data.frame(product = data$query_id, family = data$query_family),
    data.frame(product = data$candidate_id, family = data$candidate_family)))
  if (anyDuplicated(identity_families$product)) r6_abort("Product family identity is inconsistent")
  data
}

r6_row_weights <- function(data) {
  # Equal mass per family, then per query within family, then per candidate row.
  keys <- r6_query_keys(data)
  query_rows <- table(keys)
  unique_queries <- !duplicated(keys)
  family_queries <- table(data$query_family[unique_queries])
  weight <- 1 / (as.numeric(query_rows[keys]) *
                   as.numeric(family_queries[data$query_family]))
  weight / sum(weight)
}

r6_scaler <- function(train, features) {
  x <- as.matrix(train[, features, drop = FALSE])
  weights <- r6_row_weights(train)
  center <- colSums(x * weights)
  centered <- sweep(x, 2L, center, "-")
  scale <- sqrt(colSums(centered^2 * weights))
  constant <- scale < 1e-12
  scale[constant] <- 1
  list(feature_names = features, center = unname(center), scale = unname(scale),
       constant_features = features[constant])
}

r6_transform <- function(data, scaler) {
  features <- scaler$feature_names
  x <- as.matrix(data[, features, drop = FALSE])
  result <- sweep(sweep(x, 2L, scaler$center, "-"), 2L, scaler$scale, "/")
  if (any(!is.finite(result))) r6_abort("Nonfinite standardized feature")
  result
}

r6_pairs <- function(train, x) {
  groups <- split(seq_len(nrow(train)), r6_query_keys(train))
  usable <- groups[vapply(groups, function(ids) sum(train$label[ids]) == 1L &&
                           length(ids) > 1L, logical(1))]
  if (!length(usable)) r6_abort("No trainable positive/negative query pairs")
  family <- vapply(usable, function(ids) train$query_family[ids[1]], character(1))
  family_queries <- table(family)
  differences <- vector("list", length(usable))
  weights <- vector("list", length(usable))
  for (i in seq_along(usable)) {
    ids <- usable[[i]]
    positive <- ids[train$label[ids] == 1]
    negative <- ids[train$label[ids] == 0]
    differences[[i]] <- matrix(x[positive, ], nrow = length(negative),
                              ncol = ncol(x), byrow = TRUE) - x[negative, , drop = FALSE]
    weights[[i]] <- rep(1 / (unname(family_queries[family[i]]) * length(negative)),
                        length(negative))
  }
  difference <- do.call(rbind, differences)
  weight <- unlist(weights, use.names = FALSE)
  weight <- weight / sum(weight)
  list(difference = difference, weight = weight, queries = length(usable),
       families = length(unique(family)), skipped_queries = length(groups) - length(usable),
       pairs = nrow(difference))
}

r6_objective <- function(beta, difference, weight, lambda) {
  score <- drop(difference %*% beta)
  # Stable log(1 + exp(-score)) without overflow or an arbitrary clipped loss.
  loss <- pmax(-score, 0) + log1p(exp(-abs(score)))
  sum(weight * loss) + 0.5 * lambda * sum(beta^2)
}

r6_gradient <- function(beta, difference, weight, lambda) {
  score <- drop(difference %*% beta)
  drop(crossprod(difference, -weight * plogis(-score))) + lambda * beta
}

r6_rank_queries <- function(data, score) {
  if (length(score) != nrow(data) || any(!is.finite(score))) r6_abort("Invalid rank scores")
  groups <- split(seq_len(nrow(data)), r6_query_keys(data))
  summaries <- lapply(groups, function(ids) {
    ranking <- ids[order(-score[ids], data$candidate_id[ids], method = "radix")]
    positive <- which(data$label[ranking] == 1)
    rank <- if (length(positive)) positive[1] else NA_integer_
    top <- ranking[1]
    gap <- if (length(ranking) >= 2L) score[top] - score[ranking[2]] else 0
    data.frame(split = data$split[top], query_id = data$query_id[top],
      query_family = data$query_family[top], candidate_id = data$candidate_id[top],
      exact_correct = data$label[top] == 1,
      family_correct = data$candidate_family[top] == data$query_family[top],
      positive_rank = rank, candidates = length(ids),
      top_score = score[top], gap = gap, confidence = score[top] + gap,
      stringsAsFactors = FALSE)
  })
  output <- do.call(rbind, summaries)
  rownames(output) <- NULL
  output
}

r6_retrieval_metrics <- function(queries) {
  n <- nrow(queries)
  positive <- !is.na(queries$positive_rank)
  ranks <- queries$positive_rank
  rank_mean <- function(k) sum(positive & ranks <= k, na.rm = TRUE) / n
  list(queries = n, families = length(unique(queries$query_family)),
       candidate_recall = mean(positive), missing_positive_queries = sum(!positive),
       recall_at_1 = rank_mean(1), recall_at_5 = rank_mean(5),
       recall_at_10 = rank_mean(10), recall_at_50 = rank_mean(50),
       recall_at_100 = rank_mean(100),
       mrr = sum(1 / ranks[positive]) / n,
       family_recall_at_1 = mean(queries$family_correct))
}

r6_candidate_order <- function(items) {
  order(-vapply(items, function(x) x$dev$recall_at_1, numeric(1)),
        -vapply(items, function(x) x$dev$mrr, numeric(1)),
        vapply(items, function(x) length(x$feature_names), integer(1)),
        -vapply(items, function(x) x$lambda, numeric(1)), seq_along(items), method="radix")
}

r6_fit <- function(data, maxit=250L, full_cohort=TRUE) {
  data <- r6_validate_data(data)
  train <- data[data$split=="train", , drop=FALSE]
  dev <- data[data$split=="dev", , drop=FALSE]
  if (full_cohort) {
    if (length(unique(train$query_id)) != 3313L || length(unique(dev$query_id)) != 727L ||
        any(table(r6_query_keys(data)) != 100L)) r6_abort("Full train/dev top100 rows required")
  }
  if (any(abs(data$f_radio)>1.00001) || any(as.matrix(data[,R6_OCR_FEATURES])<0) ||
      any(as.matrix(data[,R6_OCR_FEATURES])>1)) r6_abort("New feature range violation")
  baseline_queries <- r6_rank_queries(data, data$r4_score)
  baseline_dev <- r6_retrieval_metrics(baseline_queries[baseline_queries$split=="dev",])
  candidates <- list(); winners <- list(); query_tables <- list()
  base_table <- baseline_queries; base_table$method <- "frozen_r4"; base_table$lambda <- NA_real_
  query_tables[[1L]] <- base_table
  for (name in names(R6_ABLATIONS)) {
    features <- R6_ABLATIONS[[name]]
    scaler <- r6_scaler(train, features)
    pair <- r6_pairs(train, r6_transform(train, scaler))
    dev_x <- r6_transform(dev, scaler)
    recipe <- lapply(R6_REGULARIZATION, function(lambda) {
      initial <- rep(0, length(features))
      initial_objective <- r6_objective(initial, pair$difference, pair$weight, lambda)
      initial_gradient <- r6_gradient(initial, pair$difference, pair$weight, lambda)
      fitted <- optim(initial, r6_objective, gr=r6_gradient, difference=pair$difference,
        weight=pair$weight, lambda=lambda, method="BFGS", control=list(maxit=maxit,reltol=1e-10))
      if (fitted$convergence!=0L || any(!is.finite(fitted$par)) || !is.finite(fitted$value))
        r6_abort(paste("Optimization failed",name,lambda))
      weights <- unname(fitted$par)
      dev_metrics <- r6_retrieval_metrics(r6_rank_queries(dev,drop(dev_x %*% weights)))
      trace <- list(convergence=fitted$convergence, initial_objective=initial_objective,
        final_objective=fitted$value, initial_gradient_max_abs=max(abs(initial_gradient)),
        final_gradient_max_abs=max(abs(r6_gradient(weights,pair$difference,pair$weight,lambda))),
        parameter_update_l2=sqrt(sum(weights^2)), parameter_update_observed=any(weights!=0),
        evaluations=as.list(fitted$counts))
      cat(sprintf("OPTIMIZED method=%s lambda=%g pairs=%d objective=%.12g->%.12g update_l2=%.9g dev_rank1=%.9f dev_mrr=%.9f\n",
        name,lambda,pair$pairs,initial_objective,fitted$value,trace$parameter_update_l2,
        dev_metrics$recall_at_1,dev_metrics$mrr))
      flush.console()
      list(method=name, feature_names=features, lambda=lambda, scaler=scaler,
        coefficients=weights, intercept=0, optimization=trace, dev=dev_metrics,
        training=list(rows=nrow(train),queries=length(unique(train$query_id)),
          families=length(unique(train$query_family)),trainable_queries=pair$queries,
          trainable_families=pair$families,skipped_untrainable_queries=pair$skipped_queries,
          pairs=pair$pairs,weighting="equal family, then query, then negative within query"))
    })
    best <- recipe[[r6_candidate_order(recipe)[1L]]]
    all_scores <- drop(r6_transform(data,best$scaler) %*% best$coefficients)
    queries <- r6_rank_queries(data,all_scores); queries$method <- name; queries$lambda <- best$lambda
    best$train <- r6_retrieval_metrics(queries[queries$split=="train",])
    winners[[name]] <- best; query_tables[[length(query_tables)+1L]] <- queries
    candidates <- c(candidates,recipe)
  }
  best <- winners[[r6_candidate_order(winners)[1L]]]
  improves <- best$dev$recall_at_1>baseline_dev$recall_at_1 ||
    (best$dev$recall_at_1==baseline_dev$recall_at_1 && best$dev$mrr>baseline_dev$mrr)
  if (improves) {
    model <- list(kind="ridge_pairwise_logistic", selected_method=best$method,
      feature_names=best$feature_names,scaler=best$scaler,coefficients=best$coefficients,
      intercept=0,regularization=best$lambda)
    score <- drop(r6_transform(data,best$scaler) %*% best$coefficients)
  } else {
    model <- list(kind="frozen_r4_score_passthrough",selected_method="frozen_r4",
      feature_names=list("r4_score"),scaler=list(feature_names=list("r4_score"),center=list(0),scale=list(1),
        constant_features=character()),coefficients=list(1),intercept=0,regularization=NULL)
    score <- data$r4_score
  }
  model <- c(list(schema_version=1L,work_id="META-LENS-R6-VERDA-20261114"),model,
    list(rank_score_is_probability=FALSE,baseline_model_sha256=R6_BASELINE_MODEL_SHA256,
      policy=list(calibrated=FALSE,threshold=NULL,reason="train_dev_only_no_acceptance_calibration"),
      qualification=FALSE,action_authorized=FALSE,physical_identity_verified=FALSE))
  metrics <- do.call(rbind,query_tables); rownames(metrics) <- NULL
  metrics$selected <- metrics$method==model$selected_method
  report <- list(schema_version=1L,work_id="META-LENS-R6-VERDA-20261114",status="trained_research_only",
    consumed_partitions=R6_SPLITS,counts=list(train=length(unique(train$query_id)),dev=length(unique(dev$query_id))),
    rows=list(train=nrow(train),dev=nrow(dev)),feature_names=R6_FEATURES,
    selection=list(method=model$selected_method,baseline_retained=!improves,
      improvement=if (improves) "strict_development_lexicographic_improvement" else "no_development_improvement",
      rule="dev Recall@1, then MRR, then fewer features, then larger ridge; exact tie retains frozen R4",
      baseline_dev=baseline_dev,best_trained_method=best$method,best_trained_dev=best$dev),
    optimizer_candidates=candidates,ablation_selected_models=winners,
    training=list(engine="base R stats::optim BFGS",fits=length(candidates),
      regularization_grid=R6_REGULARIZATION,scaler_fit="training rows only; family/query/row balanced",
      objective="weighted positive-minus-negative logistic loss plus ridge",randomness="none"),
    limitations=c("Development was reused for model selection; this is not fresh confirmation.",
      "Frozen R4 reverse-rank/density features use unlabeled same-split query batches.",
      "No OCR transcription accuracy or foundation-model training is established.",
      "No calibration/test data or acceptance policy fitting is consumed.",
      "Missing positives remain in retrieval denominators and are not injected."),
    qualification=FALSE,action_authorized=FALSE,physical_identity_verified=FALSE)
  predictions <- data.frame(split=data$split,query_id=data$query_id,candidate_id=data$candidate_id,
    rank_score=score,r4_score=data$r4_score,selected_method=model$selected_method,stringsAsFactors=FALSE)
  list(model=model,report=report,predictions=predictions,query_metrics=metrics)
}

r6_main <- function(args=commandArgs(trailingOnly=TRUE)) {
  allowed <- c("--input","--manifest","--output","--source-commit")
  if (length(args)!=8L || !setequal(args[c(1,3,5,7)],allowed)) r6_abort("Require --input --manifest --output --source-commit")
  cli <- setNames(args[c(2,4,6,8)],args[c(1,3,5,7)])
  commit <- cli[["--source-commit"]]
  if (!grepl("^[a-f0-9]{40}$",commit)) r6_abort("Full source commit required")
  output <- cli[["--output"]]
  target <- Sys.readlink(output)
  if (file.exists(output) || (!is.na(target) && nzchar(target))) r6_abort("New output directory required")
  if (!dir.create(output,recursive=TRUE)) r6_abort("Cannot create output directory")
  started <- proc.time()[["elapsed"]]
  script_arg <- grep("^--file=",commandArgs(trailingOnly=FALSE),value=TRUE)
  if (length(script_arg)!=1L) r6_abort("Rscript source path required")
  script <- sub("^--file=","",script_arg)
  result <- tryCatch({
    script_hash <- r6_source_binding(script,commit)
    admission <- r6_validate_manifest(cli[["--manifest"]],cli[["--input"]])
    data <- read.csv(cli[["--input"]],stringsAsFactors=FALSE,check.names=FALSE,
      colClasses="character",na.strings=character())
    fit <- r6_fit(data)
    if (!identical(admission,r6_validate_manifest(cli[["--manifest"]],cli[["--input"]])) ||
        script_hash!=r6_source_binding(script,commit)) r6_abort("Source or input changed during fit")
    provenance <- c(admission,list(source_commit=commit,training_script_sha256=script_hash))
    fit$model$provenance <- provenance; fit$report$provenance <- provenance
    fit$report$execution <- list(R_version=R.version.string,platform=R.version$platform,
      elapsed_seconds=proc.time()[["elapsed"]]-started,provider_inference_calls=0L,
      new_foundation_weights_trained=FALSE,ranking_weights_optimized=TRUE)
    r6_write_json(fit$model,file.path(output,"model.json"))
    write.csv(fit$predictions,file.path(output,"predictions.csv"),row.names=FALSE,na="")
    write.csv(fit$query_metrics,file.path(output,"query_metrics.csv"),row.names=FALSE,na="")
    fit$report$artifacts <- lapply(c("model.json","predictions.csv","query_metrics.csv"),function(name)
      list(path=name,sha256=r6_sha256(file.path(output,name))))
    r6_write_json(fit$report,file.path(output,"report.json"))
    fit
  },error=function(error) {
    r6_write_json(list(schema_version=1L,status="FAILED",error=conditionMessage(error),
      qualification=FALSE,action_authorized=FALSE),file.path(output,"failure.json"))
    stop(error)
  })
  cat(sprintf("R6_TRAINED selected=%s baseline_retained=%s qualification=false\n",
    result$model$selected_method,result$report$selection$baseline_retained))
  invisible(result)
}

if (sys.nframe()==0L) r6_main()
