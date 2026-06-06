import math
import random
from collections import defaultdict, namedtuple

# ==============================================================================
# 1. KINEMATIC ENGINE CONSTANTS
# ==============================================================================
BOARD_SIZE = 100.0
SUN_X, SUN_Y, SUN_RADIUS = 50.0, 50.0, 10.0
SUN_SAFETY_MARGIN = 1.5
MAX_SPEED = 6.0
SIM_HORIZON = 80 # Neçə gediş irəlini simulyasiya edəcəyik

Planet = namedtuple("Planet", ["id", "owner", "x", "y", "radius", "ships", "production"])
Fleet = namedtuple("Fleet", ["id", "owner", "x", "y", "angle", "from_planet_id", "ships"])

# ==============================================================================
# 2. BASIC MATH & GEOMETRY
# ==============================================================================
def get_distance(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)

def get_fleet_speed(ships: int) -> float:
    if ships <= 1: 
        return 1.0
    ratio = max(0.0, min(1.0, math.log(ships) / math.log(1000.0)))
    return 1.0 + (MAX_SPEED - 1.0) * (ratio ** 1.5)

def normalize_angle(angle):
    while angle > math.pi: angle -= 2 * math.pi
    while angle < -math.pi: angle += 2 * math.pi
    return angle

def point_to_segment_distance(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    seg_sq = dx * dx + dy * dy
    if seg_sq <= 1e-9:
        return get_distance(px, py, x1, y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_sq))
    return get_distance(px, py, x1 + t * dx, y1 + t * dy)

def is_path_blocked_by_sun(sx, sy, tx, ty, target_radius=0):
    total_dist = get_distance(sx, sy, tx, ty)
    if total_dist < 1e-9: return False
    dist_to_sun = point_to_segment_distance(SUN_X, SUN_Y, sx, sy, tx, ty)
    return dist_to_sun < (SUN_RADIUS + SUN_SAFETY_MARGIN)

# ==============================================================================
# 3. DYNAMIC KINEMATICS & ORBIT PREDICTION
# ==============================================================================
class KinematicsState:
    def __init__(self, obs):
        self.step = obs.get("step", 0) if isinstance(obs, dict) else getattr(obs, "step", 0)
        self.global_ang_vel = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else getattr(obs, "angular_velocity", 0.0)
        self.comets_data = obs.get("comets", []) if isinstance(obs, dict) else getattr(obs, "comets", [])
        
        raw_planets = obs.get("planets", []) if isinstance(obs, dict) else getattr(obs, "planets", [])
        raw_init = obs.get("initial_planets", []) if isinstance(obs, dict) else getattr(obs, "initial_planets", [])
        
        self.planets = {p[0]: Planet(*p) for p in raw_planets}
        self.initial_planets = {p[0]: Planet(*p) for p in raw_init}
        
        self.planet_kinematics = {}
        self.comet_ids = set()
        
        for group in self.comets_data:
            pids = group.get("planet_ids", []) if isinstance(group, dict) else getattr(group, "planet_ids", [])
            for pid in pids: self.comet_ids.add(pid)
        
        self._calculate_kinematics()

    def _calculate_kinematics(self):
        for pid, current_p in self.planets.items():
            if pid in self.comet_ids:
                self.planet_kinematics[pid] = {"is_orbital": False, "ang_vel": 0.0, "radius": 0.0, "init_phase": 0.0, "curr_phase": 0.0}
                continue
                
            init_p = self.initial_planets.get(pid, current_p)
            r = get_distance(init_p.x, init_p.y, SUN_X, SUN_Y)
            
            is_orbital = (r + init_p.radius < 45.0)
            ang_vel = self.global_ang_vel if is_orbital else 0.0
            curr_angle = math.atan2(current_p.y - SUN_Y, current_p.x - SUN_X)
            
            self.planet_kinematics[pid] = {
                "is_orbital": is_orbital,
                "ang_vel": ang_vel,
                "radius": r,
                "init_phase": math.atan2(init_p.y - SUN_Y, init_p.x - SUN_X),
                "curr_phase": curr_angle
            }

    def predict_target_position(self, target_id, turns_ahead):
        if target_id in self.comet_ids:
            return self._predict_comet(target_id, turns_ahead)
            
        kinematics = self.planet_kinematics.get(target_id)
        if not kinematics or not kinematics["is_orbital"]:
            p = self.planets.get(target_id)
            return (p.x, p.y) if p else None
            
        total_turns = self.step + turns_ahead
        new_phase = kinematics["init_phase"] + kinematics["ang_vel"] * total_turns
        r = kinematics["radius"]
        return SUN_X + r * math.cos(new_phase), SUN_Y + r * math.sin(new_phase)

    def _predict_comet(self, comet_id, turns_ahead):
        for group in self.comets_data:
            pids = group.get("planet_ids", []) if isinstance(group, dict) else getattr(group, "planet_ids", [])
            if comet_id not in pids: continue
            idx = pids.index(comet_id)
            paths = group.get("paths", []) if isinstance(group, dict) else getattr(group, "paths", [])
            path_index = group.get("path_index", 0) if isinstance(group, dict) else getattr(group, "path_index", 0)
            
            if idx >= len(paths): return None
            future_idx = int(path_index) + int(turns_ahead)
            if 0 <= future_idx < len(paths[idx]):
                return float(paths[idx][future_idx][0]), float(paths[idx][future_idx][1])
            return None
        return None

