"""
ADAPTIVE PRESSURE v1 — Strategic Agent
=======================================
Sıfırdan yazılıb. Strategiya: doc/strategy.md

Taktikalar:
  1. Temporal Sniping — düşmən fəthindən sonra zəif qarnizonu vur
  2. Kinetic Value Scoring — prod²/cost formulası ilə hədəf seçimi
  3. Backline Drain — arxa cəbhədən ön xəttə transfer
  4. Phase-Adaptive — erkən genişlənmə, gec hücum
"""

import math
from collections import defaultdict, namedtuple

# =============================================================================
# CONSTANTS
# =============================================================================
BOARD = 100.0
SUN_X, SUN_Y, SUN_R = 50.0, 50.0, 10.0
SUN_MARGIN = 1.5
TOTAL_TURNS = 500

Planet = namedtuple("Planet", "id owner x y radius ships production")
Fleet  = namedtuple("Fleet",  "id owner x y angle from_planet_id ships")

# =============================================================================
# WEIGHTS — RL-ready dict
# =============================================================================
W = {
    "reserve_mult":   2.5,    # garrison reserve = prod × this
    "late_reserve":   5,      # late game reserve (flat)
    "neutral_mult":   1.3,    # neutral target bonus
    "enemy_mult":     1.9,    # enemy target bonus (attrition)
    "drain_pct":      0.35,   # backline drain percentage
    "drain_thresh":   30,     # min ships for drain
    "backline_dist":  35.0,   # no enemies within this = backline
    "min_deploy":     10,     # minimum deployable to act
    "snipe_min":      15,     # minimum available for sniper
}

# =============================================================================
# MATH
# =============================================================================
def dist(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)

def fleet_speed(n):
    if n <= 1: return 1.0
    ratio = max(0.0, min(1.0, math.log(n) / math.log(1000)))
    return 1.0 + 5.0 * (ratio ** 1.5)

def sun_blocks(sx, sy, tx, ty):
    dx, dy = tx - sx, ty - sy
    L2 = dx*dx + dy*dy
    if L2 < 1e-12:
        return dist(sx, sy, SUN_X, SUN_Y) < SUN_R
    t = max(0.0, min(1.0, ((SUN_X-sx)*dx + (SUN_Y-sy)*dy) / L2))
    return dist(SUN_X, SUN_Y, sx + t*dx, sy + t*dy) < (SUN_R + SUN_MARGIN)

# =============================================================================
# WORLD
# =============================================================================
def _g(obs, key, default=None):
    return obs.get(key, default) if isinstance(obs, dict) else getattr(obs, key, default)

class World:
    def __init__(self, obs):
        self.player  = _g(obs, "player", 0)
        self.step    = _g(obs, "step", 0)
        self.ang_vel = _g(obs, "angular_velocity", 0.0)

        self.planets = {p[0]: Planet(*p) for p in _g(obs, "planets", [])}
        self.fleets  = [Fleet(*f) for f in _g(obs, "fleets", [])]
        self.initial = {p[0]: Planet(*p) for p in _g(obs, "initial_planets", [])}

        self.comet_ids = set(int(x) for x in _g(obs, "comet_planet_ids", []))
        self.comet_paths = {}
        for group in _g(obs, "comets", []):
            pids  = _g(group, "planet_ids", [])
            paths = _g(group, "paths", [])
            pidx  = _g(group, "path_index", 0)
            for i, pid in enumerate(pids):
                if i < len(paths):
                    self.comet_paths[pid] = (paths[i], pidx)

        self.orbital = {}
        for pid, ip in self.initial.items():
            if pid in self.comet_ids:
                self.orbital[pid] = False
            else:
                r = dist(ip.x, ip.y, SUN_X, SUN_Y)
                self.orbital[pid] = (r + ip.radius < 50.0)

# =============================================================================
# POSITION PREDICTION
# =============================================================================
def predict_pos(w, pid, t):
    if pid in w.comet_paths:
        path, pidx = w.comet_paths[pid]
        fi = int(pidx) + int(t)
        if 0 <= fi < len(path):
            return float(path[fi][0]), float(path[fi][1])
        return None
    p = w.planets.get(pid)
    if p is None: return None
    if not w.orbital.get(pid, False):
        return p.x, p.y
    # Use current position + angular velocity (like main.py)
    # More robust — no step counter dependency
    ip = w.initial.get(pid)
    if ip is None: return p.x, p.y
    r = dist(ip.x, ip.y, SUN_X, SUN_Y)
    current_phase = math.atan2(p.y - SUN_Y, p.x - SUN_X)
    future_phase = current_phase + w.ang_vel * t
    return SUN_X + r * math.cos(future_phase), SUN_Y + r * math.sin(future_phase)

