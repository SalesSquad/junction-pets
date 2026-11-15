"""Waypoint functions refactored from owner SO101 lab, 14 Nov 2026. No policy inference."""
import numpy as np
J = 6

def smoothstep(v: float) -> float:
    x = max(0.0, min(1.0, v))
    return x*x*(3-2*x)

def desired_pose(frame: int, seed: int, bounds: np.ndarray):
    # Kinematic setpoint sequence only. NOT a real VLA policy or autonomous grasp.
    poses = np.array([
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.10],
        [0.30, -0.30, 0.45, -0.28, 0.15, 1.30],
        [-0.25, 0.20, 0.32, 0.22, -0.18, 0.15],
        [0.10, -0.45, 0.55, -0.23, 0.35, 0.80],
        [0.35, 0.05, 0.10, 0.25, -0.30, 0.10],
    ], dtype=np.float64)
    s = np.random.default_rng(seed)
    jitter = s.uniform(-0.06, 0.06, size=(len(poses), J))
    jitter[0] = 0.0
    waypoints = np.clip(poses+jitter,bounds[:,0]+0.03,bounds[:,1]-0.03)
    # 4 legs of 45 simulation frames each.
    phase = min(3, frame//45)
    alpha = smoothstep((frame%45)/45.0)
    return waypoints[phase]*(1-alpha)+waypoints[phase+1]*alpha
