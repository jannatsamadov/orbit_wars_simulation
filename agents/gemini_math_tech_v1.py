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
# ADVANCED STRATEGY LAYER: DISCRETE-TIME OPTIMAL CONTROL (MPC)
# ==============================================================================

# Optimizasiya hiperparametrləri
DELTA_U = 15           # Törəmə hesablamaq üçün test edilən gəmi addımı (Gradient step)
WEIGHT_SHIPS = 1.0    # J(U) funksiyasında mövcud gəmiyə verilən çəki
WEIGHT_PROD = 8.0     # J(U) funksiyasında gələcək istehsalata verilən çəki
LAMBDA_BASE = 1.05    # Baza Kölgə Qiyməti (1.0-dən böyük olmalıdır ki, boşuna gəmi hərəkət etdirməsin)

def _evaluate_state_J(owner, ships, prod, player):
    """
    Sistemin hər hansı bir anındakı tək planet üçün Məqsəd Funksiyası J(U).
    """
    if owner == player:
        return (ships * WEIGHT_SHIPS) + (prod * WEIGHT_PROD)
    elif owner != -1:
        # Düşmənin əlindədirsə, bu bizim üçün mənfi dəyərdir (onu azaltmaq bizə müsbət J verəcək)
        return -((ships * WEIGHT_SHIPS * 0.5) + (prod * WEIGHT_PROD * 0.5))
    return 0.0

def _simulate_marginal_J_change(tgt, timeline, arr_turn, delta_u, player):
    """
    Ədədi Törəmə (Numerical Gradient) Hesablayıcısı:
    Hədəfə 'arr_turn' anında əlavə 'delta_u' qədər gəmi göndərsək, 
    simulyasiyanın sonunda (H = SIM_HORIZON) J(U) necə dəyişəcək?
    Bütün simulyatoru kopyalamaq əvəzinə, yalnız lazımi planetin gələcəyini yenidən hesablayır.
    """
    H = timeline.SIM_HORIZON
    
    # 1. Baza vəziyyəti (Bizim əlavə gəmilər olmadan J nə qədərdir?)
    base_owner, base_ships = timeline.timelines[tgt.id].get(H, (tgt.owner, 0))
    J_base = _evaluate_state_J(base_owner, base_ships, tgt.production, player)
    
    # 2. Test vəziyyəti: arr_turn anında bizim delta_u gəmimiz döyüşə qoşulur
    # Simulyasiyanı arr_turn-dən H-a qədər yenidən irəli sarıyırıq
    curr_owner, curr_ships = timeline.timelines[tgt.id].get(arr_turn - 1, (tgt.owner, tgt.ships))
    prod = tgt.production
    
    for t in range(arr_turn, H + 1):
        if curr_owner != -1:
            curr_ships += prod
            
        # Orijinal gəlişləri (arrivals) götürürük
        arrs = timeline.arrivals[tgt.id].get(t, [])
        forces = defaultdict(float)
        
        if curr_owner != -1: forces[curr_owner] = curr_ships
        else: forces[-1] = curr_ships
            
        for a in arrs:
            forces[a["owner"]] += a["ships"]
            
        # Əgər arr_turn-dəyiksə, bizim sınaq gəmilərimizi (delta_u) matrisə əlavə edirik!
        if t == arr_turn:
            forces[player] += delta_u
            
        sorted_forces = sorted(forces.items(), key=lambda x: x[1], reverse=True)
        
        if len(sorted_forces) == 1:
            curr_owner, curr_ships = sorted_forces[0]
        else:
            top1_o, top1_s = sorted_forces[0]
            top2_o, top2_s = sorted_forces[1]
            curr_ships = top1_s - top2_s
            if curr_ships == 0:
                curr_owner = -1
            else:
                curr_owner = top1_o

    J_new = _evaluate_state_J(curr_owner, curr_ships, tgt.production, player)
    
    # Delta J-ni qaytarırıq
    return J_new - J_base

