"""Orbit Wars agent.

Single-file strategy agent for the "Orbit Wars" Kaggle-style environment.
Exposes `agent(obs)` which returns a list of moves `[from_planet_id, angle, ships]`.

Design goals (see TASK.md):
- Robust parsing of dict-style and object-style observations.
- Predictive interception of orbiting planets (target moves while the fleet flies).
- Never launch a fleet on a straight-line path that crosses the Sun (instant death).
- Keep a defensive garrison on planets that have incoming enemy fleets.
"""

import math

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUN_X, SUN_Y = 50.0, 50.0
SUN_RADIUS = 10.0
SUN_SAFETY = 12.0  # avoid passing closer than this to the Sun center
MAX_SPEED = 6.0

# Module-level memory so we can detect which planets are orbiting by comparing
# their positions between consecutive turns (chosen tracking strategy).
# Maps planet id -> (x, y) from the previous observation.
_PREV_POSITIONS = {}


# ---------------------------------------------------------------------------
# Core formula (given by the task, kept exact)
# ---------------------------------------------------------------------------
def get_fleet_speed(ships):
    """Logarithmic fleet speed, capped at MAX_SPEED."""
    if ships <= 1:
        return 1.0
    return 1.0 + (MAX_SPEED - 1.0) * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5


# ---------------------------------------------------------------------------
# Parsing helpers (handle dict-style and object-style obs)
# ---------------------------------------------------------------------------
def _get(obs, key, default):
    if isinstance(obs, dict):
        return obs.get(key, default)
    return getattr(obs, key, default)


class _Planet:
    __slots__ = ("id", "owner", "x", "y", "radius", "ships", "production", "orbiting")

    def __init__(self, row):
        self.id = int(row[0])
        self.owner = int(row[1])
        self.x = float(row[2])
        self.y = float(row[3])
        self.radius = float(row[4])
        self.ships = float(row[5])
        self.production = float(row[6]) if len(row) > 6 else 0.0
        self.orbiting = False  # filled in by _detect_orbits


class _Fleet:
    __slots__ = ("id", "owner", "x", "y", "angle", "from_planet_id", "ships")

    def __init__(self, row):
        self.id = int(row[0])
        self.owner = int(row[1])
        self.x = float(row[2])
        self.y = float(row[3])
        self.angle = float(row[4])
        self.from_planet_id = int(row[5])
        self.ships = float(row[6])


def _parse(obs):
    player = _get(obs, "player", 0)
    angular_velocity = float(_get(obs, "angular_velocity", 0.0) or 0.0)
    raw_planets = _get(obs, "planets", []) or []
    raw_fleets = _get(obs, "fleets", []) or []

    planets = []
    for row in raw_planets:
        try:
            planets.append(_Planet(row))
        except (TypeError, ValueError, IndexError):
            continue

    fleets = []
    for row in raw_fleets:
        try:
            fleets.append(_Fleet(row))
        except (TypeError, ValueError, IndexError):
            continue

    return int(player), angular_velocity, planets, fleets


def _detect_orbits(planets, angular_velocity):
    """A planet is orbiting if its position changed since the previous turn.

    On the first observation (no history) every planet is treated as static and
    refined once a second observation arrives. Position memory is then updated.
    """
    moving_possible = abs(angular_velocity) > 1e-9
    for p in planets:
        prev = _PREV_POSITIONS.get(p.id)
        if prev is not None and moving_possible:
            dx = p.x - prev[0]
            dy = p.y - prev[1]
            if (dx * dx + dy * dy) > 1e-6:
                p.orbiting = True
    # Update memory for next turn.
    _PREV_POSITIONS.clear()
    for p in planets:
        _PREV_POSITIONS[p.id] = (p.x, p.y)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def _dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


def _predict_position(planet, t, angular_velocity):
    """Where a planet will be in `t` turns. Orbiting planets rotate CCW about the Sun."""
    if not planet.orbiting or abs(angular_velocity) < 1e-9:
        return planet.x, planet.y
    r = _dist(SUN_X, SUN_Y, planet.x, planet.y)
    ang = math.atan2(planet.y - SUN_Y, planet.x - SUN_X) + angular_velocity * t
    return SUN_X + r * math.cos(ang), SUN_Y + r * math.sin(ang)


