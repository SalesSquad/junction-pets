# Architecture

    glove stream ──> closure per digit ──> fingertip retargeting ──> Shadow Hand actuators ──> MuJoCo contact forces
    (rokoko_v3.py     (glove.py Glove)      (glove.py LUT from         (hand.py, lab.py)          │
     or simulated)                           scaled knuckle→tip vectors)                           ▼
                           ▲                                                      tactile model (lab.Tactile, noisy)
                           └──────── operator force feedback / hand-side limiter / slip reflex ◄──┘

- `hand.py` — scene loading, per-finger contact force readout, actuator saturation, `max_effort`.
- `glove.py` — simulated human hand and glove stream; per-finger scaled-vector retargeting to the robot.
- `rokoko_v3.py` — Rokoko Studio Live JSON v3 parser (UDP or file) producing the same closure signal.
- `lab.py` — scenarios and recorder (force-coloured fingers, contact-force arrows, operator skeleton data).
- `tasks.py` — carriage-mounted lift/carry/tilt task.
- `exp.py` — batch experiments (feedback trials, friction sweep, behaviour cloning).
- `build_site.py` + `template.html` — static demo page.

External source: MuJoCo Menagerie `shadow_hand` at commit `370c43965323c0944b433b202aac5058b5f907a9`
(Apache-2.0), fetched by `setup_model.py`, not vendored. No shared service, schema or contract is touched.