def generate_strategy_moves(obs, player, my_sources, all_targets, timeline, k_state):
    """
    Riyazi Optimizasiya (Gradient Ascent) idarəetmə bloku.
    """
    moves = []
    
    # U matrisi (Hansı mənbədən hara nə qədər göndəririk)
    u_matrix = defaultdict(lambda: defaultdict(int))
    
    # Hər mənbə üçün büdcə məhdudiyyəti
    available_budget = {src.id: src.ships for src in my_sources}
    
    # Kölgə qiymətlərini (Shadow Prices - lambda_i) təyin edirik
    # Ön cəbhədə qorunmağa ehtiyacı olan planetlərin lambda-sı yüksək olur.
    lambda_map = {}
    for src in my_sources:
        # Əgər simulyasiyanın sonunda bu planeti itiririksə, lambda kəskin artır!
        end_owner, _ = timeline.timelines[src.id].get(timeline.SIM_HORIZON, (src.owner, 0))
        if end_owner != player:
            lambda_map[src.id] = LAMBDA_BASE * 5.0 # Təcili qorunmalıdır, ordunu kənara buraxma
        else:
            lambda_map[src.id] = LAMBDA_BASE
            
    # İlkin mərhələ: Bütün etibarlı planları (arrival_turn və angle) toplayırıq
    # Burada artıq sabit DELTA_U deyil, hər hədəf üçün tələb olunan dəqiq gəmi sayını (req_ships) tapırıq
    valid_paths = defaultdict(list)
    for src in my_sources:
        if available_budget[src.id] <= 0: continue
        for tgt in all_targets:
            if tgt.id == src.id: continue
            
            # Spamın qarşısını almaq: əgər hədəf onsuz da bizim olacaqsa (əvvəlki atəşlərlə), iqnor et
            end_owner, _ = timeline.timelines[tgt.id].get(timeline.SIM_HORIZON, (tgt.owner, 0))
            if tgt.owner != player and end_owner == player:
                continue
            
            plans = find_valid_plan(src, tgt, timeline, available_budget[src.id], player, k_state)
            
            for plan in plans:
                req_ships = max(1, plan["ships"]) # Ən azı 1 gəmi (sıfıra bölmənin və s. qarşısını almaq üçün)
                valid_paths[src.id].append({
                    "tgt": tgt,
                    "arr_turn": plan["T"],
                    "angle": plan["angle"],
                    "req_ships": req_ships
                })

    # ==============================================================================
    # ITERATIVE GRADIENT ASCENT (Laqranj Optimizasiyası Dövrü)
    # ==============================================================================
    # Bizim U matrisimiz boşdur. Hər iterasiyada ən böyük marjinal fayda (qradiyent)
    # verən yola req_ships qədər gəmi əlavə edirik, ta ki büdcə bitənə qədər.
    
    optimization_active = True
    max_iterations = 200 # Sonsuz dövrün qarşısını almaq üçün təhlükəsizlik
    iters = 0
    
    while optimization_active and iters < max_iterations:
        optimization_active = False
        best_gradient = 0.0
        best_step = None # (src_id, tgt_id, angle, arr_turn, req_ships)
        
        # Qradiyent matrisini hesablayırıq
        for src in my_sources:
            lam_i = lambda_map[src.id]
            
            for path in valid_paths[src.id]:
                req_ships = path["req_ships"]
                
                # Bu yolu seçmək üçün kifayət qədər büdcə varmı?
                if available_budget[src.id] < req_ships: continue
                
                tgt = path["tgt"]
                arr_turn = path["arr_turn"]
                
                # Bu hədəfə əvvəlki iterasiyalarda göndərdiyimiz cəmi gəmi
                current_u = u_matrix[src.id][tgt.id]
                
                # Marjinal Faydanı (Delta J) hesablayırıq
                # Qeyd: Göndərdiyimiz ümumi gəmi = current_u + req_ships
                delta_J = _simulate_marginal_J_change(tgt, timeline, arr_turn, current_u + req_ships, player)
                
                # Əvvəlki addımın təsirini çıxırıq (Xalis marjinal fayda)
                if current_u > 0:
                    prev_delta_J = _simulate_marginal_J_change(tgt, timeline, arr_turn, current_u, player)
                    delta_J -= prev_delta_J
                
                # Laqranj Qradiyent Tənliyi: dL/du = (dJ/du) - lambda_i
                # Sərf olunan gəmi sayına (req_ships) və zaman itkisinə (arr_turn) görə normallaşdırırıq
                gradient = (delta_J / req_ships) / (1.0 + arr_turn * 0.05) - lam_i
                
                if gradient > best_gradient:
                    best_gradient = gradient
                    best_step = (src.id, tgt.id, path["angle"], arr_turn, req_ships)
                    
        # Əgər müsbət qradiyent tapdıqsa, həmin istiqamətə yatırım edirik
        if best_step is not None:
            opt_src_id, opt_tgt_id, opt_angle, _, opt_req_ships = best_step
            u_matrix[opt_src_id][opt_tgt_id] += opt_req_ships
            available_budget[opt_src_id] -= opt_req_ships
            optimization_active = True
        iters += 1

    # ==============================================================================
    # 3. YEKUN QƏRARLARIN ÇIXARILMASI (Extracting Final U Matrix)
    # ==============================================================================
    # Optimizasiya bitdikdən sonra U matrisində cəmlənmiş dəyərləri 'moves' formatına salırıq.
    
    for src_id, targets in u_matrix.items():
        for tgt_id, total_ships in targets.items():
            if total_ships > 0:
                # Göndəriləcək cəmi gəmi sayına uyğun olaraq DƏQİQ bucağı yenidən hesablayırıq
                src = k_state.planets[src_id]
                tgt = k_state.planets[tgt_id]
                
                final_aim = aim_at_target(src, tgt, total_ships, k_state)
                if final_aim:
                    final_angle, _ = final_aim
                    moves.append([int(src_id), float(final_angle), int(total_ships)])

    return moves

# ==============================================================================
# 6. AGENT ENTRY POINT
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
    
    moves = generate_strategy_moves(obs, player, my_sources, all_targets, timeline, k_state)

    return moves
