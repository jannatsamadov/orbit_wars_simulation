"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          ORBIT WARS — Advanced Competitive Agent                            ║
║                                                                              ║
║  Strategies:                                                                 ║
║  • Orbital intercept targeting  – iterative fixed-point solver aims at      ║
║    where a planet WILL BE when the fleet arrives, not its current position. ║
║  • Fleet-flow analysis          – tracks all friendly / enemy ships in      ║
║    transit to adjust garrison estimates and per-planet threat levels.       ║
║  • Emergency defence pass       – detects threatened planets first and       ║
║    rush-reinforces from the nearest capable ally.                           ║
║  • Economic scoring             – rates every (source, target) pair by      ║
║    production-per-ship-invested, discounted by distance.                    ║
║  • Sun avoidance                – every launch angle is validated against   ║
║    the sun exclusion zone before the move is emitted.                       ║
║  • Adaptive aggression          – when trailing on production, attack bonus  ║
║    on enemy planets increases automatically.                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import math

# ─── Constants ────────────────────────────────────────────────────────────────
SUN_X, SUN_Y, SUN_R = 50.0, 50.0, 10.0
SUN_GAP  = 1.5   # Extra clearance (units) around the sun boundary
KEEP_MIN = 1     # Always keep at least this many ships on an owned planet


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — Physics helpers
# ══════════════════════════════════════════════════════════════════════════════

def fleet_speed(n: int) -> float:
    """
    Fleet speed for n ships — exact formula from game rules.
      n <= 1  →  1.0
      n = 1000→  6.0  (maximum)
    """
    if n <= 1:
        return 1.0
    return 1.0 + 5.0 * (math.log(max(n, 1)) / math.log(1000)) ** 1.5


def eta(dist: float, n: int) -> float:
    """Travel time (turns) for a fleet of n ships over `dist` units."""
    s = fleet_speed(max(1, n))
    return dist / s if s > 0 else float('inf')


def edist(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def seg_pt_dist(px, py, ax, ay, bx, by) -> float:
    """
    Minimum distance from point P=(px,py) to line segment A=(ax,ay)→B=(bx,by).
    Used to determine whether a fleet path skims the sun.
    """
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    if d2 < 1e-12:
        return edist(px, py, ax, ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / d2))
    return edist(px, py, ax + t * dx, ay + t * dy)


def path_thru_sun(sx, sy, tx, ty) -> bool:
    """
    Returns True if the straight-line path (sx,sy) → (tx,ty) would
    enter the sun exclusion zone (radius SUN_R + SUN_GAP).
    Such a fleet would be destroyed — never launch on this angle.
    """
    return seg_pt_dist(SUN_X, SUN_Y, sx, sy, tx, ty) < SUN_R + SUN_GAP


def orbit_xy(ox: float, oy: float, omega: float, t: float):
    """
    Cartesian position of a CCW-orbiting body currently at (ox, oy)
    after t turns with angular velocity omega (rad/turn).
    """
    dx, dy = ox - SUN_X, oy - SUN_Y
    r     = math.hypot(dx, dy)
    theta = math.atan2(dy, dx) + omega * t
    return SUN_X + r * math.cos(theta), SUN_Y + r * math.sin(theta)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — Orbital intercept solver
# ══════════════════════════════════════════════════════════════════════════════

