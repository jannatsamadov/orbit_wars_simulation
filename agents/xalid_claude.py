"""
Orbit Wars — competitive single-file agent.

Public entry point:
    def agent(obs) -> list[[from_planet_id:int, angle_radians:float, num_ships:int]]

Design summary
--------------
1.  ORBIT TRACKING (state across turns): every body's per-turn angular velocity
    around the Sun is *measured* from the previous frame. This automatically
    handles orbiting inner planets, static outer planets and elliptical comets
    without needing to be told which is which.
2.  PREDICTIVE INTERCEPTION: launching at a moving body is solved as a root-find
    on  g(t) = |target_pos(t) - launch| - speed*t .  Because fleet speed depends
    on ship count (which we choose), the (ships -> speed -> eta -> ships) loop is
    solved by a short fixed-point iteration.
3.  SUN AVOIDANCE: any launch whose straight path passes within the Sun's kill
    radius is discarded (fleets cannot steer).
4.  ECONOMY / WAR LOGIC: threat timeline per owned planet -> reinforce or
    evacuate -> value/cost expansion & offense -> consolidate idle rear stacks
    toward the frontier.
"""

import math

# ----------------------------- constants -----------------------------
SUN_X, SUN_Y = 50.0, 50.0
SUN_R = 10.0
SUN_SAFE = 10.6            # keep flight paths at least this far from Sun centre
MAX_T = 200.0             # interception look-ahead horizon (turns)
STEP = 1.0                # coarse scan step for the interception root
BISECT = 30               # bisection refinement iterations
NEAREST_K = 10            # candidate targets evaluated per owned planet
TIME_DISCOUNT = 0.045     # preference for nearer captures
RESERVE = 1               # ships kept behind on a safe planet
STAGE_MIN = 8             # only consolidate stacks bigger than this

# Persistent state. Kaggle keeps module globals alive between agent() calls,
# which lets us measure orbital motion frame-to-frame.
_PERSIST = {"call": 0, "pos": {}}


# ----------------------------- math helpers ---------------------------
def get_fleet_speed(ships):
    if ships <= 1:
        return 1.0
    s = 1.0 + (6.0 - 1.0) * (math.log(max(ships, 1)) / math.log(1000.0)) ** 1.5
    return s if s < 6.0 else 6.0


def _field(obs, name, default):
    if isinstance(obs, dict):
        return obs.get(name, default)
    return getattr(obs, name, default)


def _wrap(a):
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


def _dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def _seg_point_dist(ax, ay, bx, by, px, py):
    dx, dy = bx - ax, by - ay
    den = dx * dx + dy * dy
    if den <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / den
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _hits_sun(ax, ay, bx, by):
    return _seg_point_dist(ax, ay, bx, by, SUN_X, SUN_Y) < SUN_SAFE


def _predict(state, t):
    """Predicted position of a body. state = (x0, y0, r, phi0, omega)."""
    x0, y0, r, phi0, omega = state
    if r < 1e-9 or abs(omega) < 1e-4:
        return x0, y0
    phi = phi0 + omega * t
    return SUN_X + r * math.cos(phi), SUN_Y + r * math.sin(phi)


def _intercept_time(lx, ly, state, speed):
    """Smallest t > 0 at which a fleet launched from (lx,ly) at `speed`
    can meet the (possibly orbiting) body. Returns None if unreachable."""
    if speed <= 1e-9:
        return None
    px, py = _predict(state, 0.0)
    prev_t = 0.0
    g_prev = _dist(lx, ly, px, py)            # g(0) > 0 in normal cases
    if g_prev <= 1e-6:
        return 0.0
    t = STEP
    while t <= MAX_T:
        px, py = _predict(state, t)
        g = _dist(lx, ly, px, py) - speed * t
        if g <= 0.0:                           # root bracketed in (prev_t, t]
            lo, hi = prev_t, t
            for _ in range(BISECT):
                mid = 0.5 * (lo + hi)
                mx, my = _predict(state, mid)
                if _dist(lx, ly, mx, my) - speed * mid > 0.0:
                    lo = mid
                else:
                    hi = mid
            return 0.5 * (lo + hi)
        prev_t = t
        t += STEP
    return None


