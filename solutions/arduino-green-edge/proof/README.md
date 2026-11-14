# Green Edge Proof Lab — rigorous methods without invented qualification

Scope: Arduino main M356 + technology T45, sponsor route `partnerEvidenceKey=arduino`.
This is **M4 off-board statistical evaluation** stacked on [M3](../sim/engine.mjs)
at source `7aee5bd372fa32fa92306f0db9fab39bd2ca1567`. It does not replace
the [M1 runtime policy](../core.mjs), the [M2 independent meter validator](../measurement.mjs)
or the [M3 paired simulated twin](../sim/engine.mjs).

## Why a sophisticated model is not enough

An arbitrary AI policy can look green by depriving the user of service.
A digital twin can look precise while assuming a camera costs a constant 4 W and
that the fan changes no room conditions. Synthetic paired simulation is useful for
finding bad ideas; **it cannot establish physical energy savings, real-world model
calibration or causal effects**. The sponsor's real device and edge AI criteria
remain unmet until a licensed, pinned model runs on an actual UNO Q.

Our research direction is **Proof-Carrying Green Control**:
1. **Conservative safety shield:** real-time MCU rejects stale/no-consent or
   implausible inputs; Linux model proposes rather than actuating. Never map a
   synthetic M1 `HOLD/action:null` to physical OFF. Real actuator fallback and
   hardware watchdog must be separately safety-qualified.
2. **Energy-aware active sensing (proposal, not implemented):** run vision and
   expensive inference only when expected reduction in *service-error cost plus
   load energy* exceeds **measured incremental compute/sensor cost**. If
   uncertain or drifting, request a fresh observation/hold and surface it,
   rather than guessing "empty". A verified on-device loop must measure the
   actual power-vs-inference-rate curve; it cannot assume Linux sleep works.
3. **Conformal risk control (research, not yet implemented):** calibrate the
   false-empty / missed-service risk on independently held-out days. Its
   exchangeability/monotone-loss assumptions do not automatically hold in
   time-correlated, shifted real rooms. Calibration is not a safety certificate
   for unknown users, hardware or scene distribution shifts.
4. **Robust tails instead of cherry-picked averages:** R computes signed net
   energy, worst day, bottom 10% CVaR, scenario-specific extra unmet service,
   fallback and day-level exact binomial upper bounds. Do not count 8,640
   ten-second slots as independent trials. Select an engineering candidate on
   calibration ONLY; report untouched held-out strata including faults.
5. **Randomized physical switchback proof:** alternate baseline and edge
   controller in *prospectively randomized, comparable* time blocks. Exclude
   predeclared washout and separately meter baseline, switched load and
   device/inference power. Keep every failed trial. The 2026 Applied Energy
   result about accuracy is evidence for this design, **not proof of savings
   for Green Edge**.

## Reproducible R experiment (R 4.1+, Node 22+, no external packages)

From `solutions/arduino-green-edge`:

```sh
node proof/generate.mjs --days=12 > /tmp/green-synthetic-days.csv
Rscript proof/analyze.R /tmp/green-synthetic-days.csv > /tmp/green-risk-summary.csv
Rscript proof/switchback.R plan 12 > /tmp/green-planned-randomization.csv
```

`generate.mjs` calls the **unchanged M3 policy** on 96 source-pinned synthetic
days: 12 calibration + 12 unseen-seed held-out days for each of winter,
summer, evening and fault. Sources are mutually exclusive by seed; each
simulated **day** is one descriptive unit. A SHA-256 of the deterministic CSV
is printed to stderr. It does not fetch external sensor data.

`analyze.R` refuses a changed source pin, non-synthetic evidence labels,
duplicate days, partition leakage, invalid energy arithmetic and missing
seasons. It reports 0/4/8/12/30 W device assumptions for each of eight
season/partition cells, with worst/mean/CVaR net energy, descriptive
day-bootstrap lower mean bound, exact **one-sided Bonferroni-adjusted**
Clopper–Pearson upper extra-service escape probability, fallback, and both
absolute and relative service losses. The 5% service target is **an authored
hypothesis, not a sponsor or formal safety standard**.

At 12 *independently sampled* days per stratum, even **zero** day-level
escapes gives a simultaneous 95% upper risk bound of about **30.6%** under
the binomial model: 12 is insufficient to qualify a 5% target. With zero
observed escapes, **86** independent days per season would be needed just
to move that particular four-season upper bound below 5%; changed
distribution and dependence invalidate that simple guarantee. Here all
days are synthetic, so even 86 would not establish physical-world risk.
Every row prints `statistically_qualified=FALSE` and
`physical_measurement=FALSE`, without exception.

