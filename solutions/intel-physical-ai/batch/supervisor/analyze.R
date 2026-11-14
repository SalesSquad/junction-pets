#!/usr/bin/env Rscript
# Fixed synthetic fault matrix. Never mistake repeated simulator cases for real trials.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) stop("Usage: Rscript analyze.R <synthetic-cohort.csv>")
data <- read.csv(args[[1]], stringsAsFactors = FALSE, check.names = FALSE)
required <- c("scenario", "case_id", "trip_position", "seed", "evidence",
              "trip_reason", "latched", "blocked_after_trip",
              "baseline_post_trip_software_bowls",
              "supervised_post_trip_software_bowls",
              "baseline_total_sorted", "supervised_total_sorted", "receipt_root")
if (!identical(names(data), required) ||
    nrow(data) != 20L || anyNA(data) ||
    !identical(data$case_id, paste0("case-", seq_len(20L))) ||
    any(data$evidence != "SYNTHETIC_CONTROLLED") ||
    any(!grepl("^[a-f0-9]{64}$", data$receipt_root)) ||
    anyDuplicated(data$receipt_root)) {
  stop("Invalid or incomplete synthetic case matrix/schema")
}
fault_names <- c("GRIP_LOSS", "CAMERA_DISAGREEMENT", "CAMERA_MISSING",
                 "CAPTURE_STALE", "PERCEPTION_LOW_CONFIDENCE",
                 "GLOBAL_OPERATOR_STOP")
expected_faults <- unlist(lapply(fault_names, function(nm)
  paste(nm, c(1L, 3L, 5L), sep = "@")), use.names = FALSE)
faults <- data[data$scenario %in% fault_names, ]
observed_faults <- paste(faults$scenario, faults$trip_position, sep = "@")
if (nrow(faults) != 18L ||
    !identical(sort(observed_faults), sort(expected_faults)) ||
    anyDuplicated(observed_faults) ||
    any(faults$trip_reason != faults$scenario) ||
    any(faults$latched != 1L) ||
    any(faults$blocked_after_trip != 7L - faults$trip_position) ||
    any(faults$supervised_post_trip_software_bowls != 0L) ||
    any(faults$baseline_post_trip_software_bowls > faults$blocked_after_trip)) {
  stop("Fault-family/position or latch evidence malformed")
}
controls <- data[!(data$scenario %in% fault_names), ]
if (nrow(controls) != 2L ||
    !identical(controls$scenario, c("NO_FAULT", "LOCAL_ITEM_STOP")) ||
    any(controls$trip_position != -1L) ||
    any(controls$trip_reason != "NONE") ||
    any(controls$latched != 0L) ||
    any(controls$blocked_after_trip != 0L)) {
  stop("Control scenario coverage malformed")
}
numeric_fields <- c("seed", "latched", "blocked_after_trip",
    "baseline_post_trip_software_bowls",
    "supervised_post_trip_software_bowls",
    "baseline_total_sorted", "supervised_total_sorted")
for (name in numeric_fields) {
  x <- data[[name]]
  if (!is.numeric(x) || any(!is.finite(x)) || any(x < 0) ||
      any(x != floor(x))) stop(paste("Non-integer/negative count:", name))
}
if (any(data$seed > 4294967295) ||
    any(data$baseline_total_sorted > 8L) ||
    any(data$supervised_total_sorted > 8L) ||
    any(data$supervised_total_sorted > data$baseline_total_sorted)) {
  stop("Impossible software outcome counts")
}
summarize <- function(z) data.frame(
  cases = nrow(z),
  baseline_software_bowls_after_trip =
    sum(z$baseline_post_trip_software_bowls),
  supervised_software_bowls_after_trip =
    sum(z$supervised_post_trip_software_bowls),
  blocked_episodes = sum(z$blocked_after_trip),
  lost_sorted_outputs = sum(z$baseline_total_sorted - z$supervised_total_sorted),
  row.names = NULL
)
by_family <- do.call(rbind, lapply(split(faults, faults$scenario),
  function(z) cbind(family = z$scenario[[1]], summarize(z))))
print(by_family, row.names = FALSE, right = FALSE)
cat("\nALL FAULT CASES\n")
print(summarize(faults), row.names = FALSE)
cat("\nCONTROLS\n")
print(controls[,c("scenario","latched","blocked_after_trip")],row.names = FALSE)
cat("\nSCOPE: SYNTHETIC_CONTROLLED fixed scenarios. CSV hashes are untrusted strings unless original full nested receipts are independently replayed.\n")
cat("Inference: no confidence interval, p-value, robot reliability, throughput or safety certification can be estimated from this matrix.\n")
