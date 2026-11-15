# Hand Force Lab — glove-teleoperated robot hand with measured forces

**Status: simulation prototype. No Rokoko hardware, SDK or sponsor data has been used.** Rokoko challenge
(The Robot Teleoperation Challenge), agent `junction.rokoko`. This workspace is separate from
`solutions/rokoko-teleoperation-gym/` (MotionBridge Studio and the CRACI MuJoCo pusher experiments) and does not
change it.

## What it shows

A Shadow Hand (MuJoCo Menagerie model, torque limits unchanged) is driven by a glove stream through fingertip
retargeting. Every force is a contact force computed by MuJoCo 3.3.7.

| Scenario | Result in the committed run |
| --- | --- |
| Power grip on a fixed 38 mm bar | 93 N steady, 154 N peak (published human norm for men 20–24: about 538 N) |
| Thumb–index pinch on a gauge | 26 N (human norm about 80 N) |
| Fragile object, three ways | no feedback: 15.7 N peak, breaks at the 15 N demo limit; operator force feedback: 5.2 N; hand-side limiter: 3.0 N |
| Slip reflex under a rising pull | constant grip slips at 11 N, shear-sensing reflex at 25 N |
| Lift, carry, tilt, place a free 300 g bottle | lifted 78 mm, carried 89 mm, tilted 57°, set down upright |

Batch results in `results/`: operator feedback trials (12 per mode: 6/12 broken without feedback, 0/12 with
feedback, 0/12 with the limiter), friction sweep 0.5–1.0 with noisy tactile sensors, and a behaviour-cloned grip
policy that reached the target force on 12/12 unseen bar sizes and targets.

`site/index.html` is the demo page (videos, live per-finger forces, operator hand view, audio feedback toggle).
Serve the folder with `python3 -m http.server` and open it.

## Run

    pip install -r requirements.txt
    python3 setup_model.py                 # fetches the pinned Menagerie Shadow Hand, builds the carriage variant
    python3 rokoko_v3.py                   # adapter self-test, writes sample_stream_v3.jsonl (simulated)
    python3 teleop_replay.py               # drive the hand from that stream file
    python3 teleop_replay.py --udp 14043   # drive it from a live Rokoko Studio custom stream (JSON v3, uncompressed)
    NORENDER=1 python3 lab.py grip pinch fragile slip cup   # scenarios without video
    MUJOCO_GL=osmesa python3 lab.py cup    # with video into out/
    python3 exp.py feedback friction learn # batch experiments into results/
    python3 build_site.py                  # rebuild site/index.html from out/ and results/

## Limits — read before quoting numbers

- The glove is simulated: a kinematic human hand, 60 Hz, 35 ms latency, 0.8° joint noise, 9 Hz tremor.
- The operator is a model, not a person. Without feedback it over-closes past contact by a random amount; with
  feedback it reacts to force with 180 ms delay and 10 % perception noise. These are assumptions.
- `rokoko_v3.py` follows Rokoko's public JSON v3 description but has only been tested on frames it generates itself.
  Finger joint key names must be confirmed on a real stream.
- The "arm" is a 6-axis position-controlled carriage, not a robot arm model.
- Pinch uses a pre-found robot pinch pose driven by glove closure; fingertip retargeting alone did not press hard enough.
- In the lift task the grip force pulses between about 10 and 45 N (force loop interacting with glove latency).
- Slip numbers vary by about a third between seeds. Friction 1.0 and the 15 N break limit are demo assumptions.
- The learned policy is cloned from a scripted force controller on one task, not from human demonstrations.
- Human strength figures are published norms (Mathiowetz et al. 1985), not measured here.
- The robot hand reaches roughly a fifth of human grip strength. The claim is force sensing and control, not strength.
