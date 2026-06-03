import math

SUN_X = 50.0
SUN_Y = 50.0
SUN_R = 10.0
ORBITING_THRESHOLD = 35.0


def get_fleet_speed(ships: int) -> float:
    ships = int(ships)
    if ships <= 1:
        return 1.0
    return 1.0 + (6.0 - 1.0) * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _entry_value(entry, idx, key, default=None):
    if isinstance(entry, dict):
        return entry.get(key, default)
    if hasattr(entry, key):
        return getattr(entry, key, default)
    try:
        return entry[idx]
    except Exception:
        return default


def _parse_planet(raw):
    return {
        "id": int(_entry_value(raw, 0, "id", -1)),
        "owner": int(_entry_value(raw, 1, "owner", -1)),
        "x": float(_entry_value(raw, 2, "x", 0.0)),
        "y": float(_entry_value(raw, 3, "y", 0.0)),
        "radius": float(_entry_value(raw, 4, "radius", 0.0)),
        "ships": int(_entry_value(raw, 5, "ships", 0)),
        "production": float(_entry_value(raw, 6, "production", 0.0)),
    }


def _parse_fleet(raw):
    return {
        "id": int(_entry_value(raw, 0, "id", -1)),
        "owner": int(_entry_value(raw, 1, "owner", -1)),
        "x": float(_entry_value(raw, 2, "x", 0.0)),
        "y": float(_entry_value(raw, 3, "y", 0.0)),
        "angle": float(_entry_value(raw, 4, "angle", 0.0)),
        "from_planet_id": int(_entry_value(raw, 5, "from_planet_id", -1)),
        "ships": int(_entry_value(raw, 6, "ships", 0)),
    }


def _dist(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)


def _segment_intersects_circle(x1, y1, x2, y2, cx, cy, r):
    dx = x2 - x1
    dy = y2 - y1
    fx = x1 - cx
    fy = y1 - cy

    a = dx * dx + dy * dy
    if a == 0.0:
        return _dist(x1, y1, cx, cy) < r

    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return False

    disc = math.sqrt(disc)
    t1 = (-b - disc) / (2.0 * a)
    t2 = (-b + disc) / (2.0 * a)

    return (0.0 <= t1 <= 1.0) or (0.0 <= t2 <= 1.0)


def _predict_target_position(target, source_x, source_y, ships, angular_velocity):
    tx = target["x"]
    ty = target["y"]
    dx = tx - SUN_X
    dy = ty - SUN_Y
    orbit_r = math.hypot(dx, dy)

    if orbit_r <= SUN_R + 1e-9:
        return tx, ty

    if orbit_r <= ORBITING_THRESHOLD:
        speed = max(get_fleet_speed(ships), 1e-9)
        eta = _dist(source_x, source_y, tx, ty) / speed
        theta = math.atan2(dy, dx) + angular_velocity * eta
        return SUN_X + orbit_r * math.cos(theta), SUN_Y + orbit_r * math.sin(theta)

    return tx, ty


def _target_score(target, source_x, source_y):
    d = _dist(source_x, source_y, target["x"], target["y"])
    if target["owner"] == -1:
        return 10.0 * target["production"] - 1.5 * target["ships"] - 0.35 * d - 0.1 * target["radius"]
    return 12.0 * target["production"] - 1.2 * target["ships"] - 0.25 * d - 0.1 * target["radius"]


def agent(obs):
    player = _get(obs, "player", 0)
    angular_velocity = float(_get(obs, "angular_velocity", 0.0))
    raw_planets = _get(obs, "planets", [])
    raw_fleets = _get(obs, "fleets", [])

    planets = []
    for p in raw_planets or []:
        try:
            planets.append(_parse_planet(p))
        except Exception:
            continue

    fleets = []
    for f in raw_fleets or []:
        try:
            fleets.append(_parse_fleet(f))
        except Exception:
            continue

    my_planets = [p for p in planets if p["owner"] == player]
    enemy_or_neutral = [p for p in planets if p["owner"] != player]

    if not my_planets or not enemy_or_neutral:
        return []

    enemy_pressure = {}
    for f in fleets:
        if f["owner"] != player:
            enemy_pressure[f["from_planet_id"]] = enemy_pressure.get(f["from_planet_id"], 0) + f["ships"]

    moves = []

    for source in sorted(my_planets, key=lambda p: (p["ships"], p["production"]), reverse=True):
        ships_here = int(source["ships"])
        reserve = max(8, int(0.25 * ships_here))
        available = ships_here - reserve
        if available <= 1:
            continue

        candidates = sorted(
            enemy_or_neutral,
            key=lambda t: (_target_score(t, source["x"], source["y"]), -t["production"], -t["ships"]),
            reverse=True,
        )

        chosen = None
        chosen_pos = None
        chosen_angle = None
        chosen_send = None

        for target in candidates:
            tx, ty = _predict_target_position(target, source["x"], source["y"], available, angular_velocity)
            if _segment_intersects_circle(source["x"], source["y"], tx, ty, SUN_X, SUN_Y, SUN_R):
                continue

            needed = int(target["ships"] + 1 + max(0, target["production"] * 2))
            needed = max(1, needed)

            pressure = int(enemy_pressure.get(target["id"], 0))
            needed = max(1, needed - pressure // 3)

            send = min(available, needed)
            if send <= 0:
                continue

            chosen = target
            chosen_pos = (tx, ty)
            chosen_angle = math.atan2(ty - source["y"], tx - source["x"])
            chosen_send = int(send)
            break

        if chosen is None:
            continue

        moves.append([int(source["id"]), float(chosen_angle), int(chosen_send)])

    return moves