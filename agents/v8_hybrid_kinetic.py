"""
HYBRID KINETIC AGENT (v8)
=======================================
Bu model, 1/5 udmuş olan `adaptive_pressure_v1` modelinin 
Möhkəm Kinematikası ilə `vector_field_v1`-in Qradient Axını 
və Massive Overkill (Hammer) məntiqinin birləşməsidir.

Bu model artıq qərar verərkən "qıfıllanmır" və vkhydras kimi
böyük kütlələrlə (1.35x Overkill) hücum edir.
"""

import math
from collections import defaultdict, namedtuple

# =============================================================================
# CONSTANTS & WEIGHTS (RL-Ready)
# =============================================================================
BOARD = 100.0
SUN_X, SUN_Y, SUN_R = 50.0, 50.0, 10.0
SUN_MARGIN = 1.5

W = {
    "reserve_mult":   2.0,    # garrison reserve = prod × this
    "late_reserve":   5,      # late game reserve (flat)
    "neutral_mult":   1.2,    # neutral target bonus
    "enemy_mult":     2.0,    # enemy target bonus (attrition)
    "overkill_mult":  1.35,   # Hammer overkill ratio
    "overkill_flat":  15,     # Hammer flat bonus
    "min_deploy":     10,     # minimum deployable to act
    "snipe_min":      20,     # minimum available for sniper
    "flow_thresh":    1.5,    # Gradient potential multiplier to trigger flow
}

Planet = namedtuple("Planet", "id owner x y radius ships production")
Fleet  = namedtuple("Fleet",  "id owner x y angle from_planet_id ships")

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
# KINEMATICS & TRACING
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
    ip = w.initial.get(pid)
    if ip is None: return p.x, p.y
    r = dist(ip.x, ip.y, SUN_X, SUN_Y)
    current_phase = math.atan2(p.y - SUN_Y, p.x - SUN_X)
    future_phase = current_phase + w.ang_vel * t
    return SUN_X + r * math.cos(future_phase), SUN_Y + r * math.sin(future_phase)

def solve_intercept(w, src_pid, tgt_pid, n_ships, max_h=50):
    src = w.planets.get(src_pid)
    if not src: return None
    speed = fleet_speed(max(10, n_ships)) # Prevent crawling
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
    if fp[0] < 0 or fp[0] > 100 or fp[1] < 0 or fp[1] > 100: return None
    if sun_blocks(sx, sy, fp[0], fp[1]): return None
    return math.atan2(fp[1] - sy, fp[0] - sx), flight

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

def simulate_planet(w, tgt_pid, until_turn, arrivals_map):
    tgt = w.planets.get(tgt_pid)
    if not tgt: return -1, 0

    owner = tgt.owner
    garrison = float(tgt.ships)
    prod = int(tgt.production)

    by_turn = defaultdict(list)
    for eta, fo, fs in arrivals_map.get(tgt_pid, []):
        by_turn[eta].append((fo, fs))

    for t in range(1, until_turn + 1):
        if owner != -1: garrison += prod
        turn_fleets = by_turn.get(t, [])
        if not turn_fleets: continue

        fleet_groups = defaultdict(int)
        for fo, fs in turn_fleets:
            fleet_groups[fo] += fs

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

        if survivor_ships > 0:
            if owner == survivor_owner:
                garrison += survivor_ships
            else:
                garrison -= survivor_ships
                if garrison < 0:
                    owner = survivor_owner
                    garrison = -garrison

    return owner, max(0, int(garrison))

