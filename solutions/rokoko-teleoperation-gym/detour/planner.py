"""Observed-only conservative configuration-space planner; metres, no physics access."""
import numpy as np

SIGMA = .007
MARGIN = 3 * SIGMA
OBJECT_RADIUS = .020
PUSHER_RADIUS = .012
HALF_WIDTH = .018
GOAL = np.array([.16, 0.])


def healthy(o):
    return (np.shape(o) == (18,) and np.isfinite(o).all() and not o[15]
            and bool(o[10]) and bool(o[11]) and o[8] <= .1 and o[9] >= .8)


def clear(a, b, obstacle, radius):
    """Segment vs inflated box (slab test); touching is rejected."""
    a, b, obstacle = map(lambda x: np.asarray(x, dtype=float), (a, b, obstacle))
    if not all(np.isfinite(x).all() for x in (a, b, obstacle)):
        return False
    if any(not (-.19 + radius <= p[0] <= .29 - radius and
                    abs(p[1]) <= .19 - radius) for p in (a, b)):
        return False
    extent = HALF_WIDTH + radius + MARGIN
    lo, hi = obstacle - extent, obstacle + extent
    enter, leave = 0., 1.
    for axis in range(2):
        delta = b[axis] - a[axis]
        if abs(delta) < 1e-12:
            if a[axis] < lo[axis] or a[axis] > hi[axis]:
                return True
        else:
            t1, t2 = sorted(((lo[axis]-a[axis])/delta, (hi[axis]-a[axis])/delta))
            enter, leave = max(enter, t1), min(leave, t2)
    return enter > leave


def routes(o):
    if not healthy(o):
        return []
    obj, obstacle = o[:2], o[6:8]
    candidates = [[GOAL.copy()]]
    # Two mirrored lanes, at most three intermediate waypoints. Extra 6 mm
    # bounds steering noise; the safety margin itself is never reduced.
    extent = HALF_WIDTH + OBJECT_RADIUS + MARGIN + .006
    for side in (-1, 1):
        lane = obstacle[1] + side * extent
        candidates.append([np.array([obj[0], lane]),
                           np.array([obstacle[0]+extent, lane]),
                           np.array([GOAL[0], lane]), GOAL.copy()])
    feasible = []
    for path in candidates:
        points = [obj, *path]
        if all(clear(a, b, obstacle, OBJECT_RADIUS) for a, b in zip(points, points[1:])):
            feasible.append(path)
    return sorted(feasible, key=lambda path: sum(np.linalg.norm(b-a)
                  for a, b in zip([obj, *path], path)))


def waypoint(o):
    paths = routes(o)
    if not paths:
        return None
    for point in paths[0]:
        if np.linalg.norm(point-o[:2]) > .010:
            return point
    return GOAL.copy()


def desired(o, action, selected_waypoint=None):
    # A path owner can pin a temporary waypoint, preventing sensor-noise lane
    # flipping on each 50Hz decision. Pure planner calls retain legacy behavior.
    goal = np.asarray(selected_waypoint, dtype=float) if selected_waypoint is not None else waypoint(o)
    if goal is None or not np.all(np.isfinite(goal)):
        return None
    obj, p = o[:2], o[2:4]
    v = goal-obj
    v /= max(np.linalg.norm(v), 1e-8)
    lateral = np.array([-v[1], v[0]])
    if action == 0:
        return obj-.041*v
    if action in (1, 2):
        return obj-(.029 if action == 1 else .0275)*v
    if action in (3, 4):
        return obj-.045*v+(.03 if action == 3 else -.03)*lateral
    return p-.035*v


def mask(o, selected_waypoint=None):
    allowed = np.zeros(7, dtype=bool)
    allowed[6] = True
    if not healthy(o):
        return allowed
    for action in range(6):
        target = desired(o, action, selected_waypoint)
        if target is not None:
            allowed[action] = clear(o[2:4], target, o[6:8], PUSHER_RADIUS)
    if np.linalg.norm(o[2:4]-o[:2]) < .029:
        allowed[2] = False
    return allowed


def heuristic(o, allowed, selected_waypoint=None):
    if not allowed[:5].any():
        return 6
    if np.linalg.norm(o[:2]-GOAL) < .02:
        return 5 if allowed[5] else 6
    target = desired(o, 0, selected_waypoint)
    if target is not None and np.linalg.norm(o[2:4]-target) <= .011 and allowed[1]:
        return 1
    # Reposition through the original mirrored approach options when alignment
    # crosses the inflated obstacle; never invent a direct unfiltered target.
    for action in (0, 3, 4):
        if allowed[action]:
            return action
    return 6


class RouteCommitment:
    """Only observed-map waypoints, never future reward or hidden physical data.

    Locks the selected side until the puck reaches its waypoint. It fails
    closed if the *observed* map makes the pinned segment infeasible. It does
    not silently retune or switch lanes when a sensor sample fluctuates.
    """
    def __init__(self, observation):
        candidates = routes(observation)
        self.points = tuple(np.asarray(p, dtype=float).copy()
                            for p in candidates[0]) if candidates else ()
        self.index = 0
        self.advances = 0

    def active(self, observation):
        if not self.points or not healthy(observation):
            return None
        # This is a progression threshold for a geometric training task,
        # NOT the physics/safety success threshold.
        while (self.index < len(self.points)-1 and
               np.linalg.norm(observation[:2]-self.points[self.index]) < .014):
            self.index += 1
            self.advances += 1
        goal = self.points[self.index]
        if not clear(observation[:2],goal,observation[6:8],OBJECT_RADIUS):
            return None
        return goal

    def stage(self):
        return (self.index,self.advances,len(self.points))
