"""
Orbit Wars — Agent v3: "Precision Striker"
Improvements over baseline (nearest_planet_sniper):
  1. Orbit prediction  — aims at where a rotating planet WILL BE, not where it is now
  2. Sun avoidance     — skips moves whose straight-line path crosses the sun
  3. Priority targets  — prefers high-production planets over mere proximity
  4. Defense           — reinforces own planets that enemy fleets are heading toward
  5. No double-send    — each planet picks one target per turn

Orbit prediction FIX (v2-dəki əsas xəta düzəldildi):
  v3 DÜZGÜN: obs-dakı CARI mövqe → current_angle → current_angle + omega*ETA = future_angle

Orbit prediction düsturu (sadə, dəqiq):
  1. planet.x, planet.y → current_angle = atan2(y - SUN_Y, x - SUN_X)
  2. ETA = distance / fleet_speed   (ilkin təxmin — cari mövqəyə görə)
  3. future_angle = current_angle + angular_velocity * ETA
  4. future_pos = SUN_XY + orbital_r * (cos, sin)(future_angle)
  5. Yeni ETA = dist(mine, future_pos) / fleet_speed  → 3-4 iteration ilə konvergə olur

Sair yenilikər:
  - Müdafiə: düşmən fleetin hədəfi daha dəqiq aşkar edilir (planet radiu yoxlanışı)
  - Production-weighted priority: production² / distance
  - Overflow qorunması: planetdə minimum 10 gəmi qalır
"""
import math
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet, Fleet

# ── sabitlər ─────────────────────────────────────────────────────────────────
SUN_X, SUN_Y   = 50.0, 50.0
SUN_R          = 10.0
MAX_SPEED      = 6.0
ORBIT_LIMIT    = 40.0   # bu radiusdan yaxın planetlər fırlanır
MIN_GARRISON   = 10     # planetdə minimum qalan gəmi sayı
ITERATIONS     = 4      # ETA iteration sayı

# ── module-level state (persists between turns) ───────────────────────────────
_angular_velocity = None

# ── sürət formulası ──────────────────────────────────────────────────────────
def fleet_speed(ships: int) -> float:
    """Oyun spec-dəki logarithmik sürət formulu."""
    if ships <= 1:
        return 1.0
    return 1.0 + (MAX_SPEED - 1.0) * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5

def eta(dist: float, ships: int) -> float:
    spd = fleet_speed(ships)
    return dist / spd if spd > 0 else float("inf")

# ── orbit prediction (düzgün) ─────────────────────────────────────────────────
def predict_pos_from(mine_x, mine_y, planet, ships: int, angular_velocity: float):
    """
    mine (x,y) planet-dən planetin gələcək mövqeyini hesabla.
    ITERATIONS dəfə ETA-nı yeniləyir — konvergə olana qədər.
    """
    dx = planet.x - SUN_X
    dy = planet.y - SUN_Y
    orbital_r = math.hypot(dx, dy)
    
    # Statik planet
    if orbital_r >= ORBIT_LIMIT:
        return planet.x, planet.y
        
    current_angle = math.atan2(dy, dx)
    
    # Başlanğıc: cari mövqəyə görə ilkin məsafə və ETA
    fx, fy = planet.x, planet.y
    for _ in range(ITERATIONS):
        dist_to_future = math.hypot(mine_x - fx, mine_y - fy)
        t = eta(dist_to_future, ships)
        future_angle = current_angle + angular_velocity * t
        fx = SUN_X + orbital_r * math.cos(future_angle)
        fy = SUN_Y + orbital_r * math.sin(future_angle)
        
    return fx, fy

# ── günəş yolu yoxlaması ─────────────────────────────────────────────────────
def hits_sun(x0, y0, x1, y1) -> bool:
    """Xətt seqmenti günəşin içindən keçirsə True."""
    dx, dy = x1 - x0, y1 - y0
    fx, fy = x0 - SUN_X, y0 - SUN_Y
    a = dx*dx + dy*dy
    if a == 0:
        return math.hypot(fx, fy) < SUN_R
    t = max(0.0, min(1.0, -(fx*dx + fy*dy) / a))
    return math.hypot(x0 + t*dx - SUN_X, y0 + t*dy - SUN_Y) < SUN_R

# ── hədəf prioriteti ─────────────────────────────────────────────────────────
def target_score(target, mine) -> float:
    """
    Hədəf dəyərini hesabla. Yüksək = daha cəzbedici.
    production² / distance — həm istehsal həm yaxınlığı nəzərə alır.
    """
    dist = math.hypot(mine.x - target.x, mine.y - target.y)
    return (target.production ** 2) / max(dist, 0.1)