# =============================================================================
# AGENT CORE
# =============================================================================
def agent(obs, config=None):
    w = World(obs)
    player = w.player

    my_planets = [p for p in w.planets.values() if p.owner == player]
    if not my_planets: return []

    is_late = w.step > 350
    moves = []
    allocated = defaultdict(int)
    targeted = set()

    arrivals_map = trace_all_fleets(w)

    # ================================================================
    # TACTIC 1: TEMPORAL SNIPING
    # ================================================================
    for tgt in w.planets.values():
        if tgt.id in w.comet_ids: continue
        arrs = arrivals_map.get(tgt.id, [])
        if not arrs: continue

        for t_frame in sorted(set(a[0] for a in arrs)):
            proj_owner, proj_garrison = simulate_planet(w, tgt.id, t_frame, arrivals_map)
            if proj_owner == player or proj_owner == -1: continue

            for src in sorted(my_planets, key=lambda p: p.ships, reverse=True):
                avail = int(src.ships) - allocated[src.id]
                if avail < W["snipe_min"]: continue

                required = proj_garrison + 5
                required = max(required, 15)
                
                r = solve_intercept(w, src.id, tgt.id, required)
                if r is None: continue
                angle, turns = r

                if turns == t_frame + 1 and required <= avail:
                    moves.append([int(src.id), float(angle), int(required)])
                    allocated[src.id] += required
                    targeted.add(tgt.id)
                    break

    # ================================================================
    # TACTIC 2: KINETIC VALUE SCORING (WITH OVERKILL HAMMER)
    # ================================================================
    for src in sorted(my_planets, key=lambda p: p.ships, reverse=True):
        avail = int(src.ships) - allocated[src.id]
        if w.step < 100:
            reserve = 0
        else:
            reserve = int(src.production * W["reserve_mult"]) if not is_late else W["late_reserve"]
        deployable = avail - reserve
        
        if deployable < W["min_deploy"]: continue

        best_score = -float('inf')
        best_target = None
        best_profile = None

        for tgt in w.planets.values():
            if tgt.id == src.id or tgt.owner == player: continue
            if tgt.id in w.comet_ids or tgt.id in targeted: continue

            r = solve_intercept(w, src.id, tgt.id, deployable, max_h=35)
            if r is None: continue
            angle, turns = r

            proj_owner, landing_garrison = simulate_planet(w, tgt.id, turns, arrivals_map)
            if proj_owner == player: continue
                
            required = landing_garrison + (5 if tgt.owner != -1 else 1)
            
            # Massive Overkill ONLY on enemies
            if tgt.owner != -1:
                hammer_force = int(required * W["overkill_mult"]) + W["overkill_flat"]
            else:
                hammer_force = max(required, 10) # Send at least 10 so the fleet moves fast!
                
            actual_send = min(deployable, hammer_force)
            
            if actual_send < required: continue

            dist_factor = max(1.0, float(turns))
            prod_value = (tgt.production + 1.0) ** 2
            owner_mult = W["neutral_mult"] if tgt.owner == -1 else W["enemy_mult"]

            score = (prod_value * owner_mult) / (required * dist_factor)

            if score > best_score:
                best_score = score
                best_target = tgt
                best_profile = (angle, turns, actual_send)

        if best_target and best_profile:
            angle, turns, force = best_profile
            moves.append([int(src.id), float(angle), int(force)])
            allocated[src.id] += force
            targeted.add(best_target.id)

    # ================================================================
    # TACTIC 3: GRADIENT FLOW LOGISTICS (POTENTIAL FIELDS)
    # ================================================================
    potentials = {}
    enemies = [p for p in w.planets.values() if p.owner != player]
    for p in my_planets:
        pot = p.production * 10.0
        for e in enemies:
            d = max(1.0, dist(p.x, p.y, e.x, e.y))
            pot += (e.production * 100.0) / d
        potentials[p.id] = pot

    if w.step > 20 and len(my_planets) > 1:
        for src in my_planets:
            avail = int(src.ships) - allocated[src.id]
            if avail < W["min_deploy"] * 2: continue
            
            best_friend = None
            best_grad = 0.0
            for friend in my_planets:
                if friend.id == src.id: continue
                if potentials[friend.id] > potentials[src.id] * W["flow_thresh"]:
                    d = max(1.0, dist(src.x, src.y, friend.x, friend.y))
                    grad = (potentials[friend.id] - potentials[src.id]) / d
                    if grad > best_grad:
                        best_grad = grad
                        best_friend = friend
                        
            if best_friend:
                feed = int(avail * 0.5) # Don't drain completely, send 50% waves
                if feed >= W["min_deploy"]:
                    r = solve_intercept(w, src.id, best_friend.id, feed)
                    if r:
                        angle, _ = r
                        moves.append([int(src.id), float(angle), int(feed)])
                        allocated[src.id] += feed

    return moves
