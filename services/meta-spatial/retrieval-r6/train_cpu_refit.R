#!/usr/bin/env Rscript
# Separate CPU-only control experiment. No synthetic OCR/RADIO columns.
cpu_abort <- function(message) stop(message, call.=FALSE)
cpu_python <- function(code,args) {
  python <- Sys.which("python3")
  if (!nzchar(python)) cpu_abort("Python 3 required")
  result <- suppressWarnings(system2(python,c("-I","-c",shQuote(code),vapply(args,shQuote,character(1))),
                                    stdout=TRUE,stderr=TRUE))
  status <- attr(result,"status")
  if (!is.null(status) && status!=0L) cpu_abort(paste(result,collapse="\n"))
  result
}

cpu_admit <- function(prepared,r6_source,baseline_model,runner,commit,prepared_sha) {
  code <- paste(
    "import csv,hashlib,json,math,pathlib,re,subprocess,sys,collections",
    "root,helper,model_path,runner=map(pathlib.Path,sys.argv[1:5]);commit=sys.argv[5];prepared_sha=sys.argv[6]",
    "def need(ok,why):",
    "    if not ok: raise ValueError(why)",
    "def pairs(items):",
    "    out={}",
    "    for k,v in items:",
    "        need(k not in out,'duplicate_json_key');out[k]=v",
    "    return out",
    "def bad(x): raise ValueError('nonfinite_json')",
    "def doc(p): return json.loads(p.read_bytes(),object_pairs_hook=pairs,parse_constant=bad)",
    "def sha(p):",
    "    need(p.is_file() and not p.is_symlink(),'regular_file_required')",
    "    h=hashlib.sha256()",
    "    with p.open('rb') as f:",
    "        for b in iter(lambda:f.read(1048576),b''):h.update(b)",
    "    return h.hexdigest()",
    "need(commit=='8948b44454f1a5dd174395e6d69e1ae8b533688b','source_commit_mismatch')",
    "helper=helper.resolve();repo=pathlib.Path(subprocess.check_output(['git','-C',str(helper.parent),'rev-parse','--show-toplevel']).decode().strip())",
    "committed=subprocess.check_output(['git','-C',str(repo),'show',commit+':'+helper.relative_to(repo).as_posix()])",
    "need(committed==helper.read_bytes(),'helper_source_bytes_mismatch')",
    "need(sha(helper)=='4dcd524d7ea1ab5df2574bffaa6871c26c31c67ed22c00e92619e987e7e29ad5','unexpected_helper_sha')",
    "manifest_path=root/'prepare_manifest.json'",
    "need(re.fullmatch('[0-9a-f]{64}',prepared_sha) and sha(manifest_path)==prepared_sha,'prepared_manifest_anchor_mismatch')",
    "manifest=doc(manifest_path)",
    "need(manifest['schema_version']==1 and manifest['kind']=='meta.r6.prepared_inputs' and manifest['work_id']=='META-LENS-R6-VERDA-20261114' and manifest['counts']=={'train':3313,'dev':727},'prepared_cohort_mismatch')",
    "prepare_rel=(helper.parent/'prepare_inputs.py').relative_to(repo).as_posix()",
    "prepare_source=subprocess.check_output(['git','-C',str(repo),'show',commit+':'+prepare_rel])",
    "need(manifest['source_commit']==commit and manifest['source_sha256']=={'prepare_inputs.py':hashlib.sha256(prepare_source).hexdigest()},'prepared_source_mismatch')",
    "need(manifest['input_hashes']['dataset']=='bd70decf437dd34dfa9e2866c2110b142d7e746ea66c6f1098ac81deb6cac59c' and manifest['input_hashes']['r4_report']=='8eda9a3d532b931bc93a765e555bc9008ce9d3c781d1c9efef583e6db515ca80','prepared_original_input_pins_mismatch')",
    "need(all(manifest['admission'].get(k) is True for k in ('family_disjoint','product_disjoint','image_hash_disjoint')),'prepared_split_admission_missing')",
    "need(manifest['admission']['extracted_partitions']==['train','dev'] and manifest['admission']['cal_test_ood_images_exported']==0,'unexpected_partitions')",
    "candidate_path=root/'train_dev_candidates.csv';truth_path=root/'truth.json'",
    "for p in (candidate_path,truth_path):need(sha(p)==manifest['files_sha256'][p.name],'prepared_file_hash_mismatch')",
    "model_sha=sha(model_path)",
    "need(model_sha==manifest['baseline_model_sha256']=='4f6db7b937a244b2a6cdf5298d6087bcd84d01445219882c2b7d041986a3a0b6','frozen_model_hash_mismatch')",
    "features=['f_visual','f_adapted','f_text','f_reverse_rank','f_density','f_gap']",
    "model=doc(model_path)",
    "need(model['kind']=='ridge_pairwise_logistic' and model['feature_names']==features and model['intercept']==0,'frozen_model_contract_mismatch')",
    "vectors=[model['scaler']['center'],model['scaler']['scale'],model['coefficients']]",
    "need(all(type(v) is list and len(v)==6 and all(type(x) in (int,float) and math.isfinite(x) for x in v) for v in vectors),'invalid_frozen_numeric_model')",
    "need(all(x>0 for x in vectors[1]),'invalid_frozen_scale')",
    "truth_doc=doc(truth_path);truth={};families={}",
    "need(truth_doc['kind']=='meta.r6.train_dev_truth' and truth_doc['source_commit']==commit and truth_doc['source_sha256']==manifest['source_sha256'],'truth_source_mismatch')",
    "for row in truth_doc['records']:",
    "    q,s,f=row['product_id'],row['split'],row['family_id']",
    "    need(q not in truth and s in ('train','dev') and (f not in families or families[f]==s),'truth_identity_or_split_mismatch')",
    "    truth[q]=(s,f);families[f]=s",
    "need(dict(collections.Counter(v[0] for v in truth.values()))=={'train':3313,'dev':727},'truth_count_mismatch')",
    "seen={q:set() for q in truth};ranks={q:set() for q in truth};counts=collections.Counter()",
    "columns=['split','query_id','query_family','candidate_id','candidate_family','label',*features,'baseline_rank','visual_rank','text_rank']",
    "with candidate_path.open(newline='') as stream:",
    "    rows=csv.DictReader(stream);need(rows.fieldnames==columns,'six_feature_csv_contract_mismatch')",
    "    for row in rows:",
    "        need(None not in row and all(v is not None for v in row.values()),'malformed_candidate_row')",
    "        s,q,c=row['split'],row['query_id'],row['candidate_id']",
    "        need(q in truth and c in truth and truth[q]==(s,row['query_family']) and truth[c]==(s,row['candidate_family']),'candidate_truth_mismatch')",
    "        need(row['label'] in ('0','1') and int(row['label'])==int(q==c),'candidate_label_mismatch')",
    "        need(all(math.isfinite(float(row[k])) for k in features),'nonfinite_candidate_feature')",
    "        need(all(re.fullmatch('[1-9][0-9]*',row[k]) for k in ('baseline_rank','visual_rank','text_rank')),'invalid_candidate_rank')",
    "        need(c not in seen[q] and row['baseline_rank'] not in ranks[q] and len(seen[q])<100,'duplicate_or_excess_candidate')",
    "        seen[q].add(c);ranks[q].add(row['baseline_rank']);counts[s]+=1",
    "need(dict(counts)=={'train':331300,'dev':72700} and all(len(v)==100 for v in seen.values()),'incomplete_full_train_dev_pool')",
    "for value in [sha(helper),sha(runner),sha(candidate_path),sha(manifest_path),sha(truth_path),model_sha]:print(value)",
    "for vector in vectors:print(','.join(format(v,'.17g') for v in vector))",
    "print(format(model['regularization'],'.17g'))",sep="\n")
  values <- cpu_python(code,c(prepared,r6_source,baseline_model,runner,commit,prepared_sha))
  if (length(values)!=10L || any(!grepl("^[a-f0-9]{64}$",values[1:6]))) cpu_abort("Invalid admission receipt")
  list(provenance=list(helper_source_commit=commit,helper_source_sha256=values[1],runner_sha256=values[2],
    input_sha256=values[3],prepared_manifest_sha256=values[4],truth_sha256=values[5],baseline_model_sha256=values[6],
    baseline_scores="recomputed from frozen numeric R4 model; no calibration/test rows opened"),
    center=scan(text=values[7],sep=",",quiet=TRUE),scale=scan(text=values[8],sep=",",quiet=TRUE),
    coefficients=scan(text=values[9],sep=",",quiet=TRUE),regularization=as.numeric(values[10]))
}