def _path_hits_sun(x0, y0, x1, y1):
    """True if the segment (x0,y0)->(x1,y1) passes within SUN_SAFETY of the Sun."""
    dx, dy = x1 - x0, y1 - y0
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-12:
        return _dist(x0, y0, SUN_X, SUN_Y) < SUN_SAFETY
    # Project Sun center onto the segment, clamped to [0, 1].
    t = ((SUN_X - x0) * dx + (SUN_Y - y0) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    cx = x0 + t * dx
    cy = y0 + t * dy
    return _dist(cx, cy, SUN_X, SUN_Y) < SUN_SAFETY


def _solve_interception(src, target, ships, angular_velocity):
    """Iteratively solve aim angle + ETA for a moving target.

    Returns (angle, eta, hit_x, hit_y). Speed depends on `ships`, and the target
    position depends on travel time, so we fixed-point iterate a few times.
    """
    speed = get_fleet_speed(ships)
    eta = _dist(src.x, src.y, target.x, target.y) / speed
    for _ in range(8):
        px, py = _predict_position(target, eta, angular_velocity)
        new_eta = _dist(src.x, src.y, px, py) / speed
        if abs(new_eta - eta) < 1e-3:
            eta = new_eta
            break
        eta = new_eta
    px, py = _predict_position(target, eta, angular_velocity)
    angle = math.atan2(py - src.y, px - src.x)
    return angle, eta, px, py


# ---------------------------------------------------------------------------
# Threat / force estimation
# ---------------------------------------------------------------------------
def _incoming_threat(planet, fleets, player):
    """Rough estimate of enemy ships heading toward one of our planets.

    Fleets do not expose a destination, so we count enemy fleets whose heading
    points roughly at the planet (within a tolerance) as a threat.
    """
    threat = 0.0
    for f in fleets:
        if f.owner == player:
            continue
        bearing = math.atan2(planet.y - f.y, planet.x - f.x)
        diff = abs(math.atan2(math.sin(bearing - f.angle), math.cos(bearing - f.angle)))
        if diff < 0.30:  # ~17 degrees cone
            threat += f.ships
    return threat


def _required_ships(target, eta, angular_velocity):
    """Ships needed to capture `target` at arrival time (garrison grows by production)."""
    garrison = target.ships + max(0.0, target.production) * eta
    return garrison + 1.0


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------
def agent(obs):
    try:
        player, angular_velocity, planets, fleets = _parse(obs)
        _detect_orbits(planets, angular_velocity)

        my_planets = [p for p in planets if p.owner == player]
        targets = [p for p in planets if p.owner != player]
        if not my_planets or not targets:
            return []

        moves = []
        for src in my_planets:
            reserve = _incoming_threat(src, fleets, player)
            available = int(src.ships - reserve)
            if available <= 0:
                continue

            # Score each reachable target and keep the most efficient one.
            best = None  # (score, angle, ships_to_send)
            for tgt in targets:
                # Try interception sized to the full available force first.
                angle, eta, hx, hy = _solve_interception(src, tgt, available, angular_velocity)
                if _path_hits_sun(src.x, src.y, hx, hy):
                    continue

                needed = _required_ships(tgt, eta, angular_velocity)
                send = int(math.ceil(needed))
                if send < 1 or send > available:
                    continue

                # Re-solve with the actual (smaller) force for a sharper aim.
                angle, eta, hx, hy = _solve_interception(src, tgt, send, angular_velocity)
                if _path_hits_sun(src.x, src.y, hx, hy):
                    continue

                # Prefer high production captured per ship spent, sooner.
                score = (tgt.production + 1.0) / (send * (eta + 1.0))
                if best is None or score > best[0]:
                    best = (score, angle, send)

            if best is not None:
                _, angle, send = best
                moves.append([src.id, float(angle), int(send)])

        return moves
    except Exception:
        # An agent that crashes forfeits the turn; degrade to a safe no-op.
        return []