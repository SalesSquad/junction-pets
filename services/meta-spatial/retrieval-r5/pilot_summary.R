#!/usr/bin/env Rscript
# Independent descriptive arithmetic for the eight-case R5 development pilot.
# No population inference, acceptance calibration, OCR accuracy, or model fit.
# Provenance and frozen-family admission belong to the upstream evaluator.

require_ok <- function(ok, message) {
  if (length(ok) != 1L || is.na(ok) || !ok) stop(message, call. = FALSE)
}

summarize_pilot <- function(input) {
  lanes <- c("ocr", "visual", "detail", "critic")
  columns <- c("lane", "case_id", "baseline_correct", "truth_in_top3",
               "valid_observation", "rank1_correct", "proposed",
               "proposal_correct", "ocr_observed_text")
  require_ok(file.exists(input) && !dir.exists(input), "input_file_required")
  require_ok(file.info(input)$size <= 1048576, "bounded_input_required")
  before <- readBin(input, "raw", n = 1048577L)
  require_ok(length(before) <= 1048576L, "bounded_input_required")
  d <- read.csv(text = rawToChar(before), colClasses = "character", stringsAsFactors = FALSE,
                check.names = FALSE, na.strings = character(), strip.white = FALSE)
  require_ok(nrow(d) == 32L && length(names(d)) == length(columns) &&
               setequal(names(d), columns), "exact_32_row_input_contract_required")
  require_ok(!anyNA(d) && all(d$lane %in% lanes) &&
               all(grepl("^q[0-9]{4}$", d$case_id)), "invalid_case_or_lane")
  ids <- sort(unique(d$case_id))
  require_ok(length(ids) == 8L && !anyDuplicated(d[c("lane", "case_id")]) &&
               all(vapply(lanes, function(lane) setequal(d$case_id[d$lane == lane], ids),
                          logical(1))), "eight_complete_lane_case_pairs_required")
  flags <- setdiff(columns, c("lane", "case_id"))
  for (name in flags) {
    required <- if (name == "ocr_observed_text") d$lane == "ocr" else
      if (name %in% c("rank1_correct", "proposed", "proposal_correct")) d$lane != "ocr" else
        rep(TRUE, nrow(d))
    require_ok(all(d[[name]][required] %in% c("0", "1")) &&
                 all(d[[name]][!required] == ""), paste0("invalid_boolean_or_role_field:", name))
    values <- rep(NA_integer_, nrow(d))
    values[required] <- as.integer(d[[name]][required])
    d[[name]] <- values
  }
  for (name in c("baseline_correct", "truth_in_top3")) {
    require_ok(all(vapply(split(d[[name]], d$case_id), function(x) length(unique(x)) == 1L,
                         logical(1))), paste0("inconsistent_case_truth:", name))
  }
  require_ok(all(d$baseline_correct <= d$truth_in_top3), "baseline_outside_candidate_pool")
  r <- d[d$lane != "ocr", ]
  require_ok(all(r$rank1_correct <= r$valid_observation & r$rank1_correct <= r$truth_in_top3 &
                 r$proposed <= r$valid_observation &
                 r$proposal_correct == r$proposed * r$rank1_correct),
             "inconsistent_ranking_or_proposal_flags")
  o <- d[d$lane == "ocr", ]
  require_ok(all(o$ocr_observed_text <= o$valid_observation), "text_without_valid_observation")
  result <- do.call(rbind, lapply(lanes, function(lane) {
    x <- d[d$lane == lane, ]
    n <- nrow(x); valid <- x$valid_observation == 1L
    ranking <- lane != "ocr"
    correct <- if (ranking) sum(x$rank1_correct) else NA_integer_
    proposed <- if (ranking) sum(x$proposed) else NA_integer_
    proposal_correct <- if (ranking) sum(x$proposal_correct) else NA_integer_
    baseline <- sum(x$baseline_correct)
    data.frame(
      lane = lane, all_queries = n,
      baseline_rank1_correct = baseline, baseline_rank1_rate = baseline / n,
      candidate_recall_at_3_correct = sum(x$truth_in_top3),
      candidate_recall_at_3_rate = sum(x$truth_in_top3) / n,
      valid_observations = sum(valid), valid_response_rate = sum(valid) / n,
      operational_missing_or_failed = sum(!valid),
      rank1_correct_all_queries = correct, rank1_rate_all_queries = correct / n,
      rank1_wrong_observed = if (ranking) sum(valid) - correct else NA_integer_,
      proposed_cases = proposed, correct_proposals = proposal_correct,
      wrong_proposals = proposed - proposal_correct,
      proposal_coverage_descriptive = proposed / n,
      proposal_precision_descriptive = if (ranking && proposed > 0L) proposal_correct / proposed else NA_real_,
      model_abstentions = if (ranking) sum(valid & x$proposed == 0L) else NA_integer_,
      total_no_proposal = if (ranking) n - proposed else NA_integer_,
      ocr_observed_text_cases = if (!ranking) sum(x$ocr_observed_text) else NA_integer_,
      ocr_observed_text_rate = if (!ranking) sum(x$ocr_observed_text) / n else NA_real_,
      ocr_no_legible_text_cases = if (!ranking) sum(valid & x$ocr_observed_text == 0L) else NA_integer_,
      paired_valid_cases = if (ranking) sum(valid) else NA_integer_,
      paired_wins = if (ranking) sum(valid & x$baseline_correct == 0L & x$rank1_correct == 1L) else NA_integer_,
      paired_losses = if (ranking) sum(valid & x$baseline_correct == 1L & x$rank1_correct == 0L) else NA_integer_,
      paired_both_correct = if (ranking) sum(valid & x$baseline_correct == 1L & x$rank1_correct == 1L) else NA_integer_,
      paired_both_wrong = if (ranking) sum(valid & x$baseline_correct == 0L & x$rank1_correct == 0L) else NA_integer_,
      rank1_delta_all_queries = if (ranking) (correct - baseline) / n else NA_real_,
      qualification = FALSE, action_authorized = FALSE,
      stringsAsFactors = FALSE, check.names = FALSE
    )
  }))
  require_ok(identical(before, readBin(input, "raw", n = 1048577L)), "input_changed_during_summary")
  result
}

main <- function() {
  args <- commandArgs(trailingOnly = TRUE)
  if (identical(args, "--help")) {
    cat("Rscript pilot_summary.R --input frozen_pilot.csv --output new_lane_summary.csv\n")
    return(invisible(NULL))
  }
  require_ok(length(args) == 4L && setequal(args[c(1L, 3L)], c("--input", "--output")),
             "usage: --input FILE --output NEW_FILE")
  cli <- setNames(args[c(2L, 4L)], args[c(1L, 3L)])
  input <- cli[["--input"]]; output <- cli[["--output"]]
  target <- Sys.readlink(output)
  require_ok(!file.exists(output) && (is.na(target) || !nzchar(target)) && dir.exists(dirname(output)),
             "new_output_in_existing_directory_required")
  result <- summarize_pilot(input)
  require_ok(!file.exists(output), "output_already_exists")
  write.csv(result, output, row.names = FALSE, na = "")
  cat("DESCRIPTIVE_ONLY: 8 development cases; 4 roles; qualification=false\n")
}

if (sys.nframe() == 0L) main()