### Prospective physical experiment contract

`Rscript proof/switchback.R plan 12` writes **PLANNED_NOT_EXECUTED**
balanced A/B pair orders with a **hypothetical** 60-minute block and
15-minute washout. Choose actual block/washout length from observed
dynamics before running a trial; the plan does not turn itself into
physical consent or randomized intervention.

If operators later collect period-level readings, `switchback.R analyze
observed.csv` accepts **only**
`pair_id,period_in_pair,assigned_strategy,load_kwh,device_kwh,
missed_service_seconds,duration_seconds,source_class`
with one SCHEDULE and one EDGE record per same-duration pair, and
`source_class=USER_SUPPLIED_UNVERIFIED`. It returns the *conditional*
paired net difference, 95% nominal paired-t interval and a within-pair
sign-flip p-value (exact up to 15 pairs). Actual randomization, calibration,
allocation of logging/board power, washout, carryover and missing data **are
not authenticated by a CSV**; all output remains unverified and not a
physical or causal claim. A daily timer's failure to provide service
cannot be canceled by another day's aggregate improvement.

## What to build physically: smallest honest competition demonstration

Arduino's official UNO Q has a Linux/Qualcomm application processor plus an
STM32 real-time MCU connected by Bridge; App Lab provides camera/AI Bricks.
The event kit lists UNO Q 2 GB, USB camera, Modulino Thermo, Knob, Buzzer;
the **Thermo measures temperature and humidity**, not occupancy or lux.
A USB camera with a *licensed and pinned* on-device person classifier can
produce a coarse **local-only aggregate occupancy estimate** (no recorded
faces or images); it is not an occupancy sensor guarantee. Image brightness
is not calibrated lux. Use Knob for explicit operator confirmation/override,
LED matrix + Buzzer for physically visible HOLD / TEST / PROPOSE states,
not actual mains control without independent interlock and power hardware.

Physical acceptance sequence:
1. Verify actual borrowed UNO Q, approved use, installed App Lab version
   and selected camera/person classifier Brick, then record model hash,
   latency and failure/dropout behavior with Wi-Fi unplugged.
2. Benchmark different inference duty cycles (always-on vs uncertain-only)
   **at the wall/device meter** and report energy + missed-service trade-offs.
   Safety fallback stays on the MCU and cannot depend on Linux scheduling.
3. Add a **separately calibrated and safely isolated** meter for baseline,
   switched load and board overhead. Use compatible low-voltage loads,
   no unapproved mains switching. Demonstrate Buzzer/Knob/LED response.
4. Execute prospectively logged A/B blocks with actual independent
   conditions and consent, physical power readings and a washout plan.
   No single-room 24-hour synthetic replay is experimental proof.
5. Show the sponsor the **negative counterexample**, not only positive
   gain: 4 W looks positive in M3 fault replay but returns
   NOT_RECOMMENDED because it degrades required service.
6. Publish the complete physical demo and measurements only through the
   authorized FINAL controller. Arduino Project Hub and Junction Platform
   submissions are separate official requirements and **remain undone**.

### Research sources / provenance

- Arduino UNO Q hardware split and Bridge:
  https://docs.arduino.cc/hardware/uno-q
- Official Modulino Thermo HS3003 temperature/humidity:
  https://docs.arduino.cc/hardware/modulino-thermo
- Official App Lab / Edge Impulse model training:
  https://blog.arduino.cc/2026/03/04/train-and-deploy-your-own-ai-models-in-arduino-app-lab-now-fully-integrated-with-edge-impulse/
- Arduino person classifier with LED matrix, source example:
  https://github.com/arduino/app-bricks-examples
- Angelopoulos et al. (ICLR 2024), Conformal Risk Control:
  https://proceedings.iclr.cc/paper_files/paper/2024/hash/f3549ef9b5ff520a7e41ff3cc306ab2b-Abstract-Conference.html
- Zou et al. (Applied Energy 2026), Randomized switchback measurement
  and verification, 639-building reference study:
  https://doi.org/10.1016/j.apenergy.2026.127784
- Junction official M356 + T45 and 2026-11-14 sponsor catalog:
  `../../../docs/challenge-research/current-source-catalog.json`

**Statistical guarantees in the papers do not transfer to this prototype
without satisfying their assumptions. No sponsor credential, device,
App Lab installation, external model inference, measured carbon
saving, Edge AI approval or physical deployment is implied here.**
