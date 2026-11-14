# SAMA pathway scribe dataset v1

AUDIT WARNING: The stricter same-model audit shows substantial disagreement. This dataset is not qualified as low-noise clinical training truth; inspect the audit and obtain independent review before making extraction-quality claims.

SYNTHETIC ONLY. No real patients, clinicians or patient text. Research artefact, not a medical device.

Ground truth is code-sampled with fixed seed 20261114, nine event types and five entry routes from DATA_COLLECTION.md. Episodes contain 1–4 events in date order within 400 days before notes in 2024–2026, six date forms and 0–2 distractors. Uniform event subsets and broadly stratified date offsets are a language coverage design, not calibrated Finnish disease epidemiology. Nemotron writes Finnish notes; code checks exact date spans and 60–140 words, then Jev checks every event, unlisted events, distractors and the explicit entry route at specified thresholds. All raw probabilities remain cached.

**Pathway order (found after the build).** The sampler (`scribe/sample.py`) uses an older type order, which puts `SPECIALIST_VISIT` before `DIAGNOSIS`; `SPECIALIST_VISIT` before `MDT_DECISION`. `DATA_COLLECTION.md` section 1 now defines the order `SYMPTOM_ONSET_REPORTED <= FIRST_CONTACT <= PHYSICIAN_ASSESSMENT <= REFERRAL_SENT <= REFERRAL_RECEIVED <= DIAGNOSIS <= MDT_DECISION <= SPECIALIST_VISIT <= TREATMENT_START` (`eventlog/schema.py`). Against it, 313 of 2466 accepted episodes (12.7%, about one in 8) contain at least one pair of events dated in reversed order: 211 of 1716 training, 42 of 250 validation, 60 of 500 test. Reversed pairs: DIAGNOSIS dated after SPECIALIST_VISIT: 176; MDT_DECISION dated after SPECIALIST_VISIT: 174 (an episode can have both). Run on this ground truth, `eventlog/validate.py` flags 313 episodes, the same ones, and its strict mode for simulator output rejects every split. The files are left as built because an adapter was trained and scored on them.

A SHA256 of route and canonical events assigns the episode to a split before generation; the builder may transfer whole episodes from test surplus to a validation deficit, recording each transfer. Identical ground truth (route and events) never crosses splits; the same event list with another route can: 7 test and 1 validation notes have the event list of a training note. No personal names requested.

Measured counts, rates, usage and audit:
```json
{
  "counts": {
    "train": 1716,
    "val": 250,
    "test": 500,
    "rejected": 1990
  },
  "whole_episode_split_reassignments": [
    {
      "id": "00011f568b68899c49305a797851166102221011b9de19275341f5a182dbeaf1",
      "from": "test",
      "to": "val"
    }
  ],
  "generated": 4476,
  "duplicate_episode_rows_removed": 20,
  "sampler_quarantined": 1,
  "code_check_failure": {
    "value": 0.0980786416443253,
    "n": 4476,
    "ci95": [
      0.08970707046877444,
      0.10713950701096445
    ]
  },
  "verifier_rejection_given_code_pass": {
    "value": 0.3859301461481298,
    "n": 4037,
    "ci95": [
      0.37102837787025167,
      0.4010487972959349
    ]
  },
  "usage": {
    "teacher_requests": 4500,
    "typesafe_tokens": 6846798,
    "typesafe_requests": 7194,
    "typesafe_reserved": 0
  },
  "date_forms": {
    "month": 1083,
    "days": 1056,
    "weeks": 976,
    "long": 1083,
    "numeric": 1543,
    "no_year": 490
  },
  "typesafe_cost_usd": 0.287565516,
  "audit": {
    "strata": {
      "True": {
        "population": 2466,
        "sampled": 60,
        "strict_disagreements": 43
      },
      "False": {
        "population": 1990,
        "sampled": 60,
        "strict_disagreements": 2
      }
    },
    "accepted_residual_noise_proxy": {
      "value": 0.7166666666666667,
      "n": 60,
      "ci95": [
        0.5923271483560882,
        0.8149317157156729
      ]
    },
    "limit": "Second Jev pass disagreement is a model-based proxy, not independent human label truth. Stricter thresholds and shared-model errors can bias this estimate.",
    "section4_noise_formula_estimate": {
      "teacher_unfaithfulness_e": 0.8283138839018552,
      "catch_fraction_c": 0.5211823460881974,
      "false_rejection_f": 0.08670646159208749,
      "residual": 0.7166666666666667,
      "limit": "Stratified estimates from stricter Jev judgments, not ground truth."
    }
  }
}
```

Limits: synthetic teacher/verifier bias; no clinical validation; the second Jev pass is a correlated, stricter model-based noise proxy, not human truth. Code date detection covers explicit Finnish formats but cannot prove absence of every possible paraphrase. Labels must be confirmed by humans before care use. Training, adapter quality and external-writer generalisation are not established by this dataset.

Defects found after the build (pathway order, split by route, de-duplication, cost field, verifier version, teacher) are listed in ERRATA.md in this directory.