# ==============================================================================
# 4. RAY TRACING & TIMELINE SIMULATOR
# ==============================================================================
def predict_fleet_destinations(obs_fleets, k_state: KinematicsState, max_turns=SIM_HORIZON):
    destinations = []
    
    for f in obs_fleets:
        f_id, f_owner, f_x, f_y, f_angle, f_from, f_ships = f
        speed = get_fleet_speed(f_ships)
        vx = speed * math.cos(f_angle)
        vy = speed * math.sin(f_angle)
        
        curr_x, curr_y = f_x, f_y
        for t in range(1, max_turns + 1):
            curr_x += vx
            curr_y += vy
            
            if get_distance(curr_x, curr_y, SUN_X, SUN_Y) <= SUN_RADIUS:
                break # destroyed by sun
                
            matched = False
            for pid, planet in k_state.planets.items():
                pp = k_state.predict_target_position(pid, t)
                if pp is None: continue
                px, py = pp
                
                if get_distance(curr_x, curr_y, px, py) <= planet.radius:
                    destinations.append({
                        "fleet_id": f_id,
                        "owner": f_owner,
                        "ships": f_ships,
                        "target_id": pid,
                        "arrival_turn": t
                    })
                    matched = True
                    break
            if matched: break
            
    return destinations

class TimelineSimulator:
    def __init__(self, k_state: KinematicsState, fleet_destinations):
        self.k_state = k_state
        self.planets = k_state.planets
        
        self.arrivals = defaultdict(lambda: defaultdict(list))
        for dest in fleet_destinations:
            self.arrivals[dest["target_id"]][dest["arrival_turn"]].append({
                "owner": dest["owner"],
                "ships": dest["ships"]
            })
            
        self.timelines = defaultdict(dict)
        self.SIM_HORIZON = SIM_HORIZON
        self._simulate_all()

    def _simulate_all(self):
        for pid, planet in self.planets.items():
            curr_owner = planet.owner
            curr_ships = planet.ships
            prod = planet.production
            
            for t in range(1, self.SIM_HORIZON + 1):
                # İstehsal (Production davam edir - sıfır gəmi qalsa belə fəth olunmayıbsa)
                if curr_owner != -1:
                    curr_ships += prod
                
                arrs = self.arrivals[pid].get(t, [])
                if arrs:
                    forces = defaultdict(int)
                    if curr_owner != -1:
                        forces[curr_owner] = curr_ships
                    else:
                        forces[-1] = curr_ships # Neytral qüvvə
                        
                    for a in arrs:
                        forces[a["owner"]] += a["ships"]
                        
                    sorted_forces = sorted(forces.items(), key=lambda x: x[1], reverse=True)
                    
                    if len(sorted_forces) == 1:
                        curr_owner, curr_ships = sorted_forces[0]
                    else:
                        top1_owner, top1_ships = sorted_forces[0]
                        top2_owner, top2_ships = sorted_forces[1]
                        
                        curr_ships = top1_ships - top2_ships
                        if curr_ships == 0:
                            curr_owner = -1 # Bərabərlik varsa neytrallaşır
                        else:
                            curr_owner = top1_owner
                            
                self.timelines[pid][t] = (curr_owner, curr_ships)

    def get_cost_to_capture(self, pid, arrival_turn, my_player_id):
        if arrival_turn == 1:
            prev_owner = self.planets[pid].owner
            prev_ships = self.planets[pid].ships
        else:
            prev_owner, prev_ships = self.timelines[pid].get(arrival_turn - 1, (self.planets[pid].owner, self.planets[pid].ships))
            
        prod = self.planets[pid].production
        current_ships = prev_ships
        if prev_owner != -1:
            current_ships += prod
            
        arrs = self.arrivals[pid].get(arrival_turn, [])
        forces = defaultdict(int)
        if prev_owner != -1:
            forces[prev_owner] = current_ships
        else:
            forces[-1] = current_ships
            
        for a in arrs:
            forces[a["owner"]] += a["ships"]
            
        my_current_force = forces.get(my_player_id, 0)
        max_enemy_force = 0
        for owner, ships in forces.items():
            if owner != my_player_id and ships > max_enemy_force:
                max_enemy_force = ships
                
        # Döyüşdə qalib gəlmək (yaxud qorumaq) üçün tələb olunan minimum gəmi
        if my_player_id == prev_owner:
            S = max_enemy_force - my_current_force # Qoruyan heç-heçədə qalib gəlir (və ya neytrallaşmır)
        else:
            S = max_enemy_force - my_current_force + 1 # Hücumçu mütləq üstələməlidir
            
        return max(0, S)

