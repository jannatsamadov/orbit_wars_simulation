"""
Orbit Wars — Agent v5: "Swarm Intelligence"
Fəlsəfə:
1. Qlobal İdarəetmə: Bütün planetlərdəki boş gəmiləri bir "ortaq hovuz" kimi düşünür.
2. Swarm Center: Atəş nöqtəmiz kimi bütün planetlərimizin ağırlıq mərkəzini götürür.
3. Hədəf Qiymətləndirmə (User Rule): 
   - İstehsalı (production) yüksək olanlara üstünlük verir.
   - "Bizə doğru gələn" (gələcək mövqeyi mərkəzimizə indiki mövqeyindən daha yaxın olan) fırlanan planetlərə əlavə xal verir.
   - Çox uzaq hədəfləri (məsələn, 3 turndan gec çatanları) nisbətən cəzalandırır.
4. Sinxron Atəş: Bir hədəf üçün lazım olan gəmini tək planet deyil, bir neçə ən yaxın planet ortaqlaşa ödəyir.
"""
import math
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet, Fleet
# ── Sabitlər ─────────────────────────────────────────────────────────────────
SUN_X, SUN_Y   = 50.0, 50.0
SUN_R          = 10.0
MAX_SPEED      = 6.0
ORBIT_LIMIT    = 40.0   
ITERATIONS     = 4      
MIN_GARRISON   = 5      # Swarm hər planetdə az qorunma saxlayıb böyük hovuz yaradır
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
    my_planets   = [p for p in planets if p.owner == player]
    
    # Heç planetimiz yoxdursa
    if not my_planets:
        return []
    moves = []
    
    # ── SWARM QLOBAL HOVUZU ──────────────────────────────────────────────────
    swarm_pool = {}
    total_available = 0
    cx_num, cy_num, weight_sum = 0.0, 0.0, 0.0
    
    for p in my_planets:
        avail = max(0, p.ships - MIN_GARRISON)
        swarm_pool[p.id] = avail
        total_available += avail
        
        # Ağırlıq mərkəzi (çox gəmisi olan planetin çəkisi çoxdur)
        if avail > 0:
            cx_num += p.x * avail
            cy_num += p.y * avail
            weight_sum += avail
            
    if weight_sum == 0:
        return [] # Atəş edəcək gəmi yoxdur
        
    swarm_cx = cx_num / weight_sum
    swarm_cy = cy_num / weight_sum
    # ── HƏDƏF SEÇİMİ VƏ QİYMƏTLƏNDİRİLMƏSİ ───────────────────────────────────
    attack_targets = [p for p in planets if p.owner != player]
    target_scores = []
    
    for target in attack_targets:
        # Gələcək mövqeyi Swarm Center-dən təxmin edirik 
        # (30 gəmi ortalama sürət hesablanaraq)
        fx, fy = predict_pos_from(swarm_cx, swarm_cy, target, 30, _angular_velocity)
        
        current_dist = math.hypot(swarm_cx - target.x, swarm_cy - target.y)
        future_dist  = math.hypot(swarm_cx - fx, swarm_cy - fy)
        
        # 1. "BİZƏ DOĞRU GƏLƏN" yoxlanışı
        # Gələcəkdəki məsafə indikindən azdırsa, deməli bizə tərəf gəlir!
        is_approaching = future_dist < current_dist
        approach_bonus = 2.0 if is_approaching else 1.0
        
        # 2. İSTEHSAL (Production) prioriteti
        # Neytral da olsa böyük planetlər önəmlidir
        prod_val = target.production if target.production > 0 else 1.0
        
        # 3. YAXINLIQ
        # Hədəfə sürətli çatmağı üstün tutur (istək: ~3 turn)
        dist_factor = max(future_dist, 0.1)
        
        # Ümumi Score
        score = (prod_val ** 2) * approach_bonus / dist_factor
        
        # Tələb olunan gəmi (Neytrallara daha az ekstra)
        t = eta(future_dist, 30)
        extra = int(target.production * t) if target.owner >= 0 else 0
        ships_needed = target.ships + extra + 2  # Swarm üçün buffer
        
        if not hits_sun(swarm_cx, swarm_cy, fx, fy):
            target_scores.append((score, target, ships_needed))
            
    # Ən dəyərli hədəflərə görə sırala
    target_scores.sort(key=lambda x: x[0], reverse=True)
    # ── SİNXRON ATƏŞ (COORDINATED STRIKE) ────────────────────────────────────
    
    for score, target, needed in target_scores:
        if total_available < needed:
            # Hovuzda kifayət qədər gəmi yoxdursa, gözləyirik (Swarm toplanır)
            continue
            
        # Hədəf üçün planetləri hədəfə yaxınlığa görə sıralayırıq
        # kiçik zərbələrlə uzaqdan yox, ən yaxınlarımızdan yığaq
        # Gələcək pozisiyanı yenidən dəqiq hesablayaq (hədəf kilidlənib)
        
        # Seçiləcək planetlər
        contributors = []
        
        # Məsafəyə görə sıralanmış öz planetlərimiz
        sorted_mine = sorted(
            [p for p in my_planets if swarm_pool[p.id] > 0],
            key=lambda p: math.hypot(p.x - target.x, p.y - target.y)
        )
        
        accumulated = 0
        for p in sorted_mine:
            avail = swarm_pool[p.id]
            take = min(avail, needed - accumulated)
            
            # Günəşə çırpılmırsa cəlb et
            # Dəqiq intercept point (bu planetin özündən)
            px, py = predict_pos_from(p.x, p.y, target, take, _angular_velocity)
            if not hits_sun(p.x, p.y, px, py):
                contributors.append((p, px, py, take))
                accumulated += take
                
            if accumulated >= needed:
                break
                
        # Əgər uğurla yığışdıqsa, ATAQ!
        if accumulated >= needed:
            for p, px, py, take in contributors:
                angle = math.atan2(py - p.y, px - p.x)
                moves.append([p.id, angle, take])
                # Hovuzdan çıxar
                swarm_pool[p.id] -= take
                total_available -= take
                
        # Növbəti hədəf üçün qalan hovuzla davam et...
    return moves
