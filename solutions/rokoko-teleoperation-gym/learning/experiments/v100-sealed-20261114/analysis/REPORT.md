# Rokoko Double-DQN — source-bound MuJoCo evaluation

Recorded actual physics episodes: 3950
Recorded actual solver steps: 10,411,996
R bootstrap samples: 20000 (statistical resampling, NOT physics)

## cal

dqn: 101/200 safe (50.5%, Wilson 95% 43.6–57.4%); 0 unsafe and 35 abstained.
heuristic: 0/200 safe (0.0%, Wilson 95% 0.0–1.9%); 0 unsafe and 31 abstained.
abstain: 0/200 safe (0.0%, Wilson 95% 0.0–1.9%); 0 unsafe and 200 abstained.
## test

dqn: 139/300 safe (46.3%, Wilson 95% 40.8–52.0%); 0 unsafe and 57 abstained.
heuristic: 0/300 safe (0.0%, Wilson 95% 0.0–1.3%); 0 unsafe and 47 abstained.
abstain: 0/300 safe (0.0%, Wilson 95% 0.0–1.3%); 0 unsafe and 300 abstained.
## ood

dqn: 8/150 safe (5.3%, Wilson 95% 2.7–10.2%); 1 unsafe and 125 abstained.
heuristic: 0/150 safe (0.0%, Wilson 95% 0.0–2.5%); 0 unsafe and 115 abstained.
abstain: 0/150 safe (0.0%, Wilson 95% 0.0–2.5%); 0 unsafe and 150 abstained.

## Paired bootstrap vs same-world heuristic

test dqn, strict_success: 46.33 pp (95% interval 40.67 to 52.00 pp)
test dqn, risk: 0.00 pp (95% interval 0.00 to 0.00 pp)
test abstain, strict_success: 0.00 pp (95% interval 0.00 to 0.00 pp)
test abstain, risk: 0.00 pp (95% interval 0.00 to 0.00 pp)
ood dqn, strict_success: 5.33 pp (95% interval 2.00 to 9.33 pp)
ood dqn, risk: -0.67 pp (95% interval -2.00 to 0.00 pp)
ood abstain, strict_success: 0.00 pp (95% interval 0.00 to 0.00 pp)
ood abstain, risk: 0.00 pp (95% interval 0.00 to 0.00 pp)

All successes and unsafe events are SYNTHETIC MuJoCo observations.
One training seed does NOT prove broad RL generalization or hardware safety.
Model, CUDA gradient, source and frozen-test integrity require separate
Python/Git/SHA256 verification. No real Rokoko device or Isaac training.
