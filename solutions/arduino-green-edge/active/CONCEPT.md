# Inference Must Pay Rent — Green Edge M5 research experiment


**EVIDENCE UPDATE — NO_GO for the small-load thesis.** Actual Verda Tesla V100
training exposed large held-out summer/fault occupancy false negatives, while
320 source-pinned paired simulations showed negative net after unmeasured
assumed board power. Preserve the experiment as a failed reference, not a
validated green product. The new Open-Window Heat Sentinel synthetic demo is
under active/window and is not real Arduino inference. See
active/evidence/VERDA_RECEIPT.md for exact receipts and the independent
Opus/Haiku reviews. The original hypothesis below remains historical.
Work J26-PF-ARDUINO-M5-INFERENCE-AUCTION-20261114. Parent source junction-pets M4 `eb7ff4cb7fa6c867ced7d944385b4e0bd08d04c4` / M3 `7aee5bd372fa32fa92306f0db9fab39bd2ca1567`. Sponsor route junction.arduino / arduino / official M356 + T45 (Arduino UNO Q + Modulino and genuine on-device Edge AI, physical prototype required). The project has M1 consent/HOLD/safety core, M2 self-reported meter import, M3 24h paired synthetic twin, M4 R scenario/day statistics. No connected UNO Q, physical sensor, calibrated meter or causal savings yet.

## Differentiated product thesis
A local AI must **earn its own watts before it is allowed to think**. Every potential inference is an investment with a measurable energy cost, expected information value, explicit uncertainty and a **separate independent safety veto**. No AI may assume camera absence means an empty room or infer physical energy savings from a simulation. The AI may ASK FOR INFORMATION, PROPOSE an action, or ABSTAIN; a separate MCU can permit only validated low-voltage demonstration outputs after local consent. A controller cannot trade away a single observed required-service failure in exchange for a large average saving.

The novel contribution is a privacy-first **Sensing Auction + Counterfactual Energy Receipts**: a loop where the model bids a small energy budget for a new frame; if its predicted benefit does not beat incremental cost and risk, the camera remains off and the known safe schedule holds. The LED/Knob/Buzzer physically demonstrate when the sensor requests energy, abstains, or refuses under false-empty/stale input. On official UNO Q, Linux Qualcomm predicts; STM32 handles deterministic local deadlines and physical watchdog, with no facial identity, raw frame transfer or cloud dependency. This is a target architecture, NOT yet implemented hardware.

## Competing experimental hypotheses (falsifiable)
H0: A trained occupancy-probability model on cheap temperature/humidity/time features cannot improve net energy over a credible seasonal schedule once board power, camera duty cycle, sensor dropout, 2-sample corroboration and missed occupied service are penalized. The test must be permitted to ACCEPT H0.
H1: Selective asking (uncertainty/expected-value triggered camera) reduces assumed camera queries vs always-on or a fixed periodic poll WITHOUT increasing independently scored service misses relative to the schedule, on genuinely unseen seed+shift+fault regimes.
H2: The safety shield catches sustained false-empty states that evade naive repeated camera confirmation; if not, the controller MUST refuse deployment.

## Source truth and cost boundary
M3 has synthetic `createDay({scenario,seed,shiftHours,sensorBias})` and `scheduledAction(second,scenario)`. Its 'truth' may be used as a TRAINING LABEL and OFFLINE SCORER ONLY, never at policy inference. Thermo supplies T/RH but NOT occupancy/lux. Use ambient light only in scoring, never in a deployable live policy unless additional calibrated lux source exists. Camera false-negative episodes can be correlated; two frames do NOT guarantee safety. Assume per-inference and standby watts as illustrative, not Arduino measured specs. Model may be optimized with a GPU but **cannot be claimed to run on UNO Q** until actual hardware/SDK execution. Preserve per-seed/day paired comparisons, worst-case misses, false-empty drift and gross/net with energy of the AI itself.

## GPU study
Generate deterministic source-pinned synthetic training/validation/test datasets (separate days and held-out failure/arrival shifts). Fit a small practical PyTorch model on a real existing authorized Verda Tesla V100, no downloaded pretrained weights, no proprietary/private data, no remote credential transfer. Reuse an existing venv read-only; run within the new dollar-20 Verda ceiling and with GPU idle/owner checks. Report CUDA device, epochs, actual source/data SHA, model SHA, heldout false-negative / false-empty OOD performance, inference count vs competitor and net after explicitly assumed energy. A file or CUDA launch alone is not a success. Negative findings are valuable.

## Product-winning pivot if the null wins
If baseline cannot cover the UNO Q's own energy on 40W fan/20W lamp, pivot to a **high-value non-mains-actuating physical DEMO** (e.g., mock compressed air / cold-room load with low-voltage LED controller) and require calibrated field measurements before calling it impact. Sponsor judges value actual on-board inference, physical prototype, creativity and social/environmental benefit; an honest veto and cost ledger is compelling only when proven physically.

## Outside critiques requested
Opus read-only: disprove novelty, physical feasibility/energy economics, benchmark fairness and real contest pitch, propose exactly one better winning concept, a negative test and minimum physical demo. Haiku read-only: enumerate 20 adversarial 'would turn off while occupied' cases and source assumptions; flag must-stop conditions. Neither model can authorize physical outputs, costs, or merge.