# =============================================================================
# INTERCEPTION SOLVER
# =============================================================================
def solve_intercept(w, src_pid, tgt_pid, n_ships, max_h=50):
    src = w.planets.get(src_pid)
    if not src: return None
    speed = fleet_speed(n_ships)
    sx, sy = src.x, src.y
    pos0 = predict_pos(w, tgt_pid, 0)
    if pos0 is None: return None
    est = max(1.0, dist(sx, sy, pos0[0], pos0[1]) / speed)

    for _ in range(10):
        fp = predict_pos(w, tgt_pid, est)
        if fp is None: return None
        new_est = max(1.0, dist(sx, sy, fp[0], fp[1]) / speed)
        if abs(new_est - est) < 0.05:
            est = new_est
            break
        est = 0.6 * est + 0.4 * new_est

    flight = int(math.ceil(est))
    if flight > max_h: return None
    fp = predict_pos(w, tgt_pid, flight)
    if fp is None: return None
    # Xəritədən kənara çıxarsa, getmə! (Kometlər üçün xüsusilə vacibdir)
    if fp[0] < 0 or fp[0] > 100 or fp[1] < 0 or fp[1] > 100:
        return None
        
    if sun_blocks(sx, sy, fp[0], fp[1]): return None
    return math.atan2(fp[1] - sy, fp[0] - sx), flight

# =============================================================================
# RAY TRACING
# =============================================================================
def trace_fleet(w, f, max_t=80):
    speed = fleet_speed(f.ships)
    vx, vy = speed * math.cos(f.angle), speed * math.sin(f.angle)
    for t in range(1, max_t + 1):
        fx, fy = f.x + vx * t, f.y + vy * t
        if fx < -5 or fx > 105 or fy < -5 or fy > 105: return None, None
        if dist(fx, fy, SUN_X, SUN_Y) <= SUN_R: return None, None
        for pid, p in w.planets.items():
            pos = predict_pos(w, pid, t)
            if pos and dist(fx, fy, pos[0], pos[1]) <= p.radius:
                return pid, t
    return None, None

def trace_all_fleets(w):
    arrivals = defaultdict(list)
    for f in w.fleets:
        tgt, eta = trace_fleet(w, f)
        if tgt is not None:
            arrivals[tgt].append((eta, f.owner, f.ships))
    return arrivals

# =============================================================================
# COMBAT SIMULATOR — FIXED: fleets fight first, then survivor vs garrison
# =============================================================================
def simulate_planet(w, tgt_pid, until_turn, arrivals_map):
    """
    Düzgün döyüş həlli:
    1. Gələn fleetlər öz aralarında vuruşur (ən güclü - ikinci ən güclü)
    2. Qalib fleet (survivor) garrison ilə vuruşur
    3. Əgər garrison mənfi olarsa, ownership dəyişir
    """
    tgt = w.planets.get(tgt_pid)
    if not tgt: return -1, 0

    owner = tgt.owner
    garrison = float(tgt.ships)
    prod = int(tgt.production)

    # Pre-index arrivals by turn for speed
    by_turn = defaultdict(list)
    for eta, fo, fs in arrivals_map.get(tgt_pid, []):
        by_turn[eta].append((fo, fs))

    for t in range(1, until_turn + 1):
        # Production
        if owner != -1:
            garrison += prod

        # Fleet arrivals this turn
        turn_fleets = by_turn.get(t, [])
        if not turn_fleets:
            continue

        # Group fleets by owner
        fleet_groups = defaultdict(int)
        for fo, fs in turn_fleets:
            fleet_groups[fo] += fs

        # Fleet combat: strongest fleet wins, survivor = top - second
        sorted_g = sorted(fleet_groups.items(), key=lambda x: -x[1])
        top_owner, top_ships = sorted_g[0]

        survivor_ships = top_ships
        survivor_owner = top_owner
        if len(sorted_g) > 1:
            if top_ships == sorted_g[1][1]:
                survivor_ships = 0
                survivor_owner = -1
            else:
                survivor_ships = top_ships - sorted_g[1][1]

        # Survivor vs garrison
        if survivor_ships > 0:
            if owner == survivor_owner:
                garrison += survivor_ships   # reinforcement
            else:
                garrison -= survivor_ships
                if garrison < 0:
                    owner = survivor_owner
                    garrison = -garrison

    return owner, max(0, int(garrison))


