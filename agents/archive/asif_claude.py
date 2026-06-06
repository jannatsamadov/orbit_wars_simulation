import math

# ---------------------------------------------------------------------------
# Orbit Wars - advanced competitive agent
#
# Core ideas:
#   * Predictive interception: fleets fly in straight lines and cannot turn,
#     so we solve a fixed-point equation for the time-to-impact against a
#     moving (orbiting) target and aim at the predicted future position.
#   * Empirical motion model: we keep a small amount of cross-turn global
#     state to *measure* each body's motion (angular velocity around the Sun
#     for orbiting planets, linear velocity for comets / static planets)
#     instead of guessing which planets are "inner" vs "outer".
#   * Sun avoidance: any straight path that grazes the Sun is fatal, so we
#     reject shots whose segment passes within the Sun radius + margin.
#   * Economy: capture cost accounts for production growth during transit;
#     we only commit a capture when it is actually affordable, and we hold
#     back a reserve sized to the incoming enemy threat.
# ---------------------------------------------------------------------------

SUN = (50.0, 50.0)
SUN_R = 10.0
SUN_MARGIN = 1.6          # extra clearance so we never clip the Sun
MAX_SPEED = 6.0
LOG1000 = math.log(1000.0)

# Cross-turn memory (persists within a single episode / process).
_PREV = {}                # body_id -> (x, y)


def get_fleet_speed(ships):
    """Logarithmic speed scaling, capped at 6.0."""
    if ships <= 1:
        return 1.0
    s = 1.0 + (MAX_SPEED - 1.0) * (math.log(max(ships, 1)) / LOG1000) ** 1.5
    return s if s < MAX_SPEED else MAX_SPEED


# --------------------------- parsing helpers -------------------------------

def _attr(o, key, idx, default):
    """Read a field from either dict-style, object-style, or list-style obs."""
    if isinstance(o, dict):
        return o.get(key, default)
    if isinstance(o, (list, tuple)):
        return o[idx] if idx is not None and len(o) > idx else default
    return getattr(o, key, default)


def _parse_planet(p):
    # [id, owner, x, y, radius, ships, production]
    if isinstance(p, dict):
        return {
            "id": p.get("id"), "owner": p.get("owner", -1),
            "x": float(p.get("x", 0.0)), "y": float(p.get("y", 0.0)),
            "radius": float(p.get("radius", 1.0)),
            "ships": float(p.get("ships", 0.0)),
            "prod": float(p.get("production", 0.0)),
        }
    return {
        "id": p[0], "owner": int(p[1]),
        "x": float(p[2]), "y": float(p[3]), "radius": float(p[4]),
        "ships": float(p[5]), "prod": float(p[6]),
    }


def _parse_fleet(f):
    # [id, owner, x, y, angle, from_planet_id, ships]
    if isinstance(f, dict):
        return {
            "id": f.get("id"), "owner": f.get("owner", -1),
            "x": float(f.get("x", 0.0)), "y": float(f.get("y", 0.0)),
            "angle": float(f.get("angle", 0.0)),
            "ships": float(f.get("ships", 0.0)),
        }
    return {
        "id": f[0], "owner": int(f[1]),
        "x": float(f[2]), "y": float(f[3]), "angle": float(f[4]),
        "ships": float(f[6]),
    }


# --------------------------- geometry helpers ------------------------------

def _dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def _seg_point_dist(px, py, ax, ay, bx, by):
    """Distance from point P to segment AB."""
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _sun_safe(ax, ay, bx, by):
    """True if the straight path A->B keeps clear of the Sun."""
    if _seg_point_dist(SUN[0], SUN[1], ax, ay, bx, by) <= SUN_R + SUN_MARGIN:
        return False
    if _dist(bx, by, SUN[0], SUN[1]) <= SUN_R + SUN_MARGIN:
        return False
    return True


# --------------------------- motion model ----------------------------------

def _make_predictor(body):
    """
    Build a function f(t) -> (x, y) predicting a body's position t turns ahead.

    Uses measured cross-turn motion:
      * If the radius from the Sun is ~constant and the body rotates, treat it
        as a circular orbit (handles inner orbiting planets AND static planets,
        whose measured angular velocity is ~0).
      * Otherwise extrapolate linearly (handles comets and the first turn).
    """
    bid = body["id"]
    x, y = body["x"], body["y"]
    prev = _PREV.get(bid)

    cx, cy = SUN
    r_now = math.hypot(x - cx, y - cy)

    if prev is not None and r_now > 1e-6:
        px, py = prev
        r_prev = math.hypot(px - cx, py - cy)
        if abs(r_now - r_prev) < 1.5 and r_prev > 1e-6:
            # Circular orbit about the Sun.
            th_now = math.atan2(y - cy, x - cx)
            th_prev = math.atan2(py - cy, px - cx)
            dth = math.atan2(math.sin(th_now - th_prev),
                             math.cos(th_now - th_prev))  # per-turn omega

            def f(t, _cx=cx, _cy=cy, _r=r_now, _th=th_now, _w=dth):
                a = _th + _w * t
                return (_cx + _r * math.cos(a), _cy + _r * math.sin(a))
            return f
        else:
            # Linear motion (comet, or radius drifting).
            vx, vy = x - px, y - py

            def f(t, _x=x, _y=y, _vx=vx, _vy=vy):
                return (_x + _vx * t, _y + _vy * t)
            return f

    # First sighting: assume stationary this turn.
    def f(t, _x=x, _y=y):
        return (_x, _y)
    return f


# --------------------------- interception ----------------------------------

def _intercept(ax, ay, predict, ships):
    """
    Fixed-point solve for time-to-impact of a straight fleet launched from
    (ax, ay) at the given ship count against a moving target.
    Returns (t, tx, ty) or None if it does not converge.
    """
    speed = get_fleet_speed(ships)
    tx, ty = predict(0.0)
    t = _dist(ax, ay, tx, ty) / speed
    for _ in range(48):
        tx, ty = predict(t)
        nt = _dist(ax, ay, tx, ty) / speed
        if abs(nt - t) < 1e-3:
            t = nt
            break
        t = 0.5 * t + 0.5 * nt            # damped iteration for stability
    tx, ty = predict(t)
    if t < 0.0 or t > 1e4 or math.isnan(t):
        return None
    return t, tx, ty


# --------------------------- main agent -------------------------------------

def agent(obs):
    try:
        return _agent(obs)
    except Exception:
        # Never crash the match; an empty move list is always legal.
        return []


def _agent(obs):
    player = _attr(obs, "player", None, 0)
    if isinstance(obs, dict):
        raw_planets = obs.get("planets", [])
        raw_fleets = obs.get("fleets", [])
    else:
        raw_planets = getattr(obs, "planets", [])
        raw_fleets = getattr(obs, "fleets", [])

    planets = [_parse_planet(p) for p in raw_planets]
    fleets = [_parse_fleet(f) for f in raw_fleets]

    mine = [p for p in planets if p["owner"] == player]
    targets = [p for p in planets if p["owner"] != player]

    # ---- update cross-turn memory (after reading prev inside predictors) ----
    predictors = {p["id"]: _make_predictor(p) for p in planets}

    moves = []
    if not mine:
        _remember(planets, fleets)
        return moves

    # ---- per-planet incoming enemy threat (sizing the defensive reserve) ----
    threat = {p["id"]: 0.0 for p in planets}
    for f in fleets:
        if f["owner"] == player:
            continue
        fx, fy, fa = f["x"], f["y"], f["angle"]
        dirx, diry = math.cos(fa), math.sin(fa)
        for p in mine:
            relx, rely = p["x"] - fx, p["y"] - fy
            ahead = relx * dirx + rely * diry
            if ahead <= 0:
                continue
            # perpendicular distance of the planet from the fleet's heading ray
            perp = abs(relx * diry - rely * dirx)
            if perp <= p["radius"] + 4.0:
                threat[p["id"]] += f["ships"]

    # available ships per owned planet after holding a defensive reserve
    remaining = {}
    for p in mine:
        reserve = min(p["ships"], threat[p["id"]])
        remaining[p["id"]] = max(0, int(p["ships"] - reserve))

    # ---- build candidate (source -> target) shots ----------------------------
    candidates = []

    # offensive: capture neutral / enemy planets
    for src in mine:
        avail = remaining[src["id"]]
        if avail <= 0:
            continue
        for tgt in targets:
            shot = _eval_shot(src, tgt, predictors[tgt["id"]], avail,
                              enemy_owned=(tgt["owner"] != -1))
            if shot is not None:
                candidates.append(shot)

    # defensive: reinforce a threatened owned planet from a safer one
    for tgt in mine:
        deficit = threat[tgt["id"]] - tgt["ships"]
        if deficit <= 0:
            continue
        for src in mine:
            if src["id"] == tgt["id"]:
                continue
            avail = remaining[src["id"]]
            if avail <= 0:
                continue
            shot = _eval_reinforce(src, tgt, predictors[tgt["id"]],
                                   int(deficit) + 1, avail)
            if shot is not None:
                candidates.append(shot)

    # ---- greedy allocation by value -----------------------------------------
    candidates.sort(key=lambda c: c["score"], reverse=True)
    committed = set()        # target ids already funded this turn
    for c in candidates:
        sid, tid = c["src"], c["tgt"]
        if tid in committed:
            continue
        avail = remaining[sid]
        need = c["ships"]
        if need <= 0 or need > avail:
            continue
        moves.append([sid, c["angle"], int(need)])
        remaining[sid] = avail - int(need)
        committed.add(tid)

    _remember(planets, fleets)
    return moves


def _eval_shot(src, tgt, predict, avail, enemy_owned):
    """Evaluate an offensive capture shot; return a scored candidate or None."""
    # First pass: estimate the *minimum* transit time by assuming we send our
    # full available force (more ships -> higher speed -> shorter time). This
    # gives a lower bound on the garrison we must overcome, so we never reject
    # a shot that is actually affordable at full strength.
    res = _intercept(src["x"], src["y"], predict, avail)
    if res is None:
        return None
    t, tx, ty = res
    # Only owned planets produce ships; neutral garrisons are static.
    grow = tgt["prod"] * t if enemy_owned else 0.0
    need = int(math.ceil(tgt["ships"] + grow)) + 1
    if need > avail:
        return None
    # Second pass: refine with the real ship count (changes speed -> aim).
    res = _intercept(src["x"], src["y"], predict, need)
    if res is None:
        return None
    t, tx, ty = res
    grow = tgt["prod"] * t if enemy_owned else 0.0
    need = int(math.ceil(tgt["ships"] + grow)) + 1
    if need > avail or need <= 0:
        return None
    if not _sun_safe(src["x"], src["y"], tx, ty):
        return None
    angle = math.atan2(ty - src["y"], tx - src["x"])
    own_bonus = 1.6 if enemy_owned else 1.0     # capturing denies the enemy
    time_factor = 1.0 / (1.0 + 0.05 * t)
    score = (tgt["prod"] + 0.15) / (need + 1.0) * time_factor * own_bonus
    return {"src": src["id"], "tgt": tgt["id"], "ships": need,
            "angle": angle, "score": score}


def _eval_reinforce(src, tgt, predict, need, avail):
    """Evaluate a defensive reinforcement shot."""
    if need > avail:
        need = avail
    if need <= 0:
        return None
    res = _intercept(src["x"], src["y"], predict, need)
    if res is None:
        return None
    t, tx, ty = res
    if not _sun_safe(src["x"], src["y"], tx, ty):
        return None
    angle = math.atan2(ty - src["y"], tx - src["x"])
    # high priority: defending owned production beats most expansion
    score = (tgt["prod"] + 1.0) * 2.0 / (1.0 + 0.05 * t)
    return {"src": src["id"], "tgt": tgt["id"], "ships": need,
            "angle": angle, "score": score}


def _remember(planets, fleets):
    """Store current positions for next-turn motion estimation."""
    _PREV.clear()
    for p in planets:
        _PREV[p["id"]] = (p["x"], p["y"])
    for f in fleets:
        _PREV[f["id"]] = (f["x"], f["y"])