cpu_main <- function(args=commandArgs(trailingOnly=TRUE)) {
  allowed <- c("--prepared","--r6-source","--baseline-model","--output","--source-commit","--prepared-manifest-sha")
  if (length(args)!=12L || !setequal(args[c(1,3,5,7,9,11)],allowed)) cpu_abort(paste("Require",paste(allowed,collapse=" ")))
  cli <- setNames(args[c(2,4,6,8,10,12)],args[c(1,3,5,7,9,11)])
  output <- cli[["--output"]]; link <- Sys.readlink(output)
  if (file.exists(output) || (!is.na(link)&&nzchar(link))) cpu_abort("New output directory required")
  runner_arg <- grep("^--file=",commandArgs(FALSE),value=TRUE)
  if (length(runner_arg)!=1L) cpu_abort("Rscript runner path required")
  runner <- sub("^--file=","",runner_arg)
  started <- proc.time()[["elapsed"]]
  cat("CPU_REFIT6_ADMISSION: full train/dev, six actual features, no OCR/RADIO inputs\n");flush.console()
  admission <- cpu_admit(cli[["--prepared"]],cli[["--r6-source"]],cli[["--baseline-model"]],runner,
                        cli[["--source-commit"]],cli[["--prepared-manifest-sha"]])
  source(cli[["--r6-source"]],local=TRUE)
  if (!dir.create(output,recursive=TRUE)) cpu_abort("Cannot create output directory")
  result <- tryCatch({
    data <- read.csv(file.path(cli[["--prepared"]],"train_dev_candidates.csv"),colClasses="character",
                     stringsAsFactors=FALSE,check.names=FALSE,na.strings=character())
    for (name in c("label",R6_BASE_FEATURES,"baseline_rank","visual_rank","text_rank")) data[[name]] <- as.numeric(data[[name]])
    train <- data[data$split=="train",,drop=FALSE];dev <- data[data$split=="dev",,drop=FALSE]
    frozen_scaler <- list(feature_names=R6_BASE_FEATURES,center=admission$center,scale=admission$scale,constant_features=character())
    frozen_scores <- drop(r6_transform(data,frozen_scaler)%*%admission$coefficients)
    frozen_queries <- r6_rank_queries(data,frozen_scores)
    baseline <- r6_retrieval_metrics(frozen_queries[frozen_queries$split=="dev",])
    if (baseline$queries!=727L || baseline$recall_at_1!=466/727 || baseline$candidate_recall!=719/727 ||
        baseline$missing_positive_queries!=8L) cpu_abort("Frozen R4 baseline did not reproduce 466/727 and pool 719/727")
    scale <- r6_scaler(train,R6_BASE_FEATURES);pair <- r6_pairs(train,r6_transform(train,scale))
    x <- r6_transform(data,scale);tables <- list();candidates <- list()
    frozen_queries$method <- "frozen_r4";frozen_queries$lambda <- admission$regularization;tables[[1]] <- frozen_queries
    for (lambda in c(0.01,0.1,1)) {
      initial <- rep(0,6);initial_loss <- r6_objective(initial,pair$difference,pair$weight,lambda)
      fit <- optim(initial,r6_objective,gr=r6_gradient,difference=pair$difference,weight=pair$weight,
                   lambda=lambda,method="BFGS",control=list(maxit=250L,reltol=1e-10))
      if (fit$convergence!=0L || any(!is.finite(fit$par)) || !is.finite(fit$value) ||
          fit$value>=initial_loss || !any(fit$par!=0)) cpu_abort("CPU refit optimization failed or did not update weights")
      score <- drop(x%*%fit$par);queries <- r6_rank_queries(data,score)
      method <- paste0("cpu_refit6_lambda_",format(lambda,scientific=FALSE,trim=TRUE))
      queries$method <- method;queries$lambda <- lambda;tables[[length(tables)+1L]] <- queries
      dev_metrics <- r6_retrieval_metrics(queries[queries$split=="dev",])
      item <- list(method=method,lambda=lambda,feature_names=R6_BASE_FEATURES,coefficients=unname(fit$par),
        scaler=scale,intercept=0,train=r6_retrieval_metrics(queries[queries$split=="train",]),dev=dev_metrics,
        optimization=list(convergence=fit$convergence,initial_objective=initial_loss,final_objective=fit$value,
          initial_gradient_max_abs=max(abs(r6_gradient(initial,pair$difference,pair$weight,lambda))),
          final_gradient_max_abs=max(abs(r6_gradient(fit$par,pair$difference,pair$weight,lambda))),
          parameter_update_l2=sqrt(sum(fit$par^2)),parameter_update_observed=TRUE,evaluations=as.list(fit$counts)))
      candidates[[length(candidates)+1L]] <- item
      cat(sprintf("CPU_REFIT6_OPTIMIZED lambda=%g pairs=%d objective=%.12g->%.12g update_l2=%.9g dev_rank1=%.9f dev_mrr=%.9f\n",
        lambda,pair$pairs,initial_loss,fit$value,item$optimization$parameter_update_l2,dev_metrics$recall_at_1,dev_metrics$mrr));flush.console()
    }
    best <- candidates[[r6_candidate_order(candidates)[1L]]]
    improves <- best$dev$recall_at_1>baseline$recall_at_1 ||
      (best$dev$recall_at_1==baseline$recall_at_1 && best$dev$mrr>baseline$mrr)
    selected <- if (improves) best$method else "frozen_r4"
    score <- if (improves) drop(x%*%best$coefficients) else frozen_scores
    query_metrics <- do.call(rbind,tables);rownames(query_metrics) <- NULL
    query_metrics$selected <- query_metrics$method==selected
    paired <- lapply(candidates,function(item) {
      a <- query_metrics[query_metrics$split=="dev" & query_metrics$method==item$method,]
      b <- frozen_queries[frozen_queries$split=="dev",]
      if (!identical(a$query_id,b$query_id)) cpu_abort("Paired query order mismatch")
      list(method=item$method,queries=nrow(a),corrected_errors=sum(a$exact_correct & !b$exact_correct),
        new_errors=sum(!a$exact_correct & b$exact_correct),unchanged_correct=sum(a$exact_correct & b$exact_correct),
        unchanged_incorrect=sum(!a$exact_correct & !b$exact_correct))
    })
    ending <- cpu_admit(cli[["--prepared"]],cli[["--r6-source"]],cli[["--baseline-model"]],runner,
                       cli[["--source-commit"]],cli[["--prepared-manifest-sha"]])
    if (!identical(admission,ending)) cpu_abort("Input or source changed during CPU fit")
    flags <- list(qualification=FALSE,action_authorized=FALSE,physical_identity_verified=FALSE)
    model <- c(list(schema_version=1L,experiment="cpu_refit6_only",kind="ridge_pairwise_logistic",selected_method=selected,
      feature_names=R6_BASE_FEATURES,coefficients=if(improves) best$coefficients else admission$coefficients,
      scaler=if(improves) scale else frozen_scaler,intercept=0,
      regularization=if(improves) best$lambda else admission$regularization,rank_score_is_probability=FALSE,
      policy=list(calibrated=FALSE,threshold=NULL,reason="CPU train/dev control only"),provenance=admission$provenance),flags)
    report <- c(list(schema_version=1L,work_id="META-LENS-R6-VERDA-20261114",experiment="cpu_refit6_only",
      status="cpu_refit6_trained_research_only",consumed_partitions=c("train","dev"),
      counts=list(train=nrow(train)/100,dev=nrow(dev)/100),rows=list(train=nrow(train),dev=nrow(dev)),
      feature_names=R6_BASE_FEATURES,gpu_features_present=FALSE,ocr_features_present=FALSE,provider_inference_calls=0L,
      new_foundation_weights_trained=FALSE,ranking_weights_optimized=TRUE,provenance=admission$provenance,
      training=list(fits=3L,regularization_grid=c(0.01,0.1,1),trainable_queries=pair$queries,
        trainable_families=pair$families,skipped_untrainable_queries=pair$skipped_queries,pairs=pair$pairs,
        weighting="equal family, then query, then negative within query",scaler_fit="train rows only"),
      optimizer_candidates=candidates,baseline_dev=baseline,paired_dev_changes=paired,
      selection=list(method=selected,baseline_retained=!improves,best_trained_dev=best$dev,
        rule="dev Recall@1, then MRR, then larger ridge; exact tie retains frozen R4"),
      execution=list(R_version=R.version.string,elapsed_seconds=proc.time()[["elapsed"]]-started),
      limitations=c("CPU six-feature control only; no NVIDIA image extraction or OCR improvement established.",
        "Reuses historical development data; does not establish accepted coverage or fresh qualification.",
        "Same six-feature hypothesis class as R4; improved performance is not expected merely from refitting.",
        "Missing positives stay in denominators; no candidates are injected.",
        "Frozen R4 reverse-rank and density features use unlabeled same-split query batches.")),flags)
    r6_write_json(model,file.path(output,"model.json"))
    write.csv(data.frame(split=data$split,query_id=data$query_id,candidate_id=data$candidate_id,rank_score=score,
      r4_score=frozen_scores,selected_method=selected),file.path(output,"predictions.csv"),row.names=FALSE,na="")
    write.csv(query_metrics,file.path(output,"query_metrics.csv"),row.names=FALSE,na="")
    report$artifacts <- lapply(c("model.json","predictions.csv","query_metrics.csv"),function(name)
      list(path=name,sha256=r6_sha256(file.path(output,name))))
    r6_write_json(report,file.path(output,"report.json"))
    list(model=model,report=report)
  },error=function(error) {
    r6_write_json(list(status="FAILED",experiment="cpu_refit6_only",error=conditionMessage(error),
      qualification=FALSE,action_authorized=FALSE),file.path(output,"failure.json"));stop(error)
  })
  cat(sprintf("CPU_REFIT6_COMPLETE selected=%s baseline_retained=%s fits=3 qualification=false\n",
    result$model$selected_method,result$report$selection$baseline_retained))
  invisible(result)
}

if (sys.nframe()==0L) cpu_main()