# ==============================================================================
# 5. ITERATIVE INTERCEPTION ALGORITHM
# ==============================================================================
def aim_at_target(src_planet, target_planet, num_ships, k_state: KinematicsState, max_iters=5):
    speed = get_fleet_speed(num_ships)
    
    # 1. Təxmini vaxtı tapırıq (Iterative estimation)
    dist = get_distance(src_planet.x, src_planet.y, target_planet.x, target_planet.y)
    est_turns = max(1.0, dist / speed)
    
    for _ in range(max_iters):
        predicted_pos = k_state.predict_target_position(target_planet.id, est_turns)
        if not predicted_pos: return None
        px, py = predicted_pos
        dist = get_distance(src_planet.x, src_planet.y, px, py)
        est_turns = max(1.0, dist / speed)
        
    # 2. Diskret mühit üçün tam dəqiq çatma anını (Tunneling / Overshoot problemi) həll edirik
    base_t = int(round(est_turns))
    best_t = None
    best_aim = None
    min_miss = float('inf')
    
    # Ətrafdakı turnləri yoxlayırıq ki, gəmi hədəfin "radiusu" içinə hansı turda düşür
    for t in (base_t, base_t + 1, base_t - 1, base_t + 2):
        if t < 1: continue
        pp = k_state.predict_target_position(target_planet.id, t)
        if not pp: continue
        px, py = pp
        
        fleet_travel_dist = t * speed
        actual_dist = get_distance(src_planet.x, src_planet.y, px, py)
        
        if is_path_blocked_by_sun(src_planet.x, src_planet.y, px, py, target_planet.radius):
            continue
            
        miss_dist = abs(fleet_travel_dist - actual_dist)
        
        # Əgər radiusun içinə düşürsə tam dəqiq vurduq!
        if miss_dist <= target_planet.radius:
            angle = math.atan2(py - src_planet.y, px - src_planet.x)
            return angle, t
            
        if miss_dist < min_miss:
            min_miss = miss_dist
            best_t = t
            best_aim = math.atan2(py - src_planet.y, px - src_planet.x)
            
    # Heç bir turda tam radiusa girmirsə, ən yaxın olanı qaytarırıq (bəlkə continuous collision tutur)
    if best_aim is not None:
        return best_aim, best_t
        
    return None


