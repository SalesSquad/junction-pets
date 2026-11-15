# Rokoko per-action shield — paired MuJoCo evidence

Source CSV: episodes.csv
Actual independent seeds: 100
Actually executed physics episodes: 300
Actual 2ms MuJoCo steps: 698,560
R paired bootstrap resamples, NOT physics: 5000

## Per-policy outcomes

original: 3/100 safe (3.0%, Wilson 95% 1.0–8.5%), unsafe=0, abstain=74, incomplete/timeouts=23
detour: 3/100 safe (3.0%, Wilson 95% 1.0–8.5%), unsafe=0, abstain=18, incomplete/timeouts=79
abstain: 0/100 safe (0.0%, Wilson 95% 0.0–3.7%), unsafe=0, abstain=100, incomplete/timeouts=0

Paired safe-success delta detour minus original: 0.0pp, 95% bootstrap 0.0..0.0pp.

**Interpretation:** fewer abstentions can simply become timeouts, not success.
Do not relax hard deadman/collision checks. Report all unsafe and unresolved.
This is synthetic MuJoCo with uncalibrated object/obstacle dimensions and
no physical Rokoko hardware or real human intervention. No learned RL claim.
The 95% interval is conditional on this synthetic seed distribution.
