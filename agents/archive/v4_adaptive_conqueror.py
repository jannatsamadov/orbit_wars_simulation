"""
Orbit Wars — Agent v4: "Adaptive Conqueror"
Taktika:
  1. ERKƏN OYUN & NEYTRALLAR (v1 aqressiyası):
     Neytral planetlər gəmi istehsal etmir. Onları zəbt etmək üçün
     sadəcə `ships + 1` göndəririk və MIN_GARRISON tətbiq etmirik (və ya az edirik).
     
  2. DÜŞMƏNƏ QARŞI (v3 dəqiqliyi):
     Düşmən planetlərinə qarşı tam iterativ orbit hesablanması (predict_pos).
     Gəmi istehsalı sürətini (ETA * production) nəzərə alıb böyük fleet göndərilir.
     Öz planetimizi qorumaq üçün MIN_GARRISON = 10 saxlanılır.
"""
import math
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet, Fleet
# ── Sabitlər ─────────────────────────────────────────────────────────────────
SUN_X, SUN_Y   = 50.0, 50.0
SUN_R          = 10.0
MAX_SPEED      = 6.0
ORBIT_LIMIT    = 40.0   
ITERATIONS     = 4      
def fleet_speed(ships: int) -> float:
    if ships <= 1:
        return 1.0
    return 1.0 + (MAX_SPEED - 1.0) * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5
def eta(dist: float, ships: int) -> float:
    spd = fleet_speed(ships)
    return dist / spd if spd > 0 else float("inf")
def predict_pos_from(mine_x, mine_y, planet, ships: int, angular_velocity: float):
    dx = planet.x - SUN_X
    dy = planet.y - SUN_Y
    orbital_r = math.hypot(dx, dy)
    if orbital_r >= ORBIT_LIMIT:
        return planet.x, planet.y
    current_angle = math.atan2(dy, dx)
    fx, fy = planet.x, planet.y
    for _ in range(ITERATIONS):
        dist_to_future = math.hypot(mine_x - fx, mine_y - fy)
        t = eta(dist_to_future, ships)
        future_angle = current_angle + angular_velocity * t
        fx = SUN_X + orbital_r * math.cos(future_angle)
        fy = SUN_Y + orbital_r * math.sin(future_angle)
    return fx, fy
def hits_sun(x0, y0, x1, y1) -> bool:
    dx, dy = x1 - x0, y1 - y0
    fx, fy = x0 - SUN_X, y0 - SUN_Y
    a = dx*dx + dy*dy
    if a == 0:
        return math.hypot(fx, fy) < SUN_R
    t = max(0.0, min(1.0, -(fx*dx + fy*dy) / a))
    return math.hypot(x0 + t*dx - SUN_X, y0 + t*dy - SUN_Y) < SUN_R
def target_score(target, mine) -> float:
    dist = math.hypot(mine.x - target.x, mine.y - target.y)
    # Neytral planetlər iqtisadiyyat üçün vacibdir, production önəmlidir
    return (target.production ** 2) / max(dist, 0.1)
def find_fleet_target(fleet, planets):
    best = None
    best_score = float("inf")
    for p in planets:
        dp_x = p.x - fleet.x
        dp_y = p.y - fleet.y
        dist = math.hypot(dp_x, dp_y)
        if dist < 0.1:
            continue
        angle_to_p = math.atan2(dp_y, dp_x)
        diff = abs(math.atan2(
            math.sin(fleet.angle - angle_to_p),
            math.cos(fleet.angle - angle_to_p)
        ))
        margin = math.asin(min(p.radius / dist, 1.0)) if dist > p.radius else math.pi
        if diff <= margin and dist < best_score:
            best_score = dist
            best = p
    return best
_angular_velocity = None
def agent(obs):
    global _angular_velocity
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
    if _angular_velocity is None:
        _angular_velocity = ang_vel
    planets      = [Planet(*p) for p in raw_planets]
    fleets       = [Fleet(*f)  for f in raw_fleets]
    my_planets   = [p for p in planets if p.owner == player]
    enemy_fleets = [f for f in fleets  if f.owner != player]
    planet_map   = {p.id: p for p in planets}
    moves = []
    used  = set()
    # 1. MÜDAFİƏ
    threatened = {}
    for ef in enemy_fleets:
        target_p = find_fleet_target(ef, my_planets)
        if target_p is not None:
            threatened[target_p.id] = threatened.get(target_p.id, 0) + ef.ships
    for pid, incoming in threatened.items():
        tp = planet_map.get(pid)
        if tp is None: continue
        surplus_needed = incoming - tp.ships + 5
        if surplus_needed <= 0: continue
        
        helpers = sorted(
            [p for p in my_planets if p.id != pid and p.ships > 10 + surplus_needed],
            key=lambda p: math.hypot(p.x - tp.x, p.y - tp.y)
        )
        if helpers:
            helper = helpers[0]
            send = min(helper.ships - 10, surplus_needed)
            if send >= 5:
                ang = math.atan2(tp.y - helper.y, tp.x - helper.x)
                if not hits_sun(helper.x, helper.y, tp.x, tp.y):
                    moves.append([helper.id, ang, send])
                    used.add(helper.id)
    # 2. HÜCUM (Adaptiv)
    attack_targets = [p for p in planets if p.owner != player]
    
    for mine in my_planets:
        if mine.id in used:
            continue
        scored_targets = sorted(attack_targets, key=lambda t: target_score(t, mine), reverse=True)
        for target in scored_targets:
            if target.id in used:
                continue
            is_neutral = (target.owner == -1)
            
            # Adaptiv Garrison: Neytrallara sürətli yayılmaq üçün minimum qorunmanı azaltdıq
            min_garrison = 2 if is_neutral else 10
            available = mine.ships - min_garrison
            
            if available <= 0:
                continue
            if is_neutral:
                # Neytral planetlərə v1 aqressiyası
                ships_to_send = target.ships + 1
            else:
                # Düşmən planetlərə v3 dəqiqliyi
                ships_to_send = target.ships + 5
            if available < ships_to_send:
                continue # Gözlə
            # Orbit prediction (düşmən üçünsə ETA əlavə edib təkrar hesablayırıq)
            fx, fy = predict_pos_from(mine.x, mine.y, target, ships_to_send, _angular_velocity)
            
            if not is_neutral:
                dist_to_future = math.hypot(mine.x - fx, mine.y - fy)
                t = eta(dist_to_future, ships_to_send)
                # Düşmən bu müddətdə nə qədər gəmi istehsal edəcək
                ships_to_send += int(target.production * t)
            
            ships_to_send = min(ships_to_send, available)
            if ships_to_send < target.ships + 1:
                continue
            if hits_sun(mine.x, mine.y, fx, fy):
                continue
            angle = math.atan2(fy - mine.y, fx - mine.x)
            moves.append([mine.id, angle, ships_to_send])
            used.add(target.id)
            break
    return moves