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
# 6. ADVANCED STRATEGY (Kimi)
# ==============================================================================
def generate_strategy_moves(obs, player, my_sources, all_targets, timeline, k_state):
    """
    Advanced Game-Theoretic Strategy Layer for Orbit Wars.
    
    Core Principles:
    1.  Expected Value & NPV: Future production is discounted hyperbolically by 
        arrival time. A planet captured on turn 10 is worth far less than one 
        captured on turn 2.
    2.  Economic Disruption: Denying an enemy a high-production planet is valued 
        at 2.2x-3.0x the raw production NPV (compound growth prevention).
    3.  Leader-Bashing / Snowball Prevention: The strongest opponent is identified 
        by projected endgame strength. Attacks on the leader receive a 35% score 
        bonus to force a Nash-equilibrium where no single player snowballs.
    4.  Influence Maps: Capturing planets that sit near multiple enemies creates 
        a "buffer zone" — we add a territorial control bonus for such targets.
    5.  Logistics & Speed Capital: Backline planets reinforce frontline staging 
        planets. This exploits the logarithmic fleet-speed formula: a frontline 
        planet with 200 ships launches a speed-6 fleet, while two 100-ship 
        fleets are slower and weaker in combat.
    6.  Risk-Adjusted ROI: We use a Sharpe-like ratio 
        (NPV - Cost) / (Cost + 1) so that we don't overpay for marginal captures.
    7.  Marginal Utility: We prevent overkill on neutrals. Once a target's 
        garrison is covered by an already-committed fleet, additional fleets 
        have sharply diminishing returns and are skipped.
    """
    moves = []
    committed_ships = {src.id: 0 for src in my_sources}

    # =====================================================================
    # 1. GLOBAL STATE ANALYSIS  (Macro-economics & Frontline Geometry)
    # =====================================================================
    current_step = getattr(obs, 'step', 0)
    total_steps  = getattr(obs, 'total_steps', 500)
    remaining    = max(1, total_steps - current_step)

    # --- Enemy Aggregate Metrics ---
    enemy_stats = defaultdict(lambda: {'ships': 0.0, 'production': 0.0, 'planets': 0})
    for t in all_targets:
        if t.owner not in (-1, player):
            enemy_stats[t.owner]['ships']      += t.ships
            enemy_stats[t.owner]['production'] += t.production
            enemy_stats[t.owner]['planets']    += 1

    # Identify the leader (strongest opponent by projected endgame strength)
    leader_id    = None
    leader_score = -1.0
    for eid, stats in enemy_stats.items():
        projected = stats['ships'] + stats['production'] * remaining * 1.5
        if projected > leader_score:
            leader_score = projected
            leader_id    = eid

    # --- Frontline vs Backline Classification ---
    # We use Manhattan distance purely as a strategic influence metric; 
    # no kinematics or collision code is written here.
    frontline_ids = set()
    for src in my_sources:
        min_dist = float('inf')
        for t in all_targets:
            if t.owner not in (-1, player):
                d = abs(src.x - t.x) + abs(src.y - t.y)
                if d < min_dist:
                    min_dist = d
        if min_dist < 40:          # Within strategic influence zone
            frontline_ids.add(src.id)

    # =====================================================================
    # 2. PLAN GENERATION & ADVANCED SCORING
    # =====================================================================
    plan_options = []

    def score_attack(plan, src, tgt):
        """Risk-Adjusted Expected Value for an attack/expansion plan."""
        T      = plan['T']
        ships  = plan['ships']
        discount = 0.88 ** T          # Hyperbolic time discount

        if tgt.owner == -1:
            # Neutral: pure expansion value
            future_prod    = tgt.production * max(0, remaining - T) * discount
            immediate_gain = tgt.ships * 0.25
            base_value     = future_prod + immediate_gain
            denial_value   = 0.0
        else:
            # Enemy: Capture + Economic Disruption
            future_prod = tgt.production * max(0, remaining - T) * discount
            
            # Denial multiplier: taking from enemy is worth more than neutral
            denial_mult = 2.2 if tgt.production >= 2 else 1.6
            denial_value = future_prod * denial_mult
            
            # Leader-bashing bonus (prevent opponent snowball)
            if tgt.owner == leader_id:
                denial_value *= 1.35
            
            # Influence Map bonus: planets near multiple enemies exert map control
            nearby_enemies = sum(
                1 for p in all_targets
                if p.owner not in (-1, player) and p.owner != tgt.owner
                and abs(p.x - tgt.x) + abs(p.y - tgt.y) < 30
            )
            influence_bonus = nearby_enemies * 4.0 * discount
            
            base_value = future_prod + denial_value + influence_bonus

        # Risk adjustment: slow attacks on enemy planets are riskier
        risk_penalty = 1.0
        if tgt.owner != -1 and T > 8:
            risk_penalty = max(0.6, 1.0 - (T - 8) * 0.04)

        total_value = base_value * risk_penalty

        # Opportunity cost: ships in transit don't produce at the source
        prod_loss  = src.production * T * 0.3 * discount
        total_cost = ships + prod_loss

        # Sharpe-like Risk-Adjusted ROI
        roi = (total_value - total_cost) / (total_cost + 1.0)

        # Composite score blends absolute value, efficiency, and speed
        return (total_value * 0.7) + (roi * 12.0) + (discount * 3.0)

    def score_reinforce(plan, src, front):
        """Logistics value: backline -> frontline staging."""
        T = plan['T']
        ships = plan['ships']
        discount = 0.92 ** T

        # Frontline staging creates "optionality": larger future fleets
        frontline_potential = front.production * min(remaining, 15) * 0.2
        staging_value       = front.ships * 0.15

        # Critical reinforcement if frontline is nearly empty
        urgency = 1.0
        if front.ships < 10:
            urgency = 2.0
        if front.ships < 5:
            urgency = 3.5

        total_value = (frontline_potential + staging_value) * discount * urgency
        total_cost  = ships * 0.7          # Reinforcement is low-risk
        return (total_value / (total_cost + 1.0)) * 6.0

    # --- Attack / Expansion Plans ---
    for src in my_sources:
        avail = src.ships - committed_ships[src.id]
        if avail < 3:
            continue

        for tgt in all_targets:
            if tgt.owner == player:
                continue

            # Prevent 1-1 spam
            end_owner, _ = timeline.timelines[tgt.id].get(timeline.SIM_HORIZON, (tgt.owner, 0))
            if end_owner == player:
                continue

            # Delegate kinematics entirely to the predictive engine
            plans = find_valid_plan(src, tgt, timeline, avail, player, k_state)
            if not plans:
                continue

            # Pareto-optimal selection: prefer faster arrival, then cheaper cost
            best = max(plans, key=lambda p: (-p['T'] * 2.0 - p['ships'] * 0.05))

            sc = score_attack(best, src, tgt)
            plan_options.append({
                'score':  sc,
                'src':    src,
                'tgt':    tgt,
                'plan':   best,
                'cat':    'attack',
                'ships':  best['ships'],
            })

    # --- Reinforcement Plans (Logistics / Accumulation) ---
    backline = [s for s in my_sources if s.id not in frontline_ids]
    for src in backline:
        avail = src.ships - committed_ships[src.id]
        if avail < 8:
            continue

        for front in my_sources:
            if front.id not in frontline_ids or front.id == src.id:
                continue

            plans = find_valid_plan(src, front, timeline, avail, player, k_state)
            if not plans:
                continue

            best = min(plans, key=lambda p: p['T'])   # Fastest reinforcement
            sc   = score_reinforce(best, src, front)
            plan_options.append({
                'score': sc,
                'src':   src,
                'tgt':   front,
                'plan':  best,
                'cat':   'reinforce',
                'ships': best['ships'],
            })

    # =====================================================================
    # 3. GLOBAL SELECTION  (Greedy with Marginal-Utility Constraints)
    # =====================================================================
    plan_options.sort(key=lambda x: x['score'], reverse=True)

    # Track how many ships we have already committed to each neutral target 
    # this turn to prevent overkill (diminishing marginal utility).
    target_committed_ships = defaultdict(float)

    for opt in plan_options:
        src       = opt['src']
        tgt       = opt['tgt']
        plan      = opt['plan']
        cat       = opt['cat']
        need_ships = opt['ships']

        # --- Source Constraint ---
        current_avail = src.ships - committed_ships[src.id]
        if need_ships > current_avail:
            continue

        # Don't strip a planet below 2 ships (defensive margin)
        if committed_ships[src.id] + need_ships > src.ships * 0.98:
            continue

        # --- Marginal Utility: Overkill Prevention on Neutrals ---
        if cat == 'attack' and tgt.owner == -1:
            already_committed = target_committed_ships[tgt.id]
            if already_committed >= tgt.ships + 2:
                continue        # Capture already guaranteed; extra fleets wasted
            target_committed_ships[tgt.id] += need_ships

        # --- Commit the Move ---
        moves.append([int(src.id), float(plan['angle']), int(plan['ships'])])
        committed_ships[src.id] += need_ships

        # If source is now depleted, skip its remaining options
        if src.ships - committed_ships[src.id] < 3:
            continue

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
    
    # 3. Use Kimi generated strategy
    moves = generate_strategy_moves(obs, player, my_sources, all_targets, timeline, k_state)

    return moves
