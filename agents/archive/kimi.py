import math

# -----------------------------------------------------------------------------
# CONSTANTS (derived from official environment source)
# -----------------------------------------------------------------------------
SUN_X = 50.0
SUN_Y = 50.0
SUN_RADIUS = 10.0
BOARD_SIZE = 100.0
ROTATION_RADIUS_LIMIT = 50.0   # planets with orbital_radius + planet_radius < 50 orbit
MAX_FLEET_SPEED = 6.0
MAX_INTERCEPTION_TURNS = 100


# -----------------------------------------------------------------------------
# PHYSICS / PARSING HELPERS
# -----------------------------------------------------------------------------
def _getattr_or_item(obj, key, idx, default):
    """Safely read from a dict-like or object-like observation field."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    # Fallback: try attribute, then index (for namedtuples/lists)
    val = getattr(obj, key, None)
    if val is None and hasattr(obj, '__getitem__'):
        try:
            val = obj[idx]
        except Exception:
            pass
    return default if val is None else val


def get_fleet_speed(ships: int) -> float:
    """Exact speed formula from the game mechanics."""
    if ships <= 1:
        return 1.0
    return 1.0 + (MAX_FLEET_SPEED - 1.0) * (
        math.log(max(ships, 1)) / math.log(1000)
    ) ** 1.5


def point_to_segment_distance(px, py, x1, y1, x2, y2):
    """Minimum distance from point P to segment (x1,y1)-(x2,y2)."""
    dx = x2 - x1
    dy = y2 - y1
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    projx = x1 + t * dx
    projy = y1 + t * dy
    return math.hypot(px - projx, py - projy)


def will_hit_sun(x1, y1, x2, y2):
    """True if the straight-line path from (x1,y1) to (x2,y2) intersects the Sun."""
    return point_to_segment_distance(SUN_X, SUN_Y, x1, y1, x2, y2) < SUN_RADIUS


def is_orbiting(planet):
    """Determine whether a planet is an inner (orbiting) planet."""
    # planet format: [id, owner, x, y, radius, ships, production]
    x = float(planet[2] if hasattr(planet, '__getitem__') else getattr(planet, 'x', 0.0))
    y = float(planet[3] if hasattr(planet, '__getitem__') else getattr(planet, 'y', 0.0))
    radius = float(planet[4] if hasattr(planet, '__getitem__') else getattr(planet, 'radius', 0.0))
    orbital_r = math.hypot(x - SUN_X, y - SUN_Y)
    return orbital_r + radius < ROTATION_RADIUS_LIMIT


def predict_planet_pos(planet, angular_velocity, turns):
    """
    Predict the visual position of a planet after `turns` turns.
    Uses the same CCW angular update as the environment.
    """
    x = float(planet[2] if hasattr(planet, '__getitem__') else getattr(planet, 'x', 0.0))
    y = float(planet[3] if hasattr(planet, '__getitem__') else getattr(planet, 'y', 0.0))
    dx = x - SUN_X
    dy = y - SUN_Y
    orbital_r = math.hypot(dx, dy)
    if orbital_r < 1e-9:
        return x, y
    theta = math.atan2(dy, dx)
    new_theta = theta + angular_velocity * turns
    nx = SUN_X + orbital_r * math.cos(new_theta)
    ny = SUN_Y + orbital_r * math.sin(new_theta)
    return nx, ny


def find_interception(sx, sy, planet, angular_velocity, ships_to_send):
    """
    Find a launch angle that allows a fleet to intercept an orbiting planet.
    Returns (angle, turns, tx, ty) or None if no feasible interception found.
    """
    v = get_fleet_speed(ships_to_send)
    if v < 1e-9:
        return None

    radius = float(planet[4] if hasattr(planet, '__getitem__') else getattr(planet, 'radius', 0.0))

    for t in range(1, MAX_INTERCEPTION_TURNS + 1):
        tx, ty = predict_planet_pos(planet, angular_velocity, t)
        dist = math.hypot(tx - sx, ty - sy)
        # The fleet is launched from radius+0.1 along the angle; continuous
        # collision detection means we only need to get within the planet radius.
        if dist <= v * t + radius + 1e-6:
            angle = math.atan2(ty - sy, tx - sx)
            return angle, t, tx, ty
    return None


# -----------------------------------------------------------------------------
# AGENT
# -----------------------------------------------------------------------------
def agent(obs):
    # --- Safe parsing of observation (dict or object) -----------------------
    player = int(_getattr_or_item(obs, 'player', None, 0))
    angular_velocity = float(_getattr_or_item(obs, 'angular_velocity', None, 0.0))
    raw_planets = _getattr_or_item(obs, 'planets', None, [])
    raw_fleets = _getattr_or_item(obs, 'fleets', None, [])

    moves = []

    # --- Parse planets into a clean dict format -----------------------------
    my_planets = []
    other_planets = []
    for p in raw_planets:
        if not p:
            continue
        try:
            p_id = int(p[0] if hasattr(p, '__getitem__') else getattr(p, 'id', -1))
            owner = int(p[1] if hasattr(p, '__getitem__') else getattr(p, 'owner', -1))
            x = float(p[2] if hasattr(p, '__getitem__') else getattr(p, 'x', 0.0))
            y = float(p[3] if hasattr(p, '__getitem__') else getattr(p, 'y', 0.0))
            radius = float(p[4] if hasattr(p, '__getitem__') else getattr(p, 'radius', 0.0))
            ships = int(p[5] if hasattr(p, '__getitem__') else getattr(p, 'ships', 0))
            production = float(p[6] if hasattr(p, '__getitem__') else getattr(p, 'production', 0.0))
        except Exception:
            continue

        info = {
            'id': p_id,
            'owner': owner,
            'x': x,
            'y': y,
            'radius': radius,
            'ships': ships,
            'production': production,
            'orbiting': is_orbiting(p),
            'raw': p,
        }

        if owner == player:
            my_planets.append(info)
        elif owner != player:
            other_planets.append(info)

    # --- Parse fleets (exposed for your strategy logic) ---------------------
    fleets = []
    for f in raw_fleets:
        if not f:
            continue
        try:
            fleets.append({
                'id': int(f[0] if hasattr(f, '__getitem__') else getattr(f, 'id', -1)),
                'owner': int(f[1] if hasattr(f, '__getitem__') else getattr(f, 'owner', -1)),
                'x': float(f[2] if hasattr(f, '__getitem__') else getattr(f, 'x', 0.0)),
                'y': float(f[3] if hasattr(f, '__getitem__') else getattr(f, 'y', 0.0)),
                'angle': float(f[4] if hasattr(f, '__getitem__') else getattr(f, 'angle', 0.0)),
                'from_planet_id': int(f[5] if hasattr(f, '__getitem__') else getattr(f, 'from_planet_id', -1)),
                'ships': int(f[6] if hasattr(f, '__getitem__') else getattr(f, 'ships', 0)),
            })
        except Exception:
            continue

    # -----------------------------------------------------------------------
    # BASELINE LOGIC — REPLACE EVERYTHING BELOW WITH YOUR OWN STRATEGY.
    # This minimal example attacks the nearest non-owned planet with half of
    # the available ships, respecting orbital motion and sun collision.
    # -----------------------------------------------------------------------
    for mp in my_planets:
        if mp['ships'] <= 0:
            continue

        # Simple nearest-target selection
        best_target = None
        best_dist = float('inf')
        for tp in other_planets:
            d = math.hypot(mp['x'] - tp['x'], mp['y'] - tp['y'])
            if d < best_dist:
                best_dist = d
                best_target = tp

        if best_target is None:
            continue

        ships_to_send = mp['ships'] // 2
        if ships_to_send <= 0:
            continue

        # --- Compute interception angle ------------------------------------
        if best_target['orbiting']:
            result = find_interception(mp['x'], mp['y'], best_target['raw'], angular_velocity, ships_to_send)
            if result is None:
                continue
            angle, turns, tx, ty = result
        else:
            angle = math.atan2(best_target['y'] - mp['y'], best_target['x'] - mp['x'])
            tx, ty = best_target['x'], best_target['y']
            turns = math.hypot(tx - mp['x'], ty - mp['y']) / get_fleet_speed(ships_to_send)

        # --- Sun collision guard -------------------------------------------
        # Fleets are launched from just outside the planet radius.
        start_x = mp['x'] + math.cos(angle) * (mp['radius'] + 0.1)
        start_y = mp['y'] + math.sin(angle) * (mp['radius'] + 0.1)

        if will_hit_sun(start_x, start_y, tx, ty):
            continue

        # --- Final validation ----------------------------------------------
        if ships_to_send > mp['ships']:
            continue

        moves.append([mp['id'], float(angle), int(ships_to_send)])

    return moves