def intercept_pos(sx: float, sy: float,
                  px: float, py: float,
                  omega: float, n: int, is_orb: bool,
                  iters: int = 64):
    """
    Compute the predicted arrival position and launch angle for a fleet of
    n ships departing from (sx, sy) towards a planet currently at (px, py).

    Algorithm (orbiting planets):
      1. Start estimate = planet's current position.
      2. Compute travel time to current estimate.
      3. Predict where planet will be at that travel time (orbit_xy).
      4. Blend old estimate 55% + new estimate 45% (damping prevents overshoot).
      5. Repeat until |delta| < 5×10⁻⁴ or max_iters reached.

    The damping factor 0.55/0.45 was chosen empirically — it eliminates
    oscillation for all tested angular velocities while converging in < 15
    iterations for typical map sizes.

    Returns: (pred_x, pred_y, launch_angle_radians, distance)
    """
    if not is_orb or abs(omega) < 1e-9:
        d = edist(sx, sy, px, py)
        a = math.atan2(py - sy, px - sx) if d > 1e-9 else 0.0
        return px, py, a, d

    tx, ty = float(px), float(py)
    for _ in range(iters):
        d = edist(sx, sy, tx, ty)
        if d < 1e-9:
            break
        t  = eta(d, n)
        nx, ny = orbit_xy(px, py, omega, t)
        if edist(tx, ty, nx, ny) < 5e-4:
            tx, ty = nx, ny
            break
        tx = 0.55 * tx + 0.45 * nx
        ty = 0.55 * ty + 0.45 * ny

    d = edist(sx, sy, tx, ty)
    a = math.atan2(ty - sy, tx - sx) if d > 1e-9 else 0.0
    return tx, ty, a, d


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — Fleet destination inference & flow analysis
# ══════════════════════════════════════════════════════════════════════════════

def guess_dest(fl: dict, planets: list):
    """
    Infer which planet a fleet is heading towards by finding the planet
    whose centre lies closest to the fleet's heading ray AND within
    (planet_radius + 6 units) of that ray.

    We search in order of increasing forward-projection distance so the
    result is always the *first* plausible planet along the path — not some
    planet the fleet has already passed.

    Returns the matching planet dict, or None.
    """
    fx, fy, fa = fl['x'], fl['y'], fl['angle']
    ca, sa = math.cos(fa), math.sin(fa)
    best, best_fwd = None, float('inf')

    for p in planets:
        vx, vy = p['x'] - fx, p['y'] - fy
        fwd  = vx * ca + vy * sa          # forward projection along heading
        if fwd <= 0:
            continue                        # planet is behind the fleet
        perp = abs(vx * sa - vy * ca)      # lateral offset from heading ray
        if perp <= p['radius'] + 6.0 and fwd < best_fwd:
            best_fwd, best = fwd, p

    return best


def compute_flows(fleets: list, planets: list, player: int):
    """
    Walk every in-flight fleet, infer its destination, and accumulate:
      my_in [planet_id] — friendly ships en route to that planet
      opp_in[planet_id] — opponent ships en route to that planet

    These values adjust garrison projections and threat reserves.
    """
    my_in  = {p['id']: 0.0 for p in planets}
    opp_in = {p['id']: 0.0 for p in planets}

    for fl in fleets:
        dest = guess_dest(fl, planets)
        if dest is None:
            continue
        if fl['owner'] == player:
            my_in[dest['id']]  += fl['ships']
        else:
            opp_in[dest['id']] += fl['ships']

    return my_in, opp_in


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — Scoring
# ══════════════════════════════════════════════════════════════════════════════

def score_attack(src: dict, tgt: dict, omega: float, avail_ships: int,
                 my_in: dict, opp_in: dict, player: int,
                 trailing: bool):
    """
    Evaluate the economic value of sending `avail_ships` from `src` to `tgt`.

    Garrison projection:
      g = tgt.ships + tgt.prod × travel_time          (growth during flight)
        + opp_in[tgt.id]   (if enemy: they may reinforce)
        − my_in[tgt.id]    (our prior fleets soften the garrison)

    Score formula:
      base_score = prod / (needed × (1 + dist/60))

    Modifiers applied multiplicatively:
      × 2.5  if the garrison is nearly empty  (nearly-free capture)
      × 2.2  if the target is an enemy planet (we gain AND deny production)
      × 1.4  if we are economically trailing  (extra urgency on enemy planets)

    Returns (score, angle, dist, ships_needed) or None if infeasible.
    """
    sx, sy = src['x'], src['y']
    px, py = tgt['x'], tgt['y']
    is_en  = tgt['owner'] not in (-1, player)

    # Intercept with the full available pool (sets speed / best angle estimate)
    tx, ty, angle, d = intercept_pos(sx, sy, px, py, omega, avail_ships, tgt['orb'])

    if d < 1e-6 or path_thru_sun(sx, sy, tx, ty):
        return None

    # Garrison projection at estimated arrival
    t_fly = eta(d, avail_ships)
    g = tgt['ships'] + tgt['prod'] * t_fly
    if is_en:
        g += opp_in.get(tgt['id'], 0.0)
    g -= my_in.get(tgt['id'], 0.0)
    g  = max(0.0, g)
    needed = int(g) + 2   # +2 guarantees capture even with small estimation errors

    if avail_ships < needed:
        return None

    prod  = max(tgt['prod'], 0.1)
    score = prod / (needed * (1.0 + d / 60.0))

    if g < 5:
        score *= 2.5               # snap up nearly-undefended planets
    if is_en:
        score *= 2.2               # attack = double production swing
    if trailing and is_en:
        score *= 1.4               # extra urgency when economically behind

    return score, angle, d, needed


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — Main agent entry point
# ══════════════════════════════════════════════════════════════════════════════