# ── düşmən fleeti hədəf planetini tap ────────────────────────────────────────
def find_fleet_target(fleet, planets):
    """
    Enemy fleetin hara getdiyini tap:
    fleet.angle istiqamətindəki ən yaxın planeti tap.
    """
    best = None
    best_score = float("inf")
    for p in planets:
        # Fleet-dən planetə vektor
        dp_x = p.x - fleet.x
        dp_y = p.y - fleet.y
        dist = math.hypot(dp_x, dp_y)
        if dist < 0.1:
            continue
        # Açı fərqi
        angle_to_p = math.atan2(dp_y, dp_x)
        diff = abs(math.atan2(
            math.sin(fleet.angle - angle_to_p),
            math.cos(fleet.angle - angle_to_p)
        ))
        # Planet radiusuna görə marja — böyük planet geniş hədəf
        margin = math.asin(min(p.radius / dist, 1.0)) if dist > p.radius else math.pi
        if diff <= margin and dist < best_score:
            best_score = dist
            best = p
    return best

# ── əsas agent ───────────────────────────────────────────────────────────────
def agent(obs):
    global _angular_velocity
    
    # ── observation parse ────────────────────────────────────────────────────
    if isinstance(obs, dict):
        player      = obs.get("player", 0)
        raw_planets = obs.get("planets", [])
        raw_fleets  = obs.get("fleets", [])
        ang_vel     = obs.get("angular_velocity", 0.0)
    else:
        player      = obs.player
        raw_planets = obs.planets
        raw_fleets  = getattr(obs, "fleets", [])
        ang_vel     = getattr(obs, "angular_velocity", 0.0)
        
    # Cache angular_velocity
    if _angular_velocity is None:
        _angular_velocity = ang_vel
        
    planets      = [Planet(*p) for p in raw_planets]
    fleets       = [Fleet(*f)  for f in raw_fleets]
    my_planets    = [p for p in planets if p.owner == player]
    enemy_fleets  = [f for f in fleets  if f.owner != player]
    planet_map    = {p.id: p for p in planets}
    
    moves = []
    used    = set()   # bu turda hərəkət edən planet id-ləri
    
    # ── MÜDAFİƏ: gələn düşmən fleetlərə cavab ────────────────────────────────
    threatened = {}   # my_planet_id -> total incoming enemy ships
    for ef in enemy_fleets:
        target_p = find_fleet_target(ef, my_planets)
        if target_p is not None:
            threatened[target_p.id] = threatened.get(target_p.id, 0) + ef.ships
            
    for pid, incoming in threatened.items():
        tp = planet_map.get(pid)
        if tp is None:
            continue
            
        surplus_needed = incoming - tp.ships + 5  # bu qədər əlavə gəmi lazımdır
        if surplus_needed <= 0:
            continue  # öz gücü ilə dəf edər
            
        # Ən yaxın köməkçi planet tap
        helpers = sorted(
            [p for p in my_planets if p.id != pid and p.ships > MIN_GARRISON + surplus_needed],
            key=lambda p: math.hypot(p.x - tp.x, p.y - tp.y)
        )
        if not helpers:
            continue
            
        helper = helpers[0]
        send   = min(helper.ships - MIN_GARRISON, surplus_needed)
        if send < 5:
            continue
            
        ang = math.atan2(tp.y - helper.y, tp.x - helper.x)
        if not hits_sun(helper.x, helper.y, tp.x, tp.y):
            moves.append([helper.id, ang, send])
            used.add(helper.id)
            
    # ── HÜCUM: ən dəyərli hədəfi fəth et ─────────────────────────────────────
    attack_targets = [p for p in planets if p.owner != player]
    
    for mine in my_planets:
        if mine.id in used:
            continue
            
        available = mine.ships - MIN_GARRISON
        if available <= 5:
            continue
            
        # Hədəfləri prioritetə görə sırala
        scored = sorted(
            attack_targets,
            key=lambda t: target_score(t, mine),
            reverse=True
        )
        
        for target in scored:
            if target.id in used:
                continue
                
            # ── DÜZGÜN orbit prediction ──────────────────────────────────────
            # 1. Ships needed: bufferlə
            ships_to_send = max(target.ships + 5, 15)  # some buffer
            
            # 2. Iterativ future pos hesabı (mine.x, mine.y-dən)
            fx, fy = predict_pos_from(
                mine.x, mine.y, target, ships_to_send, _angular_velocity
            )
            
            # 3. ETA-ya görə düşmən planetin topladığı əlavə gəmiləri əlavə et
            dist_to_future = math.hypot(mine.x - fx, mine.y - fy)
            t = eta(dist_to_future, ships_to_send)
            
            if target.owner >= 0:
                ships_to_send += int(target.production * t)
                
            ships_to_send = min(ships_to_send, available)
            if ships_to_send < target.ships + 1:
                continue   # kifayət etmir
                
            # 4. Günəş yoxlaması — gələcək mövqeyə doğru yol güvənlidirmi?
            if hits_sun(mine.x, mine.y, fx, fy):
                continue
                
            # 5. Atəş!
            angle = math.atan2(fy - mine.y, fx - mine.x)
            moves.append([mine.id, angle, ships_to_send])
            used.add(target.id)
            break
            
    return moves