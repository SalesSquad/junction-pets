# Jev System One as Rokoko L2 shadow supervisor

This is an optional, source-bound TypeSafe Jev experiment alongside the
existing genuine Double-DQN GPU research lane. It does NOT train a model,
control physical motors, replace the safety gate, use a real Smartgloves SDK,
or permit Jev to modify the next MuJoCo motor command.

The harness reads real synthetic MuJoCo observation vectors from ContactEnv
and only submits declared observed numeric features to TypeSafe.
Choice selects one of CONTINUE / REPLAN / REOBSERVE / REQUEST_HUMAN / HALT;
an independent Noul assesses whether new observation or review is needed.
Only the local hard-coded rules decide which advisory label is admitted.

There are 16 predeclared synthetic development cases with seed IDs
120601–120616, of which some are deliberately injected sensor/map faults.
This is not a sealed independent test; GPU test/OOD worlds are untouched.
True object mass, friction, contact forces, reward, and training weights are
never sent to Jev. No secrets are copied to Verda.

Run the offline contract and safety tests on the Mac from the learning folder:

    PYTHONDONTWRITEBYTECODE=1 /tmp/rokoko-m3-venv/bin/python test_jev_shadow.py

Run the bounded real TypeSafe call from the repository root on the
already-authenticated Mac (never in CI, never with a secret in a repo):

    set -a; source "$HOME/.config/typesafe/env"; set +a
    PYTHONDONTWRITEBYTECODE=1 /tmp/rokoko-m3-venv/bin/python \
      solutions/rokoko-teleoperation-gym/learning/jev_shadow.py \
      --live --model jev-latest --max-calls 12 \
      --output solutions/rokoko-teleoperation-gym/learning/results/jev-shadow-20261114.json

The wrapper refuses missing keys, verifies exact Choice and Noul response
types/distributions, fails closed on invalid answers and stops on a provider
error without retrying. The response receipt preserves model version,
token usage, latency, choices, probabilities, rule agreement, overrides
and source hashes, but no authentication material or provider request ids.

A confident Jev suggestion cannot override deadman/space/tracking/HOLD,
and does not modify a DQN learned policy. The Noul value measures the
model's judgment about a question, not an empirical probability of a
safe contact or successful task.

At most 16 single-case requests per run can be admitted. The provider
does not necessarily report a USD charge: never invent a billed amount.
Only a separate, preregistered test with human-reviewed judgments could
support a general decision-quality claim. This is an L2 diagnostic.
