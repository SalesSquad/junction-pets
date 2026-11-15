# Executed CPU run

Python 3.12; CPU torch; two seeds, eight epochs each. Five unit tests passed. Real Sotkanet API fetch completed. CUDA/full five-seed execution and fresh Ubuntu bootstrap were not exercised on this CPU host; shell syntax was checked.

Selection uses validation MAE pooled across units and horizons. These tables show test MAE. Missing cohorts have null scores and n=0.

## county

| Indicator | Horizon | Transformer | Persistence | Drift | Ridge | n | Chosen |
|---|---|---:|---:|---:|---:|---:|---|
| screen_breast | h1 | 0.7863 | 0.7318 | 0.9508 | 0.8059 | 44 | ridge |
| screen_breast | h2 | 0.8245 | 0.7182 | 1.1424 | 0.8652 | 22 | ridge |
| screen_cervix | h1 | 2.2197 | 1.9609 | 2.1978 | 2.3491 | 46 | ridge |
| screen_cervix | h2 | 3.1489 | 2.8957 | 3.0928 | 3.1666 | 23 | ridge |
| screen_colorectal | h1 | 1.9305 | 1.9273 | 2.7318 | 1.9273 | 44 | persistence |
| screen_colorectal | h2 | 3.7170 | 3.7273 | 3.7273 | 3.7273 | 22 | persistence |
| gp_wait_over_7d | h1 | 6.8185 | 6.8250 | 8.8682 | 6.8250 | 44 | transformer |
| gp_wait_over_7d | h2 | 11.9801 | 11.9864 | 15.9909 | 11.9864 | 44 | transformer |
| gp_wait_over_3m | h1 | 0.5030 | 0.4955 | 0.6284 | 0.4955 | 44 | persistence |
| gp_wait_over_3m | h2 | 1.3013 | 1.2955 | 1.3250 | 1.2955 | 44 | persistence |
| specialist_wait_over_6m | h1 | 14.1720 | 12.6382 | 10.3069 | 23.7544 | 34 | drift |
| specialist_wait_over_6m | h2 | 14.6734 | 15.1686 | 15.0924 | 13.6783 | 35 | drift |
| referral_handled_3d | h1 | 1.5373 | 1.5294 | 2.4529 | 1.7858 | 34 | ridge |
| referral_handled_3d | h2 | 2.9544 | 2.9886 | 5.2438 | 3.0845 | 35 | ridge |
| referral_handled_over_21d | h1 | 0.6065 | 0.5882 | 0.7745 | 0.5809 | 34 | persistence |
| referral_handled_over_21d | h2 | 0.6186 | 0.6000 | 1.0000 | 0.5513 | 35 | persistence |
## municipality

| Indicator | Horizon | Transformer | Persistence | Drift | Ridge | n | Chosen |
|---|---|---:|---:|---:|---:|---:|---|
| screen_breast | h1 | 2.4335 | 2.4981 | 3.1147 | 1.9193 | 584 | ridge |
| screen_breast | h2 | 2.3340 | 2.2462 | 3.1211 | 2.1123 | 292 | ridge |
| screen_cervix | h1 | 4.9171 | 4.9837 | 5.9209 | 4.6558 | 613 | ridge |
| screen_cervix | h2 | 5.5051 | 5.8000 | 7.9344 | 5.4935 | 307 | ridge |
| screen_colorectal | h1 | 3.0490 | 3.0228 | 4.2476 | 3.0228 | 584 | persistence |
| screen_colorectal | h2 | 3.9956 | 3.8647 | 3.8647 | 3.8647 | 292 | persistence |
| gp_wait_over_7d | h1 | 11.9705 | 11.9658 | 17.0813 | 11.9658 | 584 | transformer |
| gp_wait_over_7d | h2 | 15.8261 | 15.8442 | 27.8894 | 15.8442 | 584 | transformer |
| gp_wait_over_3m | h1 | 0.7090 | 0.6524 | 0.9360 | 0.6524 | 584 | persistence |
| gp_wait_over_3m | h2 | 1.3920 | 1.3490 | 2.0144 | 1.3490 | 584 | persistence |
| specialist_wait_over_6m | h1 | — | — | — | — | 0 | drift |
| specialist_wait_over_6m | h2 | — | — | — | — | 0 | drift |
| referral_handled_3d | h1 | — | — | — | — | 0 | ridge |
| referral_handled_3d | h2 | — | — | — | — | 0 | ridge |
| referral_handled_over_21d | h1 | — | — | — | — | 0 | persistence |
| referral_handled_over_21d | h2 | — | — | — | — | 0 | persistence |

Raw/conformal coverage, pinball, validation scores, executed epochs and panel SHA256 are in metrics.json. The selected transformer is not consistently better on held-out test MAE. No indicators were skipped by fetch. No git commands, commits or pushes performed.