# ----------------------------- agent ----------------------------------
def agent(obs):
    try:
        return _agent_impl(obs)
    except Exception:
        # Never crash the turn.
        return []


def _agent_impl(obs):
    player = int(_field(obs, "player", 0))
    raw_planets = _field(obs, "planets", []) or []
    raw_fleets = _field(obs, "fleets", []) or []

    _PERSIST["call"] += 1
    prev_pos = _PERSIST.get("pos", {})
    new_pos = {}

    # ---- parse planets + measure orbital motion -------------------------
    planets = {}
    for row in raw_planets:
        try:
            pid = int(row[0]); owner = int(row[1])
            x = float(row[2]); y = float(row[3])
            radius = float(row[4]); ships = float(row[5]); prod = float(row[6])
        except Exception:
            continue
        new_pos[pid] = (x, y)
        r = math.hypot(x - SUN_X, y - SUN_Y)
        phi0 = math.atan2(y - SUN_Y, x - SUN_X)
        omega = 0.0
        if pid in prev_pos:
            ox, oy = prev_pos[pid]
            d = _wrap(phi0 - math.atan2(oy - SUN_Y, ox - SUN_X))
            if abs(d) > 1e-3:
                omega = d
        state = (x, y, r, phi0, omega)
        planets[pid] = {"id": pid, "owner": owner, "x": x, "y": y,
                        "radius": radius, "ships": ships, "prod": prod,
                        "state": state}

    _PERSIST["pos"] = new_pos

    # ---- parse fleets ---------------------------------------------------
    fleets = []
    for row in raw_fleets:
        try:
            fid = int(row[0]); owner = int(row[1])
            x = float(row[2]); y = float(row[3]); ang = float(row[4])
            frm = int(row[5]); ships = float(row[6])
        except Exception:
            continue
        fleets.append({"id": fid, "owner": owner, "x": x, "y": y,
                       "angle": ang, "from": frm, "ships": ships})

    mine = [p for p in planets.values() if p["owner"] == player]
    if not mine:
        return []
    enemies = [p for p in planets.values()
               if p["owner"] != player and p["owner"] != -1]
    neutrals = [p for p in planets.values() if p["owner"] == -1]
    targets = enemies + neutrals
    planet_list = list(planets.values())

    # ---- infer fleet destinations by heading alignment ------------------
    def fleet_target_id(fl, candidates):
        fx, fy, fa = fl["x"], fl["y"], fl["angle"]
        ca, sa = math.cos(fa), math.sin(fa)
        best, best_err, best_d = None, 0.30, None
        for p in candidates:
            dx, dy = p["x"] - fx, p["y"] - fy
            d = math.hypot(dx, dy)
            if d < 1e-6 or dx * ca + dy * sa <= 0.0:   # at/behind the fleet
                continue
            err = abs(_wrap(math.atan2(dy, dx) - fa))
            if err < best_err:
                best_err, best, best_d = err, p["id"], d
        return best, best_d

    incoming_enemy = {p["id"]: [] for p in mine}     # pid -> [(eta, ships)]
    incoming_friendly = {p["id"]: [] for p in mine}  # pid -> [(eta, ships)]
    friendly_to_target = {}                          # tid -> ships en route

    for fl in fleets:
        spd = get_fleet_speed(fl["ships"])
        if fl["owner"] == player:
            tid, d = fleet_target_id(fl, planet_list)
            if tid is None or d is None:
                continue
            if planets[tid]["owner"] == player:
                incoming_friendly[tid].append((d / spd, fl["ships"]))
            else:
                friendly_to_target[tid] = friendly_to_target.get(tid, 0.0) + fl["ships"]
        else:
            tid, d = fleet_target_id(fl, mine)
            if tid is not None and d is not None:
                incoming_enemy[tid].append((d / spd, fl["ships"]))

    # ---- threat timeline -> spend budget per owned planet ---------------
    budget = {}
    crit = {}
    predicted_lost = set()
    for p in mine:
        pid = p["id"]
        events = [(eta, -sh) for (eta, sh) in incoming_enemy[pid]]
        events += [(eta, +sh) for (eta, sh) in incoming_friendly[pid]]
        events.sort(key=lambda e: e[0])
        g = p["ships"]; last = 0.0; ming = g; mint = 0.0
        for eta, delta in events:
            g += p["prod"] * (eta - last)
            g += delta
            if g < ming:
                ming, mint = g, eta
            last = eta
        crit[pid] = (ming, mint)
        budget[pid] = max(0, int(math.floor(ming)) - RESERVE)

    moves = []
    sent = {}

    def commit(src_id, angle, ships):
        ships = int(ships)
        if ships <= 0:
            return
        cap = int(planets[src_id]["ships"]) - sent.get(src_id, 0)
        if ships > cap:
            ships = cap
        if ships <= 0:
            return
        sent[src_id] = sent.get(src_id, 0) + ships
        moves.append([int(src_id), float(angle), int(ships)])

    # ---- DEFENSE: reinforce threatened planets --------------------------
    threatened = sorted([p for p in mine if crit[p["id"]][0] < 1.0],
                        key=lambda p: crit[p["id"]][0])
    for p in threatened:
        pid = p["id"]
        ming, mint = crit[pid]
        deficit = int(math.ceil(1.0 - ming))
        if deficit <= 0:
            continue
        srcs = sorted([s for s in mine if s["id"] != pid and budget[s["id"]] > 0],
                      key=lambda s: _dist(s["x"], s["y"], p["x"], p["y"]))
        for s in srcs:
            if deficit <= 0:
                break
            sid = s["id"]
            send = min(deficit, budget[sid])
            if send <= 0:
                continue
            spd = get_fleet_speed(send)
            eta = _intercept_time(s["x"], s["y"], p["state"], spd)
            if eta is None or eta > mint + 3.0:
                continue
            ax, ay = _predict(p["state"], eta)
            if _hits_sun(s["x"], s["y"], ax, ay):
                continue
            commit(sid, math.atan2(ay - s["y"], ax - s["x"]), send)
            budget[sid] -= send
            deficit -= send
        if deficit > 0:
            predicted_lost.add(pid)

    # Planets we can't hold: free their entire garrison for offense/retreat.
    for pid in predicted_lost:
        budget[pid] = max(budget[pid], int(planets[pid]["ships"]) - sent.get(pid, 0))

    # ---- OFFENSE / EXPANSION -------------------------------------------
    def plan_capture(src, tgt, max_send):
        owner = tgt["owner"]; prod = tgt["prod"]; cur = tgt["ships"]
        finc = friendly_to_target.get(tgt["id"], 0.0)
        grow = prod if owner != -1 else 0.0
        base_extra = 1 if owner == -1 else 2
        ships = max(1, int(cur - finc) + 1)
        for _ in range(4):
            spd = get_fleet_speed(ships)
            eta = _intercept_time(src["x"], src["y"], tgt["state"], spd)
            if eta is None:
                return None
            garrison = cur + max(0.0, grow) * eta - finc
            if garrison < 0:                       # already covered by allies
                return None
            need = max(1, int(math.floor(garrison)) + base_extra)
            if need == ships:
                break
            ships = need
        spd = get_fleet_speed(ships)
        eta = _intercept_time(src["x"], src["y"], tgt["state"], spd)
        if eta is None or ships > max_send:
            return None
        ax, ay = _predict(tgt["state"], eta)
        if _hits_sun(src["x"], src["y"], ax, ay):
            return None
        return ships, math.atan2(ay - src["y"], ax - src["x"]), eta

    try:
        candidates = []
        for src in mine:
            sid = src["id"]
            if budget[sid] <= 0:
                continue
            ranked = sorted(
                targets, key=lambda t: _dist(src["x"], src["y"], t["x"], t["y"])
            )[:NEAREST_K]
            for tgt in ranked:
                plan = plan_capture(src, tgt, budget[sid])
                if plan is None:
                    continue
                ships, ang, eta = plan
                value = tgt["prod"]
                if tgt["owner"] != -1 and tgt["owner"] != player:
                    value *= 1.3                    # deny the enemy economy
                value += 0.05                       # value even 0-prod rocks
                score = value / float(ships) / (1.0 + TIME_DISCOUNT * eta)
                candidates.append((score, sid, tgt["id"], ships, ang))

        candidates.sort(key=lambda c: c[0], reverse=True)
        claimed = set()
        for score, sid, tid, ships, ang in candidates:
            if tid in claimed or budget[sid] < ships:
                continue
            commit(sid, ang, ships)
            budget[sid] -= ships
            claimed.add(tid)
    except Exception:
        pass

    # ---- CONSOLIDATION: push idle rear stacks to the frontier -----------
    try:
        if enemies:
            def near_enemy(p):
                return min(_dist(p["x"], p["y"], e["x"], e["y"]) for e in enemies)
            frontier = min(mine, key=near_enemy)
            f_dist = near_enemy(frontier)
            for src in mine:
                sid = src["id"]
                if sid == frontier["id"] or budget[sid] <= STAGE_MIN:
                    continue
                if near_enemy(src) <= f_dist + 5.0:    # already frontline
                    continue
                spare = budget[sid]
                spd = get_fleet_speed(spare)
                eta = _intercept_time(src["x"], src["y"], frontier["state"], spd)
                if eta is None:
                    continue
                ax, ay = _predict(frontier["state"], eta)
                if _hits_sun(src["x"], src["y"], ax, ay):
                    continue
                commit(sid, math.atan2(ay - src["y"], ax - src["x"]), spare)
                budget[sid] -= spare
    except Exception:
        pass

    return moves


