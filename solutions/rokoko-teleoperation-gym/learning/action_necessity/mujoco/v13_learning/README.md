# V13 continuation hypothesis — research only

V12 exits its bounded model rescue as soon as either forward option is
mask-legal. On the V12 pilot, 24/40 near V12 episodes abstained; 20 of those
had both forward options masked in their final pre-option mask. A legal mask
alone does not prove a safe route to the goal. This source-only hypothesis
keeps an already-triggered V12 rescue active after forward reopening, to test
whether handing control straight back to V5 ends recovery prematurely.

All original V12 gate parameters, public 18D inputs, original 7-action mask,
model provenance/hash checks, supported actions, one rescue round and maximum
eight rescue options remain in force. The policy returns to reset V5 at the
option limit, within 35 mm of goal, or when no supported legal action exists.
It never chooses unsupported RIGHT4, circumvents a shield mask, uses a hidden
state, learns, or claims reachability. The model is only a one-step ranking
proxy, not a validated planner. Existing V5 goal preservation was established
only for previous gates and data, not for this altered continuation. Longer
intervention can lose baseline wins or cause unsafe physics. No actual V13
physics, improvement, generalization, or safety qualification is claimed.

Evaluation requires exact source-bound independent review, fresh disjoint TRAIN
worlds, same-world V5/V12/V13 comparison and immediate stop on unsafe or lost
V5 goal, full raw retention and independent physics replay. A positive pilot
is not a release; untouched evaluation must be separately designed. No CRACI
integration or dispatch is included in this package.

Run focused contract tests: `python3 -m unittest -v test_policy`.
