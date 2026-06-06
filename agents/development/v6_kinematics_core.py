import math
import random
from collections import defaultdict, namedtuple

# ==============================================================================
# 1. KINEMATIC ENGINE CONSTANTS
# ==============================================================================
BOARD_SIZE = 100.0
SUN_X, SUN_Y, SUN_RADIUS = 50.0, 50.0, 10.0
SUN_SAFETY_MARGIN = 1.5 # Gəmilərin günəşə çox yaxınlaşmaması üçün əlavə bufer
MAX_SPEED = 6.0

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
    """Bucağı -pi və pi arasında normalizasiya edir"""
    while angle > math.pi: angle -= 2 * math.pi
    while angle < -math.pi: angle += 2 * math.pi
    return angle

def point_to_segment_distance(px, py, x1, y1, x2, y2):
    """Bir nöqtənin (Günəşin mərkəzinin) xətt parçasına (uçuş yoluna) olan məsafəsini tapır."""
    dx, dy = x2 - x1, y2 - y1
    seg_sq = dx * dx + dy * dy
    if seg_sq <= 1e-9:
        return get_distance(px, py, x1, y1)
    
    # Proyeksiya (t) - xətt parçasında ən yaxın nöqtəni tapır
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_sq))
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    
    return get_distance(px, py, closest_x, closest_y)

def is_path_blocked_by_sun(sx, sy, tx, ty, target_radius=0):
    """
    Qeyd (User Feedback): Günəş ilə toqquşma ehtimalı burada yoxlanılır.
    Əgər Mənbədən (sx, sy) Hədəfə (tx, ty) çəkilən düz xətt Günəşin radiusundan (və təhlükəsizlik buferindən)
    yaxın keçirsə, xətt bloklanmış (yanmış) hesab edilir.
    """
    # Mərminin gəlib çatacağı yeri hesablayırıq (hədəfin kənarı qədər məsafə daxilində)
    total_dist = get_distance(sx, sy, tx, ty)
    if total_dist < 1e-9:
        return False
    
    # Toqquşma anı üçün xətt seqmenti (sx,sy) - (tx, ty)
    dist_to_sun = point_to_segment_distance(SUN_X, SUN_Y, sx, sy, tx, ty)
    if dist_to_sun < (SUN_RADIUS + SUN_SAFETY_MARGIN):
        return True
    return False

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
        
        self.planet_kinematics = {} # id -> (is_orbital, ang_vel, r, phase)
        self.comet_ids = set()
        
        # Comets parsing
        for group in self.comets_data:
            pids = group.get("planet_ids", []) if isinstance(group, dict) else getattr(group, "planet_ids", [])
            for pid in pids:
                self.comet_ids.add(pid)
        
        self._calculate_kinematics()

    def _calculate_kinematics(self):
        """
        Qeyd (User Feedback): İkinci turndan (step > 0) etibarən fırlanma sürətini hər planet üçün 
        individual (fərdi) hesablayır.
        """
        for pid, current_p in self.planets.items():
            if pid in self.comet_ids:
                self.planet_kinematics[pid] = {
                    "is_orbital": False,
                    "ang_vel": 0.0,
                    "radius": 0.0,
                    "init_phase": 0.0,
                    "curr_phase": 0.0
                }
                continue # Kometlərin yolu öz path-ində saxlanır
                
            init_p = self.initial_planets.get(pid, current_p)
            r = get_distance(init_p.x, init_p.y, SUN_X, SUN_Y)
            
            # Əgər oyun başlanğıcıdırsa (step 0), standart radius-based heuristic istifadə edirik
            if self.step == 0:
                is_orbital = (r + init_p.radius < 45.0)
                ang_vel = self.global_ang_vel if is_orbital else 0.0
            else:
                # İkinci (və ya daha sonrakı) addımlarda dəqiq hesablayırıq
                init_angle = math.atan2(init_p.y - SUN_Y, init_p.x - SUN_X)
                curr_angle = math.atan2(current_p.y - SUN_Y, current_p.x - SUN_X)
                
                # Bucağın dəyişməsini tapırıq
                angle_diff = normalize_angle(curr_angle - init_angle)
                
                # Orta fırlanma sürəti: radians per turn
                calculated_ang_vel = angle_diff / self.step
                
                # Əgər hərəkət edibsə (çox kiçik floating point error-dan yuxarı)
                if abs(calculated_ang_vel) > 1e-6:
                    is_orbital = True
                    ang_vel = calculated_ang_vel
                else:
                    is_orbital = False
                    ang_vel = 0.0
                    
            self.planet_kinematics[pid] = {
                "is_orbital": is_orbital,
                "ang_vel": ang_vel,
                "radius": r,
                "init_phase": math.atan2(init_p.y - SUN_Y, init_p.x - SUN_X),
                "curr_phase": curr_angle if self.step > 0 else math.atan2(current_p.y - SUN_Y, current_p.x - SUN_X)
            }

    def predict_target_position(self, target_id, turns_ahead):
        """Hədəfin gələcəkdə (t gediş sonra) harada olacağını tapır (həm planet, həm komet)"""
        if target_id in self.comet_ids:
            return self._predict_comet(target_id, turns_ahead)
            
        kinematics = self.planet_kinematics.get(target_id)
        if not kinematics:
            # Fallback - əgər nəsə problem varsa
            p = self.planets[target_id]
            return p.x, p.y
            
        if not kinematics["is_orbital"]:
            p = self.planets.get(target_id)
            return p.x, p.y
            
        # Fırlanan planetin gələcək mövqeyi
        total_turns = self.step + turns_ahead
        new_phase = kinematics["init_phase"] + kinematics["ang_vel"] * total_turns
        r = kinematics["radius"]
        
        future_x = SUN_X + r * math.cos(new_phase)
        future_y = SUN_Y + r * math.sin(new_phase)
        return future_x, future_y

    def _predict_comet(self, comet_id, turns_ahead):
        for group in self.comets_data:
            pids = group.get("planet_ids", []) if isinstance(group, dict) else getattr(group, "planet_ids", [])
            if comet_id not in pids:
                continue
            idx = pids.index(comet_id)
            paths = group.get("paths", []) if isinstance(group, dict) else getattr(group, "paths", [])
            path_index = group.get("path_index", 0) if isinstance(group, dict) else getattr(group, "path_index", 0)
            
            if idx >= len(paths):
                return None
            path = paths[idx]
            future_idx = int(path_index) + int(turns_ahead)
            if 0 <= future_idx < len(path):
                return float(path[future_idx][0]), float(path[future_idx][1])
            # Əgər komet oyundan çıxacaqsa, None qaytarırıq
            return None
        return None

