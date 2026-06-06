"""
UNIVERSAL ENPV MATH AGENT (v10)
=========================================
Expected Net Present Value (ENPV) Utility Equation.
Evaluates the Global State Matrix iteratively without heuristic rules.
"""

import math
from collections import defaultdict, namedtuple

# =============================================================================
# ENPV WEIGHT MATRIX (DNK)
# =============================================================================
WEIGHTS = {
    "W_eco": 6.0,         # Value of production gain
    "W_deny": 3,        # Value of destroying enemy production
    "W_kill": 3.0,        # Value of raw kinetic impact (killing enemy ships)
    "W_cost": 0.4,        # Cost multiplier for locked fleet time
    "W_time_decay": 0.85, # Time decay exponent (t^decay)
    "W_risk": 3.0,        # Danger of leaving source undefended
    "W_overkill": 1.35,   # Speed overkill multiplier 
}

SUN_X, SUN_Y, SUN_R = 50.0, 50.0, 10.0
SUN_MARGIN = 1.5

Planet = namedtuple("Planet", "id owner x y radius ships production")
Fleet  = namedtuple("Fleet",  "id owner x y angle from_planet_id ships")

def dist(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)

def fleet_speed(n):
    if n <= 1: return 1.0
    ratio = max(0.0, min(1.0, math.log(n) / math.log(1000)))
    return 1.0 + 5.0 * (ratio ** 1.5)

def sun_blocks(sx, sy, tx, ty):
    dx, dy = tx - sx, ty - sy
    L2 = dx*dx + dy*dy
    if L2 < 1e-12: return dist(sx, sy, SUN_X, SUN_Y) < SUN_R
    t = max(0.0, min(1.0, ((SUN_X-sx)*dx + (SUN_Y-sy)*dy) / L2))
    return dist(SUN_X, SUN_Y, sx + t*dx, sy + t*dy) < (SUN_R + SUN_MARGIN)

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

        # Baseline Arrivals Mapping
        self.arrivals_map = defaultdict(list)
        for f in self.fleets:
            tgt, eta = trace_fleet(self, f)
            if tgt is not None:
                self.arrivals_map[tgt].append((eta, f.owner, f.ships))

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

def solve_intercept(w, src_pid, tgt_pid, n_ships, max_h=60):
    src = w.planets.get(src_pid)
    if not src: return None
    speed = fleet_speed(n_ships)
    sx, sy = src.x, src.y
    pos0 = predict_pos(w, tgt_pid, 0)
    if pos0 is None: return None
    est = max(1.0, dist(sx, sy, pos0[0], pos0[1]) / speed)

    for _ in range(8):
        fp = predict_pos(w, tgt_pid, est)
        if fp is None: return None
        new_est = max(1.0, dist(sx, sy, fp[0], fp[1]) / speed)
        if abs(new_est - est) < 0.05:
            est = new_est
            break
        est = 0.5 * est + 0.5 * new_est

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

def simulate_planet(w, tgt_pid, until_turn):
    tgt = w.planets.get(tgt_pid)
    if not tgt: return -1, 0

    owner = tgt.owner
    garrison = float(tgt.ships)
    prod = int(tgt.production)

    by_turn = defaultdict(list)
    for eta, fo, fs in w.arrivals_map.get(tgt_pid, []):
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
# GLOBAL ENPV UTILITY EVALUATOR
# =============================================================================
def calc_utility(w, S, T, F, allocated):
    solver = solve_intercept(w, S.id, T.id, F)
    if not solver: return -float('inf'), 0, 0
    angle, t_arr = solver
    
    # Target state projection at ETA
    proj_owner, proj_garrison = simulate_node_state(w, T.id, t_arr)
    
    E = 0.0
    D = 0.0
    K = 0.0
    
    impact = min(F, proj_garrison)
    
    if proj_owner == w.player:
        # Defend / Reinforce
        success = True
        E = T.production * (500 - (w.step + t_arr)) * 0.1 # Small bonus
    else:
        # Attack / Conquer / Vanguard
        if F > proj_garrison:
            # Capture
            E = T.production * (500 - (w.step + t_arr))
            D = T.production * (500 - (w.step + t_arr)) if T.owner != -1 else 0
            K = impact * (1.5 if T.owner != -1 else 0.5)
        else:
            # Vanguard / Suicide Swarm (Lowers garrison for next fleet)
            K = F * (1.5 if T.owner != -1 else 0.5)
            
    # Time locked cost
    C = F * (t_arr ** WEIGHTS["W_time_decay"])
    
    # Risk calculation
    rem_garrison = max(0, S.ships - allocated[S.id] - F)
    pressure = 0
    for e in w.planets.values():
        if e.owner != w.player and e.owner != -1:
            pressure += e.production / max(1.0, dist(S.x, S.y, e.x, e.y))
            
    R = pressure / (rem_garrison + 1.0)
    
    # Global ENPV Equation
    U = (WEIGHTS["W_eco"] * E) + (WEIGHTS["W_deny"] * D) + (WEIGHTS["W_kill"] * K) - (WEIGHTS["W_cost"] * C) - (WEIGHTS["W_risk"] * R)
    
    return U, angle, t_arr

def simulate_node_state(w, tgt_pid, until_turn):
    return simulate_planet(w, tgt_pid, until_turn)

# =============================================================================
# AGENT LOOP
# =============================================================================
def agent(obs, config=None):
    w = World(obs)
    player = w.player

    my_planets = [p for p in w.planets.values() if p.owner == player]
    if not my_planets: return []

    moves = []
    allocated = defaultdict(int)
    
    # We greedily evaluate and dispatch the highest ENPV moves until no positive utility moves remain.
    while True:
        best_U = 0 # Utility must be > 0 to be executed
        best_move = None
        
        for S in my_planets:
            avail = int(S.ships) - allocated[S.id]
            if avail < 10: continue # Minimum operational threshold
            
            for T in w.planets.values():
                if S.id == T.id: continue
                if T.id in w.comet_ids: continue
                
                # Fast elimination filter
                rough_eta = max(1.0, dist(S.x, S.y, T.x, T.y) / 3.0)
                proj_owner, proj_garrison = simulate_node_state(w, T.id, int(rough_eta))
                
                required = proj_garrison + (5 if T.owner != -1 else 1)
                
                F_candidates = set()
                # Option 1: Exact calculation (if possible)
                if required <= avail:
                    F_candidates.add(required)
                    # Option 2: Overkill for speed
                    F_candidates.add(min(avail, int(required * WEIGHTS["W_overkill"]) + 15))
                
                # Option 3: Send Max (either for Speed or as Vanguard for Coalition)
                F_candidates.add(avail)
                
                for F in F_candidates:
                    if F < 10: continue
                    U, angle, t_arr = calc_utility(w, S, T, F, allocated)
                    
                    if U > best_U:
                        best_U = U
                        best_move = (S, T, F, angle, t_arr)
                        
        if best_move is not None:
            S, T, F, angle, t_arr = best_move
            moves.append([int(S.id), float(angle), int(F)])
            
            # Commit resources
            allocated[S.id] += F
            
            # Inject into Global Space Matrix for emergent Coalition
            w.arrivals_map[T.id].append((t_arr, player, F))
        else:
            # No profitable moves left under ENPV threshold
            break

    return moves