# =============================================================================
# MAIN AGENT
# =============================================================================
def agent(obs, config=None):
    w = World(obs)
    player = w.player

    my_planets = [p for p in w.planets.values() if p.owner == player]
    if not my_planets:
        return []

    is_late = w.step > 350
    moves = []
    allocated = defaultdict(int)  # src_pid → ships committed
    targeted = set()

    # Ray trace all fleets
    arrivals_map = trace_all_fleets(w)

    # ================================================================
    # TACTIC 1: TEMPORAL SNIPING
    # ================================================================
    # Düşmən fleet planeti fəth edəndən dəqiq 1 tur sonra aşağı qarnizonu vur
    for tgt in w.planets.values():
        if tgt.id in w.comet_ids:
            continue
        arrs = arrivals_map.get(tgt.id, [])
        if not arrs:
            continue

        for t_frame in sorted(set(a[0] for a in arrs)):
            proj_owner, proj_garrison = simulate_planet(w, tgt.id, t_frame, arrivals_map)

            if proj_owner == player or proj_owner == -1:
                continue

            # Find a sniper source
            for src in sorted(my_planets, key=lambda p: p.ships, reverse=True):
                avail = int(src.ships) - allocated[src.id]
                if avail < W["snipe_min"]:
                    continue

                required = proj_garrison + 2
                required = max(required, 10)  # Çox yavaş olmasın deyə minimum 10
                
                r = solve_intercept(w, src.id, tgt.id, required)
                if r is None:
                    continue
                angle, turns = r

                # Must arrive exactly at t_frame + 1
                if turns == t_frame + 1 and required <= avail:
                    moves.append([int(src.id), float(angle), int(required)])
                    allocated[src.id] += required
                    targeted.add(tgt.id)
                    break

    # ================================================================
    # TACTIC 2: KINETIC VALUE SCORING
    # ================================================================
    # Hər source planet üçün ən yaxşı hədəfi tap, kifayət qədər gəmi göndər
    for src in sorted(my_planets, key=lambda p: p.ships, reverse=True):
        avail = int(src.ships) - allocated[src.id]

        # Reserve calculation
        reserve = int(src.production * W["reserve_mult"]) if not is_late else W["late_reserve"]
        deployable = avail - reserve
        if deployable < W["min_deploy"]:
            continue

        best_score = -float('inf')
        best_target = None
        best_profile = None  # (angle, turns, ships_to_send)

        for tgt in w.planets.values():
            if tgt.id == src.id or tgt.owner == player:
                continue
            if tgt.id in w.comet_ids or tgt.id in targeted:
                continue

            # Solve interception
            r = solve_intercept(w, src.id, tgt.id, deployable, max_h=35)
            if r is None:
                continue
            angle, turns = r

            # Predict garrison at landing
            proj_owner, landing_garrison = simulate_planet(w, tgt.id, turns, arrivals_map)
            
            if proj_owner == player:
                continue # Bizim fleet artıq yoldadır və fəth edəcək, selə ehtiyac yoxdur!
                
            required = landing_garrison + (5 if tgt.owner != -1 else 1)
            required = max(required, 10)  # Yavaş uçmamaq üçün 1 fleetlik selin qarşısını al

            if required > deployable:
                continue

            # Score: (production + 1)² × owner_mult / (required × distance)
            dist_factor = max(1.0, float(turns))
            prod_value = (tgt.production + 1.0) ** 2

            if tgt.owner == -1:
                owner_mult = W["neutral_mult"]
            else:
                owner_mult = W["enemy_mult"]

            score = (prod_value * owner_mult) / (required * dist_factor)

            if score > best_score:
                best_score = score
                best_target = tgt
                best_profile = (angle, turns, required)

        if best_target and best_profile:
            angle, turns, force = best_profile
            moves.append([int(src.id), float(angle), int(force)])
            allocated[src.id] += force
            targeted.add(best_target.id)

    # ================================================================
    # TACTIC 3: BACKLINE DRAIN
    # ================================================================
    if w.step > 30 and len(my_planets) > 2:
        for src in my_planets:
            if allocated[src.id] > 0:
                continue  # artıq göndərib

            # Backline check: no enemy within range
            is_back = True
            for hp in w.planets.values():
                if hp.owner >= 0 and hp.owner != player:
                    if dist(src.x, src.y, hp.x, hp.y) < W["backline_dist"]:
                        is_back = False
                        break

            if not is_back or src.ships < W["drain_thresh"]:
                continue

            feed = int(src.ships * W["drain_pct"])

            # Find closest friendly planet
            closest = None
            min_d = float('inf')
            for c in my_planets:
                if c.id == src.id:
                    continue
                d = dist(src.x, src.y, c.x, c.y)
                if d < min_d:
                    min_d = d
                    closest = c

            if closest:
                r = solve_intercept(w, src.id, closest.id, feed)
                if r:
                    angle, _ = r
                    moves.append([int(src.id), float(angle), int(feed)])
                    allocated[src.id] += feed

    return moves