# ==============================================================================
# 4. ITERATIVE INTERCEPTION ALGORITHM
# ==============================================================================
def aim_at_target(src_planet, target_planet, num_ships, k_state: KinematicsState, max_iters=5):
    """
    Qeyd (User Feedback): Kometdən və ya fırlanan planetdən fırlanan (və ya statik) planeti vurmaq.
    Mənbə fırlanan ola bilər, amma gəmini Atdığımız an o anki x,y-dən düz xətt boyunca gedəcək.
    Ona görə də src_planet.x və src_planet.y sabit başlanğıc hesab olunur.
    
    Qaytarır: (angle, travel_time) və ya bloklanıbsa None.
    """
    speed = get_fleet_speed(num_ships)
    
    # 1. İlk ehtimal: Hədəf elə yerində dursa neçə gedişə çatarıq?
    dist = get_distance(src_planet.x, src_planet.y, target_planet.x, target_planet.y)
    est_turns = max(1.0, dist / speed)
    
    # 2. İterativ olaraq hədəfin gələcək yerinə görə vaxtı düzəldirik (Iterative refinement)
    for _ in range(max_iters):
        predicted_pos = k_state.predict_target_position(target_planet.id, est_turns)
        if not predicted_pos:
            return None # Komet məhv olub/oyundan çıxıb
            
        px, py = predicted_pos
        dist = get_distance(src_planet.x, src_planet.y, px, py)
        # Hədəfin kənarına çatmaq kifayətdir (optional olaraq: - target_planet.radius)
        # Amma daha dəqiq olması üçün mərkəzini hədəf alırıq
        est_turns = max(1.0, dist / speed)
        
    # Ən son tapılmış gediş sayını tam ədədə (yuxarı) yuvarlaqlaşdırırıq
    final_turns = int(math.ceil(est_turns))
    final_pos = k_state.predict_target_position(target_planet.id, final_turns)
    
    if not final_pos:
        return None
        
    fx, fy = final_pos
    
    # Sun Collision (Günəş bloklaması) Yoxlaması!
    if is_path_blocked_by_sun(src_planet.x, src_planet.y, fx, fy, target_planet.radius):
        return None
        
    angle = math.atan2(fy - src_planet.y, fx - src_planet.x)
    return angle, final_turns

# ==============================================================================
# 5. AGENT ENTRY POINT
# ==============================================================================
def agent(obs) -> list:
    player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
    
    # Kinematik State Engine-i işə salırıq
    k_state = KinematicsState(obs)
    
    my_sources = [p for p in k_state.planets.values() if p.owner == player]
    all_targets = list(k_state.planets.values())
    
    moves = []
    committed_ships = defaultdict(int)
    
    # Bütün planetlərdən (kometlər daxil) bütün digər hədəflərə (planet + komet) test atışları
    for src in my_sources:
        avail = src.ships - committed_ships[src.id]
        
        for target in all_targets:
            if src.id == target.id:
                continue
                
            if avail <= 0:
                break
                
            # 1 ilə 5 arasında təsadüfi sayda gəmi göndəririk
            ships_to_send = random.randint(1, 5)
            if avail < ships_to_send:
                ships_to_send = avail # Qalan nə varsa onu at
                
            aim = aim_at_target(src, target, ships_to_send, k_state)
            if aim is not None:
                angle, travel_time = aim
                moves.append([int(src.id), float(angle), int(ships_to_send)])
                committed_ships[src.id] += ships_to_send
                avail -= ships_to_send

    return moves
