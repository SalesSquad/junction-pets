# Pure selection step for public HomebrewedDB Vision R experiments.
#
# IMPORTANT: A zero-acceptance baseline is not a scientific success. First
# filter ALL candidates against the pre-registered strict calibration
# constraints, THEN rank the eligible candidates. Previously ranking first
# dropped an eligible second-place candidate if first-place had >0 errors.
#
# No train/cal/test data are read here; input contains calibration metrics only.
select_hb_candidate <- function(candidates, baseline, total_cal, known_cal) {
  if (!is.list(candidates) || !length(candidates) ||
      !is.numeric(total_cal) || length(total_cal) != 1L ||
      !is.numeric(known_cal) || length(known_cal) != 1L ||
      !is.finite(total_cal) || !is.finite(known_cal) ||
      total_cal <= 0 || known_cal <= 0 || known_cal > total_cal) {
    stop("Invalid HB calibration selection inputs")
  }
  budget <- floor(.05 * total_cal)
  extract <- function(m) {
    if (!is.list(m) || is.null(m$correctKnown) || is.null(m$wrongTotal) ||
        is.null(m$knownCoverage) ||
        length(m$correctKnown) != 1L || length(m$wrongTotal) != 1L ||
        length(m$knownCoverage) != 1L ||
        !all(is.finite(c(m$correctKnown, m$wrongTotal, m$knownCoverage))) ||
        m$correctKnown < 0 || m$wrongTotal < 0 ||
        m$correctKnown > known_cal || m$wrongTotal > total_cal ||
        m$correctKnown + m$wrongTotal > total_cal ||
        m$knownCoverage < 0 || m$knownCoverage > 1 ||
        abs(m$knownCoverage - m$correctKnown/known_cal) > 1e-6) {
      stop("Invalid or contradictory calibration counts")
    }
    c(correct = as.numeric(m$correctKnown),
      wrong = as.numeric(m$wrongTotal),
      coverage = as.numeric(m$knownCoverage))
  }
  base <- extract(baseline$metrics)
  scores <- t(vapply(candidates, function(candidate) {
    if (is.null(candidate$calibration$metrics))
      stop("Missing calibrated candidate measurements")
    extract(candidate$calibration$metrics)
  }, numeric(3)))
  # All original scientific constraints are preserved:
  # - <= 5% empirical wrong accepts on calibration,
  # - never more wrong accepts than the baseline,
  # - strictly more correct proposals than baseline,
  # - >=20% known-object calibration coverage (avoid zero usefulness).
  eligible <- which(scores[, "wrong"] <= budget &
                    scores[, "wrong"] <= base[["wrong"]] &
                    scores[, "correct"] > base[["correct"]] &
                    scores[, "coverage"] >= .20)
  if (!length(eligible)) {
    return(list(index = 0L, status = "STRICT_BASELINE_FALLBACK",
                eligibleIndices = integer(),
                calibrationWrongBudget = budget))
  }
  ranking <- order(-scores[eligible, "correct"],
                   scores[eligible, "wrong"],
                   eligible)
  list(index = as.integer(eligible[[ranking[[1]]]]),
       status = "SAFE_PARETO_CANDIDATE",
       eligibleIndices = as.integer(eligible),
       calibrationWrongBudget = budget)
}
