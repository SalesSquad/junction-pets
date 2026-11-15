"""14+14 URDF joint bounds from official pinned M320 joint_spec.yaml.

Source: https://github.com/zupermiez/aaltonomous-humanoid/blob/36daf5b44dad46b8f448a5124ded7faa9947be1e/aaltonomous/interface/joint_spec.yaml
These are URDF position bounds, NOT complete safety-filter workspace checks.
Left Dex3 order thumb/middle/index, right thumb/index/middle. Do not mirror.
"""
ARM_BOUNDS = (
    (-3.0892, 2.6704), (-1.5882, 2.2515), (-2.618, 2.618),
    (-1.0472, 2.0944), (-1.972222, 1.972222), (-1.61443, 1.61443),
    (-1.61443, 1.61443), (-3.0892, 2.6704), (-2.2515, 1.5882),
    (-2.618, 2.618), (-1.0472, 2.0944), (-1.972222, 1.972222),
    (-1.61443, 1.61443), (-1.61443, 1.61443),
)
HAND_BOUNDS = (
    (-1.047198, 1.047198), (-0.724312, 1.047198), (0.0, 1.745329),
    (-1.570796, 0.0), (-1.745329, 0.0), (-1.570796, 0.0),
    (-1.745329, 0.0), (-1.047198, 1.047198), (-1.047198, 0.724312),
    (-1.745329, 0.0), (0.0, 1.570796), (0.0, 1.745329),
    (0.0, 1.570796), (0.0, 1.745329),
)
assert len(ARM_BOUNDS) == len(HAND_BOUNDS) == 14
