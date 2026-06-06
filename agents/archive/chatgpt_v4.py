import math

SUN_X = 50.0
SUN_Y = 50.0
SUN_R = 10.0
BOARD = 100.0
MAX_SPEED = 6.0
HORIZON = 80
MIN_SEND = 8

# Persistent memory across turns
_PREV_POS = {}
_ORBITING = {}
_STEP = 0


def _get(obs, key, default=None):
    if isinstance(obs, dict):
        return obs.get(key, default)
    return getattr(obs, key, default)


def fleet_speed(ships: int) -> float:
    if ships <= 1:
        return 1.0
    x = math.log(max(1, ships)) / math.log(1000.0)
    x = max(0.0, min(1.0, x))
    return 1.0 + (MAX_SPEED - 1.0) * (x ** 1.5)


def d(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def seg_dist_to_sun(x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    den = dx * dx + dy * dy
    if den < 1e-12:
        return d(x1, y1, SUN_X, SUN_Y)
    t = ((SUN_X - x1) * dx + (SUN_Y - y1) * dy) / den
    t = max(0.0, min(1.0, t))
    px = x1 + t * dx
    py = y1 + t * dy
    return d(px, py, SUN_X, SUN_Y)


def path_hits_sun(x1, y1, x2, y2):
    return seg_dist_to_sun(x1, y1, x2, y2) < SUN_R + 0.2


def planet_pos(p, t, ang_v):
    pid, owner, x, y, r, ships, prod = p
    orbit = _ORBITING.get(pid)
    if orbit is None:
        prev = _PREV_POS.get(pid)
        if prev is not None:
            orbit = d(prev[0], prev[1], x, y) > 1e-4
        else:
            rr = d(x, y, SUN_X, SUN_Y)
            orbit = rr < 40.0
        _ORBITING[pid] = orbit

    if not orbit:
        return x, y

    rr = d(x, y, SUN_X, SUN_Y)
    th = math.atan2(y - SUN_Y, x - SUN_X) + ang_v * t
    return SUN_X + rr * math.cos(th), SUN_Y + rr * math.sin(th)


def predict_fleet_pos(f, t):
    fid, owner, x, y, ang, from_pid, ships = f
    sp = fleet_speed(int(ships))
    return x + math.cos(ang) * sp * t, y + math.sin(ang) * sp * t


def fleet_hits_planet(f, p, t, ang_v):
    fx, fy = predict_fleet_pos(f, t)
    px, py = planet_pos(p, t, ang_v)
    return d(fx, fy, px, py) <= p[4] + 1e-6


def fleet_target(f, planets, ang_v):
    best = None
    best_t = None
    for p in planets:
        for t in range(1, HORIZON + 1):
            if fleet_hits_planet(f, p, t, ang_v):
                if best_t is None or t < best_t:
                    best = p
                    best_t = t
                break
    if best is None:
        return None, None
    return best, best_t


def arrivals_by_planet(fleets, planets, ang_v):
    out = {p[0]: [] for p in planets}
    for f in fleets:
        target, eta = fleet_target(f, planets, ang_v)
        if target is None:
            continue
        out[target[0]].append((int(eta), int(f[1]), int(f[6])))
    for pid in out:
        out[pid].sort(key=lambda x: x[0])
    return out


def resolve_wave(owner, ships, arrivals):
    by_owner = {}
    for o, s in arrivals:
        by_owner[o] = by_owner.get(o, 0) + s
    if not by_owner:
        return owner, ships

    if owner != -1 and owner in by_owner:
        ships += by_owner.pop(owner)

    if not by_owner:
        return owner, ships

    items = sorted(by_owner.items(), key=lambda kv: kv[1], reverse=True)
    top_owner, top_ships = items[0]
    second = items[1][1] if len(items) > 1 else 0
    if top_ships == second:
        return -1, 0

    surv_owner = top_owner
    surv = top_ships - second

    if owner == -1:
        return surv_owner, surv

    if surv_owner == owner:
        return owner, ships + surv

    ships -= surv
    if ships < 0:
        return surv_owner, -ships
    return owner, ships


def simulate_planet(p, arrs, turns, player_id):
    owner = int(p[1])
    ships = int(p[5])
    prod = int(p[6])
    by_turn = {}
    for eta, o, s in arrs:
        if 1 <= eta <= turns:
            by_turn.setdefault(int(eta), []).append((int(o), int(s)))

    for t in range(1, turns + 1):
        if owner != -1:
            ships += prod
        if t in by_turn:
            owner, ships = resolve_wave(owner, ships, by_turn[t])
    return owner, ships


def survival_reserve(p, arrs, player_id):
    ships_now = int(p[5])
    lo, hi = 0, ships_now
    extra = max(6, int(p[6]) * 2)
    while lo < hi:
        mid = (lo + hi) // 2
        test = list(p)
        test[5] = mid
        ok_owner, ok_ships = simulate_planet(test, arrs, HORIZON, player_id)
        if ok_owner == player_id and ok_ships >= 1:
            hi = mid
        else:
            lo = mid + 1
    return min(ships_now, lo + extra)


def predict_arrival_state(target, eta, arrs, player_id):
    owner = int(target[1])
    ships = int(target[5])
    prod = int(target[6])
    by_turn = {}
    for t, o, s in arrs:
        if 1 <= t <= eta:
            by_turn.setdefault(int(t), []).append((int(o), int(s)))
    for turn in range(1, eta + 1):
        if owner != -1:
            ships += prod
        if turn in by_turn:
            owner, ships = resolve_wave(owner, ships, by_turn[turn])
    return owner, ships


def capture_need(target, eta, arrs, player_id):
    owner, ships = predict_arrival_state(target, eta, arrs, player_id)
    return ships + 1


def choose_target_value(target, eta, need, player_id, step):
    owner = int(target[1])
    prod = int(target[6])
    ships = int(target[5])

    if owner == -1:
        base = 18.0 + 12.0 * prod + 0.5 * ships
    else:
        base = 10.0 + 18.0 * prod + 0.25 * ships

    if step < 20:
        base *= 1.25 if owner == -1 else 0.95
    else:
        base *= 0.95 if owner == -1 else 1.20

    return base / ((need + 4.0) ** 0.85) / (eta + 0.8)


def intercept_plan(src, tgt, ships, ang_v):
    sx, sy = src[2], src[3]
    sr = src[4]
    t = 1
    angle = math.atan2(tgt[3] - sy, tgt[2] - sx)
    for _ in range(6):
        tx, ty = planet_pos(tgt, t, ang_v)
        angle = math.atan2(ty - sy, tx - sx)
        lx = sx + math.cos(angle) * (sr + 0.15)
        ly = sy + math.sin(angle) * (sr + 0.15)
        if path_hits_sun(lx, ly, tx, ty):
            return None
        speed = fleet_speed(int(ships))
        dist_to = d(lx, ly, tx, ty)
        nt = max(1, int(math.ceil(dist_to / speed)))
        if nt == t:
            return angle, t, tx, ty
        t = nt
    tx, ty = planet_pos(tgt, t, ang_v)
    angle = math.atan2(ty - sy, tx - sx)
    lx = sx + math.cos(angle) * (sr + 0.15)
    ly = sy + math.sin(angle) * (sr + 0.15)
    if path_hits_sun(lx, ly, tx, ty):
        return None
    return angle, t, tx, ty


def nearest_enemy_dist(p, enemies):
    if not enemies:
        return 999.0
    return min(d(p[2], p[3], e[2], e[3]) for e in enemies)


def agent(obs):
    global _STEP, _PREV_POS, _ORBITING

    player = _get(obs, "player", 0)
    ang_v = float(_get(obs, "angular_velocity", 0.0))
    planets = list(_get(obs, "planets", []) or [])
    fleets = list(_get(obs, "fleets", []) or [])

    step = _get(obs, "step", None)
    if step is not None:
        if step == 0 and _STEP != 0:
            _PREV_POS = {}
            _ORBITING = {}
        _STEP = int(step) + 1
    else:
        _STEP += 1

    if not planets:
        return []

    my_planets = [p for p in planets if p[1] == player]
    if not my_planets:
        return []

    enemy_planets = [p for p in planets if p[1] not in (-1, player)]
    neutral_planets = [p for p in planets if p[1] == -1]

    for p in planets:
        pid = p[0]
        if pid in _PREV_POS:
            px, py = _PREV_POS[pid]
            moved = d(px, py, p[2], p[3]) > 1e-4
            if moved:
                _ORBITING[pid] = True
        _PREV_POS[pid] = (p[2], p[3])

    arrs = arrivals_by_planet(fleets, planets, ang_v)

    reserves = {}
    threatened = {}
    for p in my_planets:
        pid = p[0]
        incoming = arrs.get(pid, [])
        reserve = survival_reserve(p, incoming, player)

        border = nearest_enemy_dist(p, enemy_planets)
        threat_turns = min([eta for eta, o, s in incoming if o != player], default=999)
        extra = 0
        if border < 18.0:
            extra += 8
        elif border < 28.0:
            extra += 4
        if threat_turns <= 8:
            extra += 8
        elif threat_turns <= 16:
            extra += 4

        reserve = min(int(p[5]), max(reserve, 8 + int(p[6]) * 2 + extra))
        reserves[pid] = reserve
        threatened[pid] = (border, threat_turns)

    my_prod = sum(int(p[6]) for p in my_planets)
    total_prod = sum(int(p[6]) for p in planets if p[1] != -1)
    prod_share = (my_prod / total_prod) if total_prod else 0.0
    pressure_mode = (step is not None and step >= 18 and prod_share >= 0.40) or len(my_planets) >= 3

    candidates = []
    targets = enemy_planets + neutral_planets

    for src in my_planets:
        available = int(src[5]) - reserves[src[0]]
        if available < MIN_SEND:
            continue

        best = None
        best_score = None

        for tgt in targets:
            if tgt[0] == src[0]:
                continue

            plan = intercept_plan(src, tgt, max(MIN_SEND, min(available, 60)), ang_v)
            if plan is None:
                continue
            angle, eta, tx, ty = plan
            if eta > HORIZON:
                continue

            need = capture_need(tgt, eta, arrs, player)
            if need <= 0:
                need = int(tgt[5]) + 1

            send = min(available, max(MIN_SEND, int(math.ceil(need * 1.08)) + 1))
            if send > available:
                continue
            if send <= need:
                continue

            future_owner, future_ships = predict_arrival_state(tgt, eta, arrs, player)
            if future_owner == player and future_ships > 0:
                continue

            val = choose_target_value(tgt, eta, need, player, step if step is not None else 0)
            if tgt[1] == -1:
                val += 0.8 * int(tgt[6]) * (2.0 if pressure_mode else 1.0)
            else:
                val += 1.5 * int(tgt[6]) + 0.15 * int(tgt[5])

            sx, sy = src[2], src[3]
            sr = src[4]
            lx = sx + math.cos(angle) * (sr + 0.15)
            ly = sy + math.sin(angle) * (sr + 0.15)
            if path_hits_sun(lx, ly, tx, ty):
                continue

            score = val - 0.03 * send - 0.15 * eta
            if tgt[1] == -1 and not pressure_mode:
                score *= 1.15
            if tgt[1] != -1 and pressure_mode:
                score *= 1.20

            if best is None or score > best_score:
                best = (src[0], angle, int(send), tgt[0], score)
                best_score = score

        if best is None and available >= 20 and my_planets:
            hub = max(
                my_planets,
                key=lambda p: (int(p[6]) * 3 + int(p[5]) - threatened.get(p[0], (999, 999))[0]),
            )
            if hub[0] != src[0]:
                plan = intercept_plan(src, hub, max(MIN_SEND, min(available, 50)), ang_v)
                if plan is not None:
                    angle, eta, tx, ty = plan
                    sx, sy = src[2], src[3]
                    sr = src[4]
                    lx = sx + math.cos(angle) * (sr + 0.15)
                    ly = sy + math.sin(angle) * (sr + 0.15)
                    if not path_hits_sun(lx, ly, tx, ty):
                        send = min(available, max(12, available // 2))
                        score = 2.0 * int(hub[6]) + 0.4 * int(hub[5]) - 0.05 * eta
                        best = (src[0], angle, int(send), hub[0], score)
                        best_score = score

        if best is not None and best_score is not None and best_score > -999:
            candidates.append(best)

    candidates.sort(key=lambda x: x[4], reverse=True)
    used_sources = set()
    moves = []
    for source_id, angle, send, target_id, score in candidates:
        if source_id in used_sources:
            continue
        src = next((p for p in my_planets if p[0] == source_id), None)
        if src is None:
            continue
        if send > int(src[5]) - reserves[source_id]:
            continue
        if send < MIN_SEND:
            continue
        used_sources.add(source_id)
        moves.append([int(source_id), float(angle), int(send)])

    return moves