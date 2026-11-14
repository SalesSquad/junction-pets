#!/usr/bin/env Rscript
# Deterministic safety-latch case matrix. This is not an i.i.d. sample of robot runs.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) stop("Usage: Rscript analyze.R <synthetic-cohort.csv>")
data <- read.csv(args[[1]], stringsAsFactors = FALSE, check.names = FALSE)
required <- c("scenario", "case_id", "trip_position", "seed", "evidence",
              "trip_reason", "latched", "blocked_after_trip",
              "baseline_post_trip_software_bowls",
              "supervised_post_trip_software_bowls",
              "baseline_total_sorted", "supervised_total_sorted", "receipt_root")
if (!identical(names(data), required)) stop("Unexpected source schema")
if (nrow(data) != 20L || anyDuplicated(data$case_id) ||
    anyNA(data) || any(data$evidence != "SYNTHETIC_CONTROLLED") ||
    any(!grepl("^[a-f0-9]{64}$", data$receipt_root))) {
  stop("Expected exactly 20 complete distinct synthetic case receipts")
}
faults <- data[data$scenario %in% c("GRIP_LOSS", "CAMERA_DISAGREEMENT",
    "CAMERA_MISSING", "CAPTURE_STALE", "PERCEPTION_LOW_CONFIDENCE",
    "GLOBAL_OPERATOR_STOP"), ]
if (nrow(faults) != 18L ||
    !identical(sort(unique(faults$trip_position)), c(1L,3L,5L)) ||
    any(faults$latched != 1L) ||
    any(faults$supervised_post_trip_software_bowls != 0L) ||
    any(faults$blocked_after_trip != 7L - faults$trip_position) ||
    any(faults$supervised_total_sorted > faults$baseline_total_sorted)) {
  stop("A mandatory interlock or cohort invariant failed")
}
controls <- data[data$scenario %in% c("NO_FAULT", "LOCAL_ITEM_STOP"), ]
if (nrow(controls) != 2L || any(controls$latched != 0L) ||
    any(controls$blocked_after_trip != 0L)) stop("Local/no-fault semantics changed")

summarize <- function(z) {
  data.frame(
    cases = nrow(z),
    baseline_software_bowls_after_trip = sum(z$baseline_post_trip_software_bowls),
    supervised_software_bowls_after_trip = sum(z$supervised_post_trip_software_bowls),
    blocked_episodes = sum(z$blocked_after_trip),
    lost_sorted_outputs = sum(z$baseline_total_sorted - z$supervised_total_sorted),
    row.names = NULL
  )
}
by_family <- do.call(rbind, lapply(split(faults, faults$scenario), function(z) {
  cbind(family = z$scenario[[1]], summarize(z), row.names = NULL)
}))
print(by_family, row.names = FALSE, right = FALSE)
cat("\nALL FAULT CASES\n")
print(summarize(faults), row.names = FALSE)
cat("\nCONTROLS\n")
print(controls[,c("scenario","latched","blocked_after_trip")], row.names = FALSE)
cat("\nSCOPE: SYNTHETIC_CONTROLLED fixed scenarios; no random independent trials.\n")
cat("Inference: no confidence interval, p-value, robot reliability, throughput or safety certification can be estimated from this matrix.\n")
