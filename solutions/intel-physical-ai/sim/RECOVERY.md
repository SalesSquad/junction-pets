# Intel source recovery — 15 November 2026

Recovered narrowly onto main-based source without changing the original Macs' worktrees, indexes or branches:

- Mini sim snapshot: `15cda5bc4c5ba87cdfaca44f7047a01bc43eb4ea`, branch `rescue/mini-20261115/Developer/j26-intel-physics-bridge-m8-20261114`. This preserves local commit `a051fa852db8e1e53dbc60f2588e16581c882e62` plus dirty bridge.py, run.py and test_bridge.py.
- MBP R snapshot: `953d875d282466b7e21220c214c88ac7ba446827`, branch `rescue/mbp-20261115/Developer/j26-intel-vision-m7-20261114`. Only the changed `vision/analyze.R` is imported; existing vision source stays on main.

The source bytes match those snapshots, except this recovery note and the README clarification of the recovered hold semantics. Historical evidence.json, historical.json and their hashes are preserved unchanged. They describe earlier bytes: no historical pass is rebound to this recovery. Current Python files parse; a tiny direct Bridge check covers local hold/recovery and global latch only. It is not a physical replay, browser, rendered-camera or hardware qualification. R execution was not repeated.

The Intel owner must finish the source/evidence reconciliation and qualify the changed numerical/replay path using the existing pinned external model/camera fixtures. This recovery is a draft for that owner, not permission to route real hardware. No model/assets or private credentials are imported.