def find_valid_plan(src, tgt, timeline: TimelineSimulator, avail, player, k_state: KinematicsState):
    valid_plans = []
    
    for T in range(1, timeline.SIM_HORIZON + 1):
        S_combat = timeline.get_cost_to_capture(tgt.id, T, player)
        if S_combat > avail: continue
        
        predicted_pos = k_state.predict_target_position(tgt.id, T)
        if not predicted_pos: continue
        px, py = predicted_pos
        
        actual_dist = get_distance(src.x, src.y, px, py)
        req_speed = actual_dist / T
        
        if req_speed > MAX_SPEED: continue
        
        if req_speed <= 1.0:
            S_speed = 1
        else:
            ratio = ((req_speed - 1.0) / (MAX_SPEED - 1.0)) ** (1.0 / 1.5)
            S_speed = int(math.ceil(1000.0 ** ratio))
            
        S_final = max(S_combat, S_speed)
        if S_final > avail: continue
        
        aim = aim_at_target(src, tgt, S_final, k_state)
        if aim is None: continue
        angle, t_actual = aim
        
        # Əgər hesabladığımız çatma vaxtında S_final kifayətdirsə, bu uğurlu plandır
        if S_final >= timeline.get_cost_to_capture(tgt.id, t_actual, player):
            valid_plans.append({"T": t_actual, "ships": S_final, "angle": angle})
            
    return valid_plans

# ==============================================================================
# ==============================================================================
# 6. ADVANCED STRATEGY LAYER: LAGRANGIAN RELAXATION
# ==============================================================================

# Hyperparameters for Lagrangian Strategy Layer
W_PROD    = 1.00   # Value of 1 ship/turn of production over the horizon
W_SHIPS   = 0.30   # Value of 1 garrison ship at the horizon
W_OPP     = 0.15   # Penalty: 1 ship absent for 1 turn costs OPP * prod_eff
W_FORT    = 0.05   # Bonus: 1 extra ship left on captured planet * prod_j
W_DISRUPT = 0.90   # Enemy double-swing multiplier
W_DEFENSE = 5.00   # Emergency-defence premium
W_LOGISTICS_DISC = 0.35
LOGISTICS_MIN_SURPLUS = 5

def _global_snapshot(k_state, player):
    """
    Compute per-player economic and military totals from current k_state.

    Returns
    -------
    my_prod        : float  – my production rate (ships / turn)
    my_ships       : float  – my total garrison across all planets
    leader_id      : int    – opponent with highest production (None if no enemies)
    leader_prod    : float  – leader's production rate
    aggression     : float  – 1.0 + min(2, eco_gap / my_prod)  ∈ [1, 3]
    player_prod    : dict   – pid → production
    player_garrison: dict   – pid → garrison ships on planets
    """
    player_prod     = defaultdict(float)
    player_garrison = defaultdict(float)

    for p in k_state.planets.values():
        player_prod    [p.owner] += p.production
        player_garrison[p.owner] += p.ships

    my_prod  = player_prod    [player]
    my_ships = player_garrison[player]

    enemy_prods = {
        pid: pr for pid, pr in player_prod.items()
        if pid not in (-1, player) and pr > 0
    }

    leader_id   = max(enemy_prods, key=enemy_prods.get) if enemy_prods else None
    leader_prod = enemy_prods.get(leader_id, 0.0)

    eco_gap    = max(0.0, leader_prod - my_prod)
    aggression = 1.0 + min(2.0, eco_gap / (my_prod + 1.0))

    return my_prod, my_ships, leader_id, leader_prod, aggression, player_prod, player_garrison


# ==============================================================================
# SECTION 7-C  ─  Crossover Turn T* & Optimal Ship Count
# ==============================================================================

def crossover_turn(src_prod, src_garrison, tgt_prod):
    """
    T*(i→j) = δ · prod_j · G_i / (γ · prod_i)

    Below T*: marginal fortification gain > opportunity cost → send MORE ships.
    At/above T*: opportunity cost dominates → send exactly S_min.

    Parameters
    ----------
    src_prod     : production of source planet (prod_i)
    src_garrison : garrison of source planet   (G_i)
    tgt_prod     : production of target planet (prod_j)

    Returns
    -------
    T_star : float  (in turns)
    """
    denom = W_OPP * max(0.01, src_prod)
    return (W_FORT * tgt_prod * src_garrison) / denom


def optimal_ship_count(src, tgt, T_arrive, S_min, avail):
    """
    Decide how many ships to send given the T* crossover rule.

    If T_arrive < T*: send extra ships (fortification is worthwhile).
        Extra ships scale as min(avail, round(S_min · sqrt(T* / T_arrive))).
        Square-root scaling captures diminishing returns of extra garrison.
    Else:
        Send exactly S_min (opportunity cost dominates).

    Returns
    -------
    S_optimal : int ∈ [S_min, avail]
    """
    T_star = crossover_turn(
        src_prod     = max(0.1, src.production),
        src_garrison = max(1,   src.ships),
        tgt_prod     = max(0.1, tgt.production),
    )

    if T_arrive < T_star:
        # Worthwhile to fortify; scale extra ships with sqrt of "how far inside T*"
        fortify_factor = math.sqrt(T_star / max(1.0, T_arrive))
        S_target = int(round(S_min * fortify_factor))
        return max(S_min, min(avail, S_target))
    else:
        return S_min  # Opportunity cost dominates; send minimum


# ==============================================================================
# SECTION 7-D  ─  Per-Plan Score Function
# ==============================================================================

def compute_plan_score(src, tgt, plan, player, k_state, timeline, T_h,
                       leader_id, aggression):
    """
    Compute (roi_score, J_absolute) for a single valid plan.

    roi_score = J / S   (value per ship, used for candidate ranking)
    J         = raw absolute Lagrangian value (used for net-value gate)

    Full formula:
    ─────────────────────────────────────────────────────────────────────────
    J  =  (α+β)·prod_j·max(0, T_h−T)            [C_prod:   production PV]
        − β·S_min                                 [C_cost:   ship cost]
        + ε·prod_j·max(0, T_h−T)·I(enemy)        [C_disrupt: double swing]
        + δ·max(0, S−S_min)·prod_j               [C_fort:   garrison bonus]
        − γ·S·T·(prod_i / G_i)                   [C_opp:    transit cost]
        + ζ·prod_j·T_h·I(my planet falling)       [C_def:    defence premium]
    ─────────────────────────────────────────────────────────────────────────
    """
    T     = plan["T"]
    S     = plan["ships"]

    prod_j    = tgt.production
    prod_i    = max(0.1, src.production)
    G_i       = max(1.0, float(src.ships))
    
    if tgt.id in k_state.comet_ids:
        lifespan = 9999
        for group in k_state.comets_data:
            pids = group.get('planet_ids', []) if isinstance(group, dict) else getattr(group, 'planet_ids', [])
            if tgt.id in pids:
                idx = pids.index(tgt.id)
                paths = group.get('paths', []) if isinstance(group, dict) else getattr(group, 'paths', [])
                path_index = group.get('path_index', 0) if isinstance(group, dict) else getattr(group, 'path_index', 0)
                if idx < len(paths):
                    lifespan = max(0, len(paths[idx]) - path_index)
                break
        remaining = max(0, min(T_h - T, lifespan - T))
    else:
        remaining = max(0, T_h - T)

    t_owner  = tgt.owner
    is_enemy = t_owner not in (-1, player)
    is_mine  = t_owner == player

    S_min = max(0, timeline.get_cost_to_capture(tgt.id, T, player))
    surplus = max(0, S - S_min)

    # ── Component 1: Time-Discounted Production PV ───────────────────────────
    # (α + β) because production materialises as both rate and garrison ships
    C_prod = (W_PROD + W_SHIPS) * prod_j * remaining

    # ── Component 2: Minimum Ship Cost ───────────────────────────────────────
    C_cost = -W_SHIPS * S_min

    # ── Component 3: Economic Disruption (enemy targets only) ────────────────
    # Attacking enemy = we gain production AND deny it to them (double swing)
    C_disrupt = 0.0
    if is_enemy:
        C_disrupt = W_DISRUPT * prod_j * remaining * aggression
        if t_owner == leader_id:
            C_disrupt *= 1.5   # Extra weight on leader disruption

    # ── Component 4: Fortification Bonus ────────────────────────────────────
    # Surplus ships left on the captured planet act as garrison → more production
    C_fort = W_FORT * surplus * prod_j

    # ── Component 5: Opportunity Cost of Transit ─────────────────────────────
    # Every ship is "worth" (prod_i / G_i) production-efficiency per turn.
    # Sending S ships for T turns costs S · T · prod_efficiency.
    prod_efficiency = prod_i / G_i
    C_opp = -W_OPP * S * T * prod_efficiency

    # ── Component 6: Emergency Defence Premium ───────────────────────────────
    # If this is our own planet that the timeline shows falling to an enemy,
    # multiply by ζ to ensure defence beats any attack-value plan.
    C_def = 0.0
    if is_mine:
        proj_owner, _ = timeline.timelines[tgt.id].get(T, (tgt.owner, 0))
        if proj_owner != player:
            C_def = W_DEFENSE * prod_j * T_h

    J         = C_prod + C_cost + C_disrupt + C_fort + C_opp + C_def
    roi_score = J / max(1.0, float(S))

    return roi_score, J


# ==============================================================================
# SECTION 7-E  ─  Threat Proximity Map (for defence triage)
# ==============================================================================

def _build_threat_map(k_state, player):
    """
    Aggregate incoming enemy fleet mass per my planet using spatial proximity.
    Closest my-planet to each enemy fleet receives its ship mass.

    Returns dict: my_planet_id → estimated incoming threat (ships)
    """
    threat = defaultdict(float)
    my_planet_positions = {
        pid: (p.x, p.y)
        for pid, p in k_state.planets.items()
        if p.owner == player
    }

    for f in getattr(k_state, 'fleets', {}).values() if hasattr(k_state, 'fleets') else []:
        f_owner = getattr(f, 'owner', -1)
        if f_owner in (-1, player):
            continue
        fx, fy = float(getattr(f, 'x', 50)), float(getattr(f, 'y', 50))
        best_d, best_pid = float('inf'), None
        for pid, (px, py) in my_planet_positions.items():
            d = math.hypot(px - fx, py - fy)
            if d < best_d:
                best_d, best_pid = d, pid
        if best_pid is not None:
            threat[best_pid] += float(getattr(f, 'ships', 0))

    return threat


# ==============================================================================
# SECTION 7-F  ─  Logistic Frontline Score
# ==============================================================================

def _frontline_score(planet, all_planets, player, sigma=20.0):
    """
    Gaussian military influence field at planet's position.
    Returns exposure = enemy_influence / (my_influence + ε).
    High exposure → frontline planet (should receive ships, not send them).
    """
    px, py = planet.x, planet.y
    sigma2 = 2.0 * sigma ** 2
    my_inf = en_inf = 0.0

    for p in all_planets:
        if p.owner == -1:
            continue
        d2  = (p.x - px) ** 2 + (p.y - py) ** 2
        w   = math.exp(-d2 / sigma2)
        mil = p.ships + p.production * 6

        if p.owner == player:
            my_inf += mil * w
        else:
            en_inf += mil * w

    return en_inf / (my_inf + 1e-9)


# ==============================================================================
# SECTION 7-G  ─  Main Strategy Function
# ==============================================================================

def generate_strategy_moves(player, k_state, timeline, obs_fleets=None):
    """
    Lagrangian-Relaxation Strategy Layer.

    Solves (approximately) the ship-budget constrained integer programme via:
      1. Global state snapshot (economy, leader detection, aggression index)
      2. Per-plan score computation using the analytical J formula
      3. Optimal ship-count selection via T* crossover rule
      4. Greedy priority-ordered assignment with adaptive shadow prices (λ_i)

    Candidate types and their relative priority:
      DEFENCE   (×5.0 boost)  : reinforce my planets projected to fall
      ATTACK    (×1.0)        : capture enemy / neutral planets
      LOGISTICS (×0.35)       : backline surplus → frontline accumulation

    Parameters
    ----------
    player     : int
    k_state    : KinematicsState
    timeline   : TimelineSimulator
    obs_fleets : raw fleet list from obs (optional; used for extra threat data)

    Returns
    -------
    moves : list of [from_planet_id: int, angle: float, ships: int]
    """

    # ── Setup ──────────────────────────────────────────────────────────────────
    my_planets  = {pid: p for pid, p in k_state.planets.items() if p.owner == player}
    all_planets = list(k_state.planets.values())

    if not my_planets:
        return []

    committed   = defaultdict(int)   # ships committed per source planet
    T_h         = timeline.SIM_HORIZON

    # ── Phase 0: Global snapshot ───────────────────────────────────────────────
    (my_prod, my_ships,
     leader_id, leader_prod,
     aggression,
     player_prod, player_garrison) = _global_snapshot(k_state, player)

    # ── Phase 1: Threat triage ─────────────────────────────────────────────────
    threat_map = _build_threat_map(k_state, player)

    # Frontline classification: exposure ratio per my planet
    exposure = {
        pid: _frontline_score(p, all_planets, player)
        for pid, p in my_planets.items()
    }

    # ── Phase 2: Generate & score all candidate plans ──────────────────────────
    #
    # Lagrangian shadow prices λ_i per source planet.
    # Interpretation: λ_i is the current "scarcity premium" of 1 ship at planet i.
    # A plan is worth executing only if  J(plan) − λ_i · S > 0.
    #
    # Initial value: λ_i = 0  (no scarcity yet; any positive-J plan is acceptable).
    # Update rule after committing k ships:
    #   λ_i  ←  (ships_committed / ships_remaining) · γ
    # This captures the non-linear rise in scarcity as budget depletes.
    #
    lambda_price = {pid: 0.0 for pid in my_planets}

    all_candidates = []   # (roi, J, src, tgt, plan, kind)

    for src_id, src in my_planets.items():
        budget = max(0, int(src.ships) - 1)
        if budget < 1:
            continue

        src_exposure = exposure.get(src_id, 0.0)

        for tgt in all_planets:
            if tgt.id == src_id:
                continue

            avail = budget - committed[src_id]
            if avail < 1:
                continue

            t_owner  = tgt.owner
            is_mine  = (t_owner == player)
            is_enemy = (t_owner not in (-1, player))

            # ── Classify plan kind ────────────────────────────────────────────
            if is_mine:
                # Defence or logistics
                tgt_exposure = exposure.get(tgt.id, 0.0)
                tgt_threat   = threat_map.get(tgt.id, 0.0)

                # Defence: planet has incoming threat AND is more exposed than src
                if tgt_threat >= 5.0 and tgt_exposure >= src_exposure * 0.8:
                    kind = 'defense'
                # Logistics: backline → frontline (no threat necessary)
                elif (not exposure.get(src_id, False)    # src is backline (low exposure)
                      and src_exposure < 0.5
                      and tgt_exposure > src_exposure * 1.1
                      and avail >= LOGISTICS_MIN_SURPLUS):
                    kind = 'logistics'
                else:
                    continue   # No strategic reason to send ships here
            else:
                kind = 'attack'

            # ── Query predictive engine ───────────────────────────────────────
            plans = find_valid_plan(src, tgt, timeline, avail, player, k_state)
            if not plans:
                continue

            for plan in plans:
                S_plan = plan["ships"]
                T_plan = plan["T"]

                if S_plan > avail:
                    continue

                # ── Compute optimal ship count via T* crossover ───────────────
                if kind == 'attack':
                    S_opt = optimal_ship_count(src, tgt, T_plan, S_plan, avail)
                    # Cap at available; re-check plan validity is guaranteed by
                    # the engine (S_plan ≤ S_opt, so fortification does not
                    # violate the capture requirement)
                    if S_opt > avail:
                        S_opt = avail
                    adjusted_plan = {"T": T_plan, "ships": S_opt,
                                     "angle": plan["angle"]}
                else:
                    # Defence / logistics: send exactly what the engine recommends
                    S_opt = S_plan
                    adjusted_plan = plan

                # ── Score the plan ────────────────────────────────────────────
                roi, J = compute_plan_score(
                    src, tgt, adjusted_plan,
                    player, k_state, timeline, T_h,
                    leader_id, aggression)

                # Logistics discount
                if kind == 'logistics':
                    roi *= W_LOGISTICS_DISC
                    J   *= W_LOGISTICS_DISC

                all_candidates.append((roi, J, src, tgt, adjusted_plan, kind))

    # ── Phase 3: Lagrangian greedy assignment ──────────────────────────────────
    #
    # Sort by ROI (value per ship) descending.
    # For each candidate:
    #   (a) Check ship budget of source.
    #   (b) Net-value gate: J − λ_i · S > 0   (worth the shadow cost).
    #   (c) Deduplication: one fleet per target (defence can stack if needed).
    #   (d) Commit; update λ_i.
    #
    all_candidates.sort(key=lambda c: -c[0])

    moves      = []
    targeted   = set()   # targets already receiving an attack fleet
    defended   = set()   # targets already receiving a defence fleet
    logistics  = set()   # targets already receiving a logistics transfer

    for roi, J, src, tgt, plan, kind in all_candidates:
        S      = plan["ships"]
        src_id = src.id

        # ── Budget check ──────────────────────────────────────────────────────
        avail = int(my_planets[src_id].ships) - 1 - committed[src_id]
        if S > avail:
            continue

        # ── Deduplication ─────────────────────────────────────────────────────
        if kind == 'attack'   and tgt.id in targeted:   continue
        if kind == 'defense'  and tgt.id in defended:   continue
        if kind == 'logistics'and tgt.id in logistics:  continue

        # Cross-check: do not simultaneously attack AND defend the same target
        if kind == 'attack'  and tgt.id in defended:    continue
        if kind == 'defense' and tgt.id in targeted:    continue

        # ── Net-value Lagrangian gate ─────────────────────────────────────────
        # J − λ_i · S > 0  means the plan earns more than the opportunity cost
        # of the ships at their current scarcity price.
        net_value = J - lambda_price[src_id] * S
        if net_value <= 0:
            continue   # Not worth committing at current shadow price

        # ── Execute move ──────────────────────────────────────────────────────
        moves.append([int(src_id), float(plan["angle"]), int(S)])
        committed[src_id] += S

        # ── Update shadow price (scarcity premium) ────────────────────────────
        #
        # λ_i(k+1) = (committed_i / remaining_i) · γ
        #
        # As remaining → 0, λ → ∞ (scarce ships only go to top-priority plans).
        remaining = int(my_planets[src_id].ships) - 1 - committed[src_id]
        if remaining > 0:
            lambda_price[src_id] = (committed[src_id] / remaining) * W_OPP
        else:
            lambda_price[src_id] = float('inf')   # Budget exhausted

        # ── Register assignment ───────────────────────────────────────────────
        if   kind == 'attack':    targeted.add(tgt.id)
        elif kind == 'defense':   defended.add(tgt.id)
        elif kind == 'logistics': logistics.add(tgt.id)

    return moves


# ==============================================================================
# SECTION 7-H  ─  Modified Agent Entry Point
# ==============================================================================
#
# Drop-in replacement for the existing `agent()` function.
# Only the strategy section (previously the greedy loop) is replaced;
# all kinematics, ray-tracing, and timeline simulation code is UNCHANGED.
#
# How to integrate:
#   1. Paste sections 7-A through 7-H after section 6 in your file.
#   2. Replace the body of agent() from "moves = []" onward with the call below.
#
# ==============================================================================

def agent(obs, config=None) -> list:
    """
    Orbit Wars agent with mathematical strategy layer.
    Sections 1-6 (kinematics + simulation) are identical to the original.
    Section 7 (strategy) uses Lagrangian optimisation.
    """
    # ── Parse ──────────────────────────────────────────────────────────────────
    _d      = isinstance(obs, dict)
    player  = obs.get("player", 0)      if _d else getattr(obs, "player", 0)
    obs_fl  = obs.get("fleets", [])     if _d else getattr(obs, "fleets", [])

    # ── Kinematics & simulation (UNCHANGED from original sections 3-5) ─────────
    k_state     = KinematicsState(obs)
    fleet_dests = predict_fleet_destinations(obs_fl, k_state)
    timeline    = TimelineSimulator(k_state, fleet_dests)

    # ── Mathematical strategy layer (Section 7) ────────────────────────────────
    return generate_strategy_moves(player, k_state, timeline, obs_fleets=obs_fl)