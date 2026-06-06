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
# 6. ADVANCED STRATEGY (Claude 3.5 Sonnet)
# ==============================================================================
def generate_strategy_moves(obs, player, my_sources, all_targets, timeline, k_state):
    """
    Parameters
    ----------
    obs        : raw game observation (provides current turn / step)
    player     : our player ID (int)
    my_sources : list of Planet objects we own (launch sites)
    all_targets: list of Planet objects we may target (enemy + neutral; may also
                 include our own planets for defense / logistics)
    timeline   : predictive engine timeline object (passed directly to planner)
    k_state    : full knowledge-state object; expected attributes:
                     .planets  → list of all Planet objects on the board
                     .fleets   → list of all Fleet  objects currently in flight

    Returns
    -------
    list of [from_planet_id: int, angle: float, ships: int]
    """

    moves           = []
    committed_ships = {src.id: 0 for src in my_sources}

    # ── Robust attribute accessors ────────────────────────────────────────────
    def geta(obj, *names, default=0.0):
        """Return first existing attribute; fall back to default."""
        for n in names:
            v = getattr(obj, n, None)
            if v is not None:
                return v
        return default

    def get_prod(p): return float(geta(p, 'production', 'prod', default=0.0))
    def get_ships(p): return float(geta(p, 'ships',      default=0.0))
    def get_owner(p): return int  (geta(p, 'owner',      default=-1))
    def get_x(p):    return float(geta(p, 'x',           default=50.0))
    def get_y(p):    return float(geta(p, 'y',           default=50.0))

    def avail(src):
        """Ships free to send from src planet (always keep ≥ 1 for ownership)."""
        return max(0, int(get_ships(src)) - committed_ships[src.id] - 1)

    # ══════════════════════════════════════════════════════════════════════════
    #  PHASE 0-A ─ Economic & Military Snapshot
    # ══════════════════════════════════════════════════════════════════════════

    all_planets  = geta(k_state, 'planets', default=[])
    all_fleets   = geta(k_state, 'fleets',  default=[])

    # Current turn and remaining game horizon
    current_turn = int(geta(obs, 'step', 'turn', 'current_turn', default=0))
    GAME_LENGTH  = 400                               # adjust if env exposes it
    turns_left   = max(1, GAME_LENGTH - current_turn)

    # Per-player economic and military totals
    economy  = defaultdict(float)   # pid → production / turn
    garrison = defaultdict(float)   # pid → ships sitting on planets
    flying   = defaultdict(float)   # pid → ships currently in transit

    for p in all_planets:
        pid = get_owner(p)
        economy [pid] += get_prod(p)
        garrison[pid] += get_ships(p)

    for f in all_fleets:
        flying[get_owner(f)] += float(geta(f, 'ships', default=0.0))

    total_str = {pid: garrison[pid] + flying[pid] for pid in economy}

    my_prod = economy [player]
    my_str  = total_str.get(player, 1.0)

    # ── Leader / Snowball Detection ───────────────────────────────────────────
    #
    # We compute each opponent's share of total active economic output and flag
    # a "snowball" condition when any single player holds > SNOWBALL_THRESHOLD
    # of all production.  The anti-leader urgency index (0–4) scales our
    # disruption bonus continuously rather than as a binary switch.

    opp_eco = {
        pid: eco
        for pid, eco in economy.items()
        if pid not in (-1, player) and eco > 0
    }

    if opp_eco:
        leader_id  = max(opp_eco, key=opp_eco.get)
        leader_eco = opp_eco[leader_id]
    else:
        leader_id  = None
        leader_eco = 0.0

    all_active_eco    = sum(e for pid, e in economy.items() if pid != -1) + 1e-9
    leader_glob_share = leader_eco / all_active_eco

    SNOWBALL_THRESHOLD = 0.35
    snowball_active    = leader_id is not None and leader_glob_share > SNOWBALL_THRESHOLD
    i_am_leader        = (leader_id is None) or (my_prod >= leader_eco)

    eco_gap              = max(0.0, leader_eco - my_prod)
    anti_leader_urgency  = min(4.0, eco_gap / (my_prod + 1e-9)) if leader_id else 0.0

    # Opportunity-cost rate: how much production each committed ship foregoes
    # per turn while in transit (= my_production / my_total_ships).
    opp_cost_rate = my_prod / (my_str + 1e-9)

    # ══════════════════════════════════════════════════════════════════════════
    #  PHASE 0-B ─ Gaussian Influence Map & Frontline Classification
    # ══════════════════════════════════════════════════════════════════════════
    #
    # We model military presence as a Gaussian field:
    #   Influence(px, py)  =  Σ_planets  weight_p × exp(–d²/2σ²)
    # where
    #   weight_p  =  ships_on_p + production_p × 8    (8-turn accumulation proxy)
    #   σ         =  22 units   (≈ ⅕ of the board width)
    #
    # A planet where enemy_influence > 0.5 × my_influence is classified as a
    # FRONTLINE planet; the rest are BACKLINE.  Exposure = enemy/my ratio.

    SIGMA     = 22.0
    SIGMA2    = 2.0 * SIGMA ** 2

    def gaussian_influence_at(px, py):
        """Return (my_influence, enemy_influence) at (px, py)."""
        mi = ei = 0.0
        for p in all_planets:
            pid = get_owner(p)
            if pid == -1:
                continue
            d2  = (get_x(p) - px) ** 2 + (get_y(p) - py) ** 2
            w   = math.exp(-d2 / SIGMA2)
            mil = get_ships(p) + get_prod(p) * 8
            if pid == player:
                mi += mil * w
            else:
                ei += mil * w
        return mi, ei

    # Classify every planet we own (both sources and any other owned planet)
    planet_class = {}   # planet_id → {'exposure', 'is_frontline', 'mi', 'ei'}

    all_my_planets = [p for p in all_planets if get_owner(p) == player]
    # Also include sources in case they're not in all_planets
    classify_pool  = {p.id: p for p in all_my_planets}
    for src in my_sources:
        classify_pool.setdefault(src.id, src)

    for pid_key, p in classify_pool.items():
        mi, ei   = gaussian_influence_at(get_x(p), get_y(p))
        exposure = ei / (mi + 1e-9)
        planet_class[pid_key] = {
            'exposure':    exposure,
            'is_frontline': exposure > 0.5,
            'mi':          mi,
            'ei':          ei,
        }

    # Enemy production centroid — our strategic "target" in positional scoring
    ecx = ecy = ew = 0.0
    for p in all_planets:
        if get_owner(p) not in (-1, player):
            w   = max(get_prod(p), 0.1)
            ecx += get_x(p) * w
            ecy += get_y(p) * w
            ew  += w
    if ew > 0:
        ecx /= ew
        ecy /= ew
    else:
        ecx = ecy = 50.0   # Board centre if no enemies

    # ══════════════════════════════════════════════════════════════════════════
    #  PHASE 1 ─ Incoming Threat Triage
    # ══════════════════════════════════════════════════════════════════════════
    #
    # We aggregate enemy fleet mass by associating each enemy fleet with the
    # nearest of our own planets.  This is a conservative proxy (NOT kinematics)
    # used only to trigger the defence scoring pass.  The predictive engine
    # (find_valid_plan) performs the exact threat simulation.

    planet_threat = defaultdict(float)   # my planet_id → aggregated threat mass

    my_src_map = {src.id: src for src in my_sources}
    my_src_list = list(my_sources)

    for f in all_fleets:
        f_owner = int(geta(f, 'owner', default=-1))
        if f_owner in (-1, player):
            continue
        fx = float(geta(f, 'x', default=50.0))
        fy = float(geta(f, 'y', default=50.0))
        best_d, best_id = float('inf'), None
        for src in my_src_list:
            d = math.hypot(get_x(src) - fx, get_y(src) - fy)
            if d < best_d:
                best_d, best_id = d, src.id
        if best_id is not None:
            planet_threat[best_id] += float(geta(f, 'ships', default=0.0))

    # ══════════════════════════════════════════════════════════════════════════
    #  PHASE 2 ─ Candidate Generation & Scoring
    # ══════════════════════════════════════════════════════════════════════════

    all_candidates = []   # (score, src_id, src, tgt, plan, kind)

    # ── 2A · DEFENSE ─────────────────────────────────────────────────────────
    #
    # For every planet whose estimated threat mass exceeds its current garrison,
    # we ask find_valid_plan for a reinforcement plan from every other source.
    # Defence score is proportional to threat urgency × planet production value.
    # A 5× global multiplier ensures defence always beats equal-value attacks.

    THREAT_THRESHOLD = 5.0   # minimum enemy ships before we generate plans

    for src in my_sources:
        av = avail(src)
        if av < 2:
            continue
        for tgt in my_sources:                          # my planets as tgt
            if tgt.id == src.id:
                continue
            threat = planet_threat.get(tgt.id, 0.0)
            if threat < THREAT_THRESHOLD:
                continue

            plans = find_valid_plan(src, tgt, timeline, av, player, k_state)
            for plan in plans:
                if plan["ships"] > av:
                    continue
                garrison_now = get_ships(tgt)
                urgency      = threat / (garrison_now + 1.0)
                tgt_prod     = get_prod(tgt)

                # Urgency-weighted production value; double if critically low
                def_score = urgency * (tgt_prod * 80 + 40)
                if garrison_now < threat * 0.5:
                    def_score *= 2.0           # Planet almost certainly falls; act now

                # 5× defence priority multiplier applied at merge time
                all_candidates.append(
                    (def_score * 5.0, src.id, src, tgt, plan, 'defense'))

    # ── Risk sub-functions for attacks ────────────────────────────────────────

    def risk_counter_attack(tgt, transit_turns):
        """
        Estimate how likely the enemy retakes `tgt` after we capture it.
        We weight nearby enemy military (ships + production × transit_turns) with
        a Gaussian falloff; more concentrated nearby enemy → higher risk.
        Score ∈ [1, 4].
        """
        t_owner = get_owner(tgt)
        if t_owner == -1:
            return 1.0       # Neutrals: no organised counter
        tx, ty = get_x(tgt), get_y(tgt)
        nearby_threat = 0.0
        for p in all_planets:
            if get_owner(p) == t_owner:
                d   = math.hypot(get_x(p) - tx, get_y(p) - ty)
                mil = (get_ships(p) +
                       get_prod(p) * min(transit_turns, 30))
                nearby_threat += mil * math.exp(-d / 30.0)
        return 1.0 + min(3.0, nearby_threat / 150.0)

    def risk_source_exposure(src, ships_to_send):
        """
        Risk that sending ships_to_send leaves the source dangerously exposed.
        Based on aggregated threat already pointing at it vs remaining garrison.
        Score ∈ [1, 5].
        """
        remaining = get_ships(src) - committed_ships[src.id] - ships_to_send
        if remaining < 1:
            return 5.0
        threat    = planet_threat.get(src.id, 0.0)
        ratio     = threat / (remaining + 1e-9)
        return 1.0 + min(4.0, ratio * 0.6)

    # ── 2B · ATTACK / CAPTURE ─────────────────────────────────────────────────
    #
    # For every (source, target) pair the Risk-Adjusted ROI is:
    #
    #   Gain  = W_prod × PV(production)
    #         + W_dis  × PV(disruption)        ← only for enemy targets
    #         + W_pos  × positional_premium
    #
    #   Cost  = ships_sent
    #         + ships_sent × transit_turns × opp_cost_rate × 0.05
    #
    #   Risk  = risk_counter_attack × risk_source_exposure
    #
    #   Mult  = anti_snowball_multiplier        ← 1x … 5x, leader-targeted
    #
    #   ROI   = (Gain × Mult) / (Cost × Risk)
    #
    # Key properties:
    #  • PV(production) = production × (turns_left − arrival_turn)
    #    — punishes late captures that leave little time to recoup ships
    #  • PV(disruption) = PV(production) × disruption_factor
    #    — attacking an enemy is a double swing: we gain AND they lose
    #  • positional_premium = 30 × exp(−dist_to_enemy_core / 35)
    #    — planets inside the enemy heartland are worth more (threaten them)
    #  • opportunity_cost = ships × transit_turns × (my_prod / my_str) × 0.05
    #    — ships locked in transit can't compound locally

    W_PROD   = 1.0
    W_DISRUPT= 1.4
    W_POS    = 0.25

    for src in my_sources:
        av = avail(src)
        if av < 2:
            continue

        for tgt in all_targets:
            t_owner = get_owner(tgt)
            if t_owner == player:
                continue   # own planets handled in defence / logistics

            # Prevent 1-1 spam
            end_owner, _ = timeline.timelines[tgt.id].get(timeline.SIM_HORIZON, (t_owner, 0))
            if end_owner == player:
                continue

            plans = find_valid_plan(src, tgt, timeline, av, player, k_state)
            if not plans:
                continue

            for plan in plans:
                ships_req = plan["ships"]
                T_arrive  = plan["T"]
                if ships_req > av:
                    continue

                t_prod     = get_prod(tgt)
                is_enemy   = t_owner not in (-1, player)
                is_leader  = (t_owner == leader_id)
                transit    = max(1, T_arrive - current_turn)

                # ── Value decomposition ──────────────────────────────────────
                # 1. Time-discounted production (present value of captured output)
                active_turns = max(0, turns_left - T_arrive)
                pv_prod      = W_PROD * t_prod * active_turns

                # 2. Economic disruption (enemy: swing = gain PLUS deny)
                if is_enemy:
                    dis_factor = 1.0
                    if is_leader:
                        # Leader disruption: stronger bonus the further ahead they are
                        dis_factor = 1.5 + anti_leader_urgency * 0.35
                    pv_disrupt = W_DISRUPT * t_prod * active_turns * dis_factor
                else:
                    pv_disrupt = 0.0

                # 3. Positional premium (deep in enemy territory = more threatening)
                d_core   = math.hypot(get_x(tgt) - ecx, get_y(tgt) - ecy)
                pv_pos   = W_POS * 30.0 * math.exp(-d_core / 35.0)

                total_gain = pv_prod + pv_disrupt + pv_pos
                if total_gain < 1.0:
                    continue

                # ── Anti-snowball urgency multiplier ─────────────────────────
                # Scales smoothly with urgency index; max 5× when snowballing
                if is_leader:
                    anti_snow = 1.0 + anti_leader_urgency * (
                        1.0 if snowball_active else 0.3)
                    anti_snow = min(5.0, anti_snow)
                else:
                    anti_snow = 1.0

                # ── Cost model ────────────────────────────────────────────────
                ship_cost   = float(ships_req)
                opp_cost    = ship_cost * transit * opp_cost_rate * 0.05
                total_cost  = ship_cost + opp_cost

                # ── Risk model ────────────────────────────────────────────────
                r_counter   = risk_counter_attack(tgt, transit)
                r_source    = risk_source_exposure(src, ships_req)
                total_risk  = r_counter * r_source

                # ── Final Risk-Adjusted ROI ───────────────────────────────────
                roi = (total_gain * anti_snow) / (total_cost * total_risk + 1.0)

                all_candidates.append(
                    (roi, src.id, src, tgt, plan, 'attack'))

    # ── 2C · LOGISTICS PIPELINE ───────────────────────────────────────────────
    #
    # Backline planets accumulate ships that sit idle.  We route surplus to the
    # most exposed frontline planet; this keeps our fighting weight concentrated
    # at the front without sacrificing coverage at the rear.
    #
    # A planet qualifies as a backline SOURCE if:
    #   • Its exposure ratio < 0.5  (not directly threatened)
    #   • It has ≥ 15 spare ships   (meaningful surplus to share)
    #
    # A planet qualifies as a frontline TARGET if:
    #   • It is ours and its exposure > 0.5
    #   • It is more exposed than the source  (genuinely forward)
    #
    # Logistics score is deliberately discounted (×0.30) so attack plans win
    # any tie-break; we only pipeline when there is nothing better to do.

    LOGISTICS_DISCOUNT = 0.30
    MIN_SURPLUS        = 15

    # Build a ranked list of frontline targets (most exposed first)
    frontline_targets = sorted(
        [
            (planet_class.get(p.id, {}).get('exposure', 0.0), p)
            for p in all_planets
            if get_owner(p) == player
            and planet_class.get(p.id, {}).get('is_frontline', False)
        ],
        key=lambda t: -t[0]
    )

    for src in my_sources:
        av         = avail(src)
        src_cls    = planet_class.get(src.id, {})
        src_exp    = src_cls.get('exposure', 0.0)

        # Only backline planets act as logistics hubs
        if src_cls.get('is_frontline', True):
            continue
        if av < MIN_SURPLUS:
            continue

        for fl_exp, fl_tgt in frontline_targets[:5]:      # top 5 frontline targets
            if fl_tgt.id == src.id:
                continue
            # Only funnel "forward" — target must be meaningfully more exposed
            if fl_exp < src_exp * 1.15:
                continue

            plans = find_valid_plan(src, fl_tgt, timeline, av, player, k_state)
            if not plans:
                continue

            for plan in plans:
                if plan["ships"] > av:
                    continue

                # Logistics score: front-line exposure × production priority
                tgt_prod  = max(get_prod(fl_tgt), 0.1)
                log_score = (fl_exp * tgt_prod * 20.0) / (plan["ships"] + 1.0)
                log_score *= LOGISTICS_DISCOUNT

                all_candidates.append(
                    (log_score, src.id, src, fl_tgt, plan, 'logistics'))

    # ══════════════════════════════════════════════════════════════════════════
    #  PHASE 3 ─ Global Priority-Ordered Assignment
    # ══════════════════════════════════════════════════════════════════════════
    #
    # All candidate moves are merged and sorted by score descending.
    # The 5× defence multiplier already promotes those to the top.
    # We commit plans greedily while three invariants hold:
    #   (a) per-source ship budget not exceeded
    #   (b) no two moves target the same planet (attack / logistics)
    #       — defence *can* stack if multiple threats exist on different planets
    #   (c) a planet is not both defended and attacked in the same turn

    all_candidates.sort(key=lambda c: -c[0])

    targeted_ids   = set()   # planets committed for attack / capture
    defended_ids   = set()   # planets covered by a defence plan
    logistics_ids  = set()   # planets receiving a logistics transfer

    for score, src_id, src, tgt, plan, kind in all_candidates:

        # ── Budget check ─────────────────────────────────────────────────────
        ships_req = plan["ships"]
        if ships_req > avail(src):
            continue

        tgt_id = tgt.id

        # ── Deduplication guards ─────────────────────────────────────────────
        if kind == 'attack'    and tgt_id in targeted_ids:
            continue
        if kind == 'defense'   and tgt_id in defended_ids:
            continue
        if kind == 'logistics' and tgt_id in logistics_ids:
            continue

        # Don't defend a planet we're simultaneously attacking
        # (logistics to our own planet is fine alongside attacks)
        if kind == 'defense'   and tgt_id in targeted_ids:
            continue
        if kind == 'attack'    and tgt_id in defended_ids:
            continue

        # ── Commit move ──────────────────────────────────────────────────────
        moves.append([int(src_id), float(plan["angle"]), int(ships_req)])
        committed_ships[src_id] += ships_req

        if   kind == 'attack':    targeted_ids.add(tgt_id)
        elif kind == 'defense':   defended_ids.add(tgt_id)
        elif kind == 'logistics': logistics_ids.add(tgt_id)

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
    
    # 3. Use Claude 3.5 Sonnet generated strategy
    moves = generate_strategy_moves(obs, player, my_sources, all_targets, timeline, k_state)

    return moves