# ----------------------------- smoke test -----------------------------
if __name__ == "__main__":
    # minimal self-check (dict-style + object-style, two turns for orbit est.)
    av = 0.08

    def planet(pid, owner, x, y, ships, prod, r=2.0):
        return [pid, owner, x, y, r, ships, prod]

    obs1 = {
        "player": 0,
        "angular_velocity": av,
        "planets": [
            planet(0, 0, 20.0, 50.0, 40, 1.0),   # mine (inner, orbiting)
            planet(1, -1, 80.0, 50.0, 12, 2.0),  # neutral (outer, static)
            planet(2, -1, 50.0, 20.0, 5, 0.0),   # neutral inner
            planet(3, 1, 50.0, 85.0, 30, 1.5),   # enemy
        ],
        "fleets": [
            [100, 1, 35.0, 50.0, math.atan2(0.0, -1.0), 3, 15],  # enemy -> me
        ],
    }
    out1 = agent(obs1)
    assert isinstance(out1, list)
    for mv in out1:
        assert len(mv) == 3 and isinstance(mv[0], int) and isinstance(mv[2], int)

    # advance orbiting planets one step so omega can be measured
    def rot(x, y, w):
        a = math.atan2(y - 50.0, x - 50.0) + w
        r = math.hypot(x - 50.0, y - 50.0)
        return 50.0 + r * math.cos(a), 50.0 + r * math.sin(a)

    x0, y0 = rot(20.0, 50.0, av)
    x2, y2 = rot(50.0, 20.0, av)

    class Obs:
        pass
    o2 = Obs()
    o2.player = 0
    o2.angular_velocity = av
    o2.planets = [
        planet(0, 0, x0, y0, 60, 1.0),
        planet(1, -1, 80.0, 50.0, 12, 2.0),
        planet(2, -1, x2, y2, 5, 0.0),
        planet(3, 1, 50.0, 85.0, 30, 1.5),
    ]
    o2.fleets = []
    out2 = agent(o2)
    assert isinstance(out2, list)

    # verify per-planet ship caps are respected
    spent = {}
    for fid, ang, n in out2:
        spent[fid] = spent.get(fid, 0) + n
    caps = {p[0]: p[5] for p in o2.planets if p[1] == 0}
    for pid, used in spent.items():
        assert used <= caps[pid], (pid, used, caps[pid])

    print("Turn 1 moves:", out1)
    print("Turn 2 moves:", out2)
    print("speed(1)=%.3f speed(100)=%.3f speed(5000)=%.3f"
          % (get_fleet_speed(1), get_fleet_speed(100), get_fleet_speed(5000)))
    print("OK: agent runs, output format & ship caps valid.")