def agent(obs):
    """
    Orbit Wars agent.

    Decision pipeline each turn:
      1. Parse observation (supports both dict and object forms).
      2. Tag each planet as orbiting vs static.
      3. Infer fleet destinations → build friendly / enemy flow maps.
      4. Compute available ships per planet (reserve ships against threats).
      5. PASS 1 — Emergency defence: rush-reinforce planets about to fall.
      6. PASS 2 — Score all (source, target) pairs economically.
      7. PASS 3 — Greedy best-first move assignment with recomputed intercepts.

    Returns a list of moves: [[from_planet_id, angle_rad, num_ships], ...]
    """

    # ── 1. Parse observation ──────────────────────────────────────────────────
    _d  = isinstance(obs, dict)
    P   = obs.get("player", 0)              if _d else obs.player
    W   = obs.get("angular_velocity", 0.0)  if _d else getattr(obs, "angular_velocity", 0.0)
    rp  = obs.get("planets", [])            if _d else obs.planets
    rf  = obs.get("fleets",  [])            if _d else getattr(obs, "fleets", [])

    # ── 2. Build planet list ──────────────────────────────────────────────────
    planets = []
    for p in rp:
        try:
            pl = {
                'id':     int(p[0]),
                'owner':  int(p[1]),
                'x':      float(p[2]),
                'y':      float(p[3]),
                'radius': float(p[4]),
                'ships':  float(p[5]),
                'prod':   float(p[6]),
            }
            dx, dy = pl['x'] - SUN_X, pl['y'] - SUN_Y
            sr = math.hypot(dx, dy)
            # Inner planets (solar dist 10–42) orbit when angular_velocity ≠ 0.
            # Outer planets and comets outside this band are treated as static
            # for the intercept solver (good-enough approximation).
            pl['orb'] = abs(W) > 1e-9 and 10.0 < sr < 42.0
            planets.append(pl)
        except (IndexError, TypeError, ValueError):
            pass  # Malformed entry — skip safely

    # ── 3. Build fleet list ───────────────────────────────────────────────────
    fleets = []
    for f in rf:
        try:
            fleets.append({
                'owner': int(f[1]),
                'x':     float(f[2]),
                'y':     float(f[3]),
                'angle': float(f[4]),
                'ships': float(f[6]),
            })
        except (IndexError, TypeError, ValueError):
            pass

    # ── 4. Categorise ─────────────────────────────────────────────────────────
    mine    = [p for p in planets if p['owner'] == P]
    targets = [p for p in planets if p['owner'] != P]

    if not mine:
        return []

    en_pl    = [p for p in planets if p['owner'] not in (-1, P)]
    my_prod  = sum(p['prod'] for p in mine)
    opp_prod = sum(p['prod'] for p in en_pl)
    trailing = my_prod < opp_prod   # True → activate aggression boost

    # ── 5. Fleet flow analysis ────────────────────────────────────────────────
    my_in, opp_in = compute_flows(fleets, planets, P)

    # ── 6. Compute available (sendable) ships per planet ─────────────────────
    #
    # Reserve rule:
    #   If an enemy fleet threatens this planet (opp_in > current garrison),
    #   we keep enough ships to survive after the attack lands.
    #   Otherwise we keep the bare minimum (KEEP_MIN = 1).
    #
    avail = {}
    for p in mine:
        pid    = p['id']
        shield = p['ships'] + my_in.get(pid, 0.0)   # garrison + friendly help
        threat = opp_in.get(pid, 0.0)
        if threat > shield:
            reserve = int(threat - p['ships']) + 2
        else:
            reserve = KEEP_MIN
        avail[pid] = max(0, int(p['ships']) - max(KEEP_MIN, reserve))

    used   = {p['id']: 0 for p in mine}
    moves  = []
    locked = set()   # Planet IDs already handled this turn

    # ════════════════════════════════════════════════════════════════════════
    # PASS 1 — Emergency defence
    # Planets that cannot survive incoming attacks without reinforcement,
    # sorted worst-deficit-first.
    # ════════════════════════════════════════════════════════════════════════
    danger = sorted(
        [(opp_in.get(p['id'], 0.0) - p['ships'] - my_in.get(p['id'], 0.0), p)
         for p in mine
         if opp_in.get(p['id'], 0.0) > p['ships'] + my_in.get(p['id'], 0.0)],
        key=lambda x: -x[0]   # largest deficit first
    )

    for deficit, pl in danger:
        pid  = pl['id']
        need = int(deficit) + 2

        # Try each allied planet in order of proximity
        allies = sorted(
            [s for s in mine if s['id'] != pid],
            key=lambda s: edist(s['x'], s['y'], pl['x'], pl['y'])
        )
        for src in allies:
            sid = src['id']
            a   = avail[sid] - used[sid]
            if a < 1:
                continue
            send = min(a, need + 3)
            # Use intercept solver even for our own orbiting planets
            tx, ty, angle, d = intercept_pos(
                src['x'], src['y'], pl['x'], pl['y'], W, send, pl['orb'])
            if d < 1e-6 or path_thru_sun(src['x'], src['y'], tx, ty):
                continue
            moves.append([sid, angle, send])
            used[sid]  += send
            locked.add(pid)
            break   # One reinforcement per threatened planet per turn

    # ════════════════════════════════════════════════════════════════════════
    # PASS 2 — Score every (source planet, target planet) pair
    # ════════════════════════════════════════════════════════════════════════
    cands = []
    for src in mine:
        sid = src['id']
        a   = avail[sid] - used[sid]
        if a < 1:
            continue

        for tgt in targets:
            result = score_attack(src, tgt, W, a, my_in, opp_in, P, trailing)
            if result is None:
                continue
            sc, angle, d, needed = result
            cands.append((sc, sid, src, tgt, needed))

    cands.sort(key=lambda c: -c[0])   # best economic score first

    # ════════════════════════════════════════════════════════════════════════
    # PASS 3 — Greedy best-first assignment
    #
    # Send formula:
    #   target_send = needed × 1.5 + 5     (50% buffer + flat bonus for speed)
    #   send = clamp(target_send, needed, available)
    #
    # Reasoning: larger fleets are faster (log-speed formula), so sending
    # slightly more than the minimum is usually free — the fleet arrives
    # sooner, reducing how much the garrison grows during transit.
    # The 1.5× cap prevents over-committing when many good targets exist.
    #
    # After determining the actual send count we RECOMPUTE the intercept
    # because fleet speed (and therefore the exact orbital intercept angle)
    # changes with ship count.
    # ════════════════════════════════════════════════════════════════════════
    for _, sid, src, tgt, needed in cands:
        tid = tgt['id']
        if tid in locked:
            continue
        a = avail[sid] - used[sid]
        if a < needed:
            continue

        send = max(needed, min(a, int(needed * 1.5) + 5))

        # Recompute with actual ship count — orbit intercept angle differs
        tx, ty, angle, d = intercept_pos(
            src['x'], src['y'], tgt['x'], tgt['y'], W, send, tgt['orb'])
        if d < 1e-6 or path_thru_sun(src['x'], src['y'], tx, ty):
            continue

        moves.append([sid, angle, send])
        used[sid] += send
        locked.add(tid)

    return moves