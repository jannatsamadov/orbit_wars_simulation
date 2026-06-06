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
    dist = get_distance(src_planet.x, src_planet.y, target_planet.x, target_planet.y)
    est_turns = max(1.0, dist / speed)
    
    for _ in range(max_iters):
        predicted_pos = k_state.predict_target_position(target_planet.id, est_turns)
        if not predicted_pos: return None
        px, py = predicted_pos
        dist = get_distance(src_planet.x, src_planet.y, px, py)
        est_turns = max(1.0, dist / speed)
        
    final_turns = int(math.ceil(est_turns))
    final_pos = k_state.predict_target_position(target_planet.id, final_turns)
    if not final_pos: return None
    fx, fy = final_pos
    
    if is_path_blocked_by_sun(src_planet.x, src_planet.y, fx, fy, target_planet.radius):
        return None
        
    angle = math.atan2(fy - src_planet.y, fx - src_planet.x)
    return angle, final_turns

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
# 6. ADVANCED STRATEGY (Qwen)
# ==============================================================================
def generate_strategy_moves(obs, player, my_sources, all_targets, timeline, k_state):
    moves = []
    committed_ships = {src.id: 0 for src in my_sources}
    
    # 1. Calculate global board state (Influence Map & Frontline Detection)
    enemy_planets = [p for p in all_targets if p.owner != -1 and p.owner != player]
    my_planets = [p for p in all_targets if p.owner == player]
    
    # Dynamically determine Frontline vs Backline based on median distance to enemies
    is_frontline = {}
    frontline_threshold = 50.0
    if enemy_planets and my_planets:
        dists = []
        for p in my_planets:
            min_d = min(math.hypot(p.x - ep.x, p.y - ep.y) for ep in enemy_planets)
            dists.append(min_d)
        dists.sort()
        frontline_threshold = dists[len(dists)//2] if dists else 50.0
        
    for p in my_planets:
        if enemy_planets:
            min_d = min(math.hypot(p.x - ep.x, p.y - ep.y) for ep in enemy_planets)
            is_frontline[p.id] = min_d <= frontline_threshold
        else:
            is_frontline[p.id] = False
            
    def get_reserve(src, is_fl):
        """Calculate risk-adjusted ship reserve for frontline defense."""
        if not is_fl:
            return 0.0
        threat = 0.0
        for ep in enemy_planets:
            d = math.hypot(src.x - ep.x, src.y - ep.y)
            if d < 45.0:
                threat += ep.production * 3.0
        return threat + src.production * 2.0

    def calculate_score(src, tgt, plan, is_fl_src, is_fl_tgt):
        """Advanced Evaluation: Expected Value, ROI, and Economic Disruption."""
        T = plan["T"]
        ships = plan["ships"]
        
        # Time discount factor (prefer faster captures/impacts)
        time_discount = 0.96 ** T
        
        if tgt.owner == player:
            # Logistics/Accumulation: Backline -> Frontline transfer
            if not is_fl_src and is_fl_tgt:
                return (ships * 0.95) * time_discount
            return -1.0
            
        elif tgt.owner == -1:
            # Neutral planet ROI
            remaining_turns = max(10, 60 - T)
            value = tgt.production * remaining_turns
            cost = ships * 1.5  # Ships are mostly lost in neutral combat
            return (value - cost) * time_discount
            
        else:
            # Enemy planet: Economic Disruption & Snowball Prevention
            enemy_owner_prod = sum(p.production for p in all_targets if p.owner == tgt.owner)
            snowball_factor = 1.0 + (enemy_owner_prod / 15.0)
            
            remaining_turns = max(10, 60 - T)
            # Denying enemy production + gaining it = ~2.5x multiplier
            value = tgt.production * 2.5 * remaining_turns * snowball_factor
            cost = ships * 1.2 
            
            # Frontline enemy planets pose immediate threats, prioritize their destruction
            if is_fl_tgt:
                value *= 1.2
                
            return (value - cost) * time_discount

    # 2. Iterate through sources and targets to get plans via Predictive Engine
    all_candidates = []
    for src in my_sources:
        is_fl_src = is_frontline.get(src.id, False)
        reserve = get_reserve(src, is_fl_src)
        avail_ships = max(0, int(src.ships - reserve))
        
        if avail_ships < 5:
            continue
            
        for tgt in all_targets:
            is_fl_tgt = is_frontline.get(tgt.id, False)
            
            # Prevent spamming 1 ship at a time
            end_owner, _ = timeline.timelines[tgt.id].get(timeline.SIM_HORIZON, (tgt.owner, 0))
            if tgt.owner != player and end_owner == player:
                continue
            
            # Query the pre-built kinematics/combat engine
            plans = find_valid_plan(src, tgt, timeline, avail_ships, player, k_state)
            if not plans:
                continue
                
            best_plan = None
            best_score = -float('inf')
            
            for plan in plans:
                score = calculate_score(src, tgt, plan, is_fl_src, is_fl_tgt)
                if score > best_score:
                    best_score = score
                    best_plan = plan
                    
            if best_plan and best_score > 0:
                all_candidates.append({
                    "src": src,
                    "tgt": tgt,
                    "plan": best_plan,
                    "score": best_score
                })

    # 3. Global Assignment (Greedy Knapsack-like allocation)
    all_candidates.sort(key=lambda x: x["score"], reverse=True)
    locked_targets = set()
    
    for cand in all_candidates:
        src = cand["src"]
        tgt = cand["tgt"]
        plan = cand["plan"]
        
        # Prevent overkill/overcommitment on the same target
        if tgt.id in locked_targets:
            continue
            
        current_avail = src.ships - committed_ships[src.id]
        if current_avail >= plan["ships"]:
            moves.append([int(src.id), float(plan["angle"]), int(plan["ships"])])
            committed_ships[src.id] += plan["ships"]
            locked_targets.add(tgt.id)
            
    return moves


# ==============================================================================
# 7. AGENT ENTRY POINT
# ==============================================================================
def agent(obs) -> list:
    player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
    obs_fleets = obs.get("fleets", []) if isinstance(obs, dict) else getattr(obs, "fleets", [])
    
    k_state = KinematicsState(obs)
    
    # 1. Ray Tracing
    fleet_dests = predict_fleet_destinations(obs_fleets, k_state)
    
    # 2. Timeline Simulator
    timeline = TimelineSimulator(k_state, fleet_dests)
    
    my_sources = [p for p in k_state.planets.values() if p.owner == player]
    all_targets = list(k_state.planets.values())
    
    # 3. Use Qwen generated strategy
    moves = generate_strategy_moves(obs, player, my_sources, all_targets, timeline, k_state)

    return moves
