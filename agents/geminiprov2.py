import math

# ==========================================
# ADVANCED KINEMATICS & PHYSICS ENGINE
# ==========================================

def get_fleet_speed(ships: int) -> float:
    """Loqarifmik miqyaslama düsturuna əsasən donanmanın sürətini hesablayır."""
    if ships <= 1: 
        return 1.0
    return min(6.0, 1.0 + (6.0 - 1.0) * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5)

def check_sun_collision(sx: float, sy: float, tx: float, ty: float) -> bool:
    """
    Donanmanın (sx, sy) nöqtəsindən (tx, ty) nöqtəsinə düz xətt üzrə hərəkətinin 
    (50.0, 50.0) mərkəzli və 10.0 radiuslu Günəşlə kəsişib-kəsişmədiyini yoxlayır.
    """
    sun_x, sun_y, sun_radius = 50.0, 50.0, 10.0
    
    dx = tx - sx
    dy = ty - sy
    l2 = dx * dx + dy * dy
    
    if l2 == 0:
        return math.dist((sx, sy), (sun_x, sun_y)) < sun_radius
        
    t = max(0.0, min(1.0, ((sun_x - sx) * dx + (sun_y - sy) * dy) / l2))
    
    proj_x = sx + t * dx
    proj_y = sy + t * dy
    
    return math.dist((proj_x, proj_y), (sun_x, sun_y)) < (sun_radius + 0.5)

def predict_interception(sx: float, sy: float, tx: float, ty: float, 
                         angular_velocity: float, speed: float, is_static: bool = False) -> tuple:
    """
    Əgər planet statikdirsə (xarici planet), birbaşa hədəfə atəş açır.
    Fırlanırsa (daxili planet), iterativ olaraq gələcək kəsişmə nöqtəsini tapır.
    Qaytarır: (intercept_x, intercept_y, time_of_flight, launch_angle)
    """
    if is_static or angular_velocity == 0.0:
        dist = math.dist((sx, sy), (tx, ty))
        angle = math.atan2(ty - sy, tx - sx)
        return tx, ty, dist / speed, angle
        
    sun_x, sun_y = 50.0, 50.0
    R = math.dist((sun_x, sun_y), (tx, ty))
    initial_angle = math.atan2(ty - sun_y, tx - sun_x)
    
    t = math.dist((sx, sy), (tx, ty)) / speed 
    
    pred_x, pred_y = tx, ty
    for _ in range(10): 
        future_angle = initial_angle + (angular_velocity * t)
        pred_x = sun_x + R * math.cos(future_angle)
        pred_y = sun_y + R * math.sin(future_angle)
        
        new_dist = math.dist((sx, sy), (pred_x, pred_y))
        new_t = new_dist / speed
        
        if abs(new_t - t) < 0.05: 
            t = new_t
            break
        t = new_t
        
    launch_angle = math.atan2(pred_y - sy, pred_x - sx)
    return pred_x, pred_y, t, launch_angle

# ==========================================
# AGENT LOGIC & STRATEGY
# ==========================================

def agent(obs) -> list:
    """Əsas agent funksiyası."""
    # 1. Mühitin Təhlükəsiz Parsinqi
    player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
    angular_velocity = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else getattr(obs, "angular_velocity", 0.0)
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else getattr(obs, "planets", [])
    
    my_planets = []
    targets = []
    
    for p in raw_planets:
        p_data = {
            "id": p[0], "owner": p[1], "x": p[2], "y": p[3], 
            "radius": p[4], "ships": p[5], "production": p[6]
        }
        if p_data["owner"] == player:
            my_planets.append(p_data)
        else:
            targets.append(p_data)
            
    moves = []
    
    # Gəmi sayına görə sıralayırıq ki, ilk olaraq ən güclü planetlərdən hücum edək
    my_planets.sort(key=lambda p: p["ships"], reverse=True)
    
    for source in my_planets:
        available_ships = source["ships"]
        
        # Baza müdafiəsi üçün istehsalat sürətinə mütənasib gəmi saxlayırıq
        garrison = source["production"] * 2
        deployable_ships = available_ships - garrison
        
        if deployable_ships <= 5:
            continue
            
        # 2. Dinamik Faydalılıq Hesablanması (Dynamic Utility Scoring)
        best_target = None
        best_score = -float('inf')
        best_action = None
        
        for target in targets:
            theoretical_speed = get_fleet_speed(deployable_ships)
            
            # Daxili və Xarici planeti ayıran məsafə
            orbit_radius = math.dist((target["x"], target["y"]), (50.0, 50.0))
            INNER_PLANET_MAX_RADIUS = 40.0 # Bura oyunun dəqiq ölçüsünə görə dəqiqləşdirilə bilər
            target_is_static = orbit_radius > INNER_PLANET_MAX_RADIUS
            
            # Kəsişməni proqnozlaşdırırıq
            pred_x, pred_y, t, angle = predict_interception(
                source["x"], source["y"], target["x"], target["y"], 
                angular_velocity, theoretical_speed, is_static=target_is_static
            )
            
            # Günəşlə toqquşma ehtimalını yoxlayırıq
            if check_sun_collision(source["x"], source["y"], pred_x, pred_y):
                continue
                
            # Hədəfə çatana qədər onun yığacağı gəmiləri hesablayırıq
            future_garrison = target["ships"] + (target["production"] * t if target["owner"] != -1 else 0)
            required_ships = int(future_garrison) + 5 # Təhlükəsizlik marjası kimi əlavə 5 gəmi
            
            if required_ships > deployable_ships:
                continue 
                
            # Faydalılıq düsturu
            utility = target["production"] / (t + 1.0) 
            score = utility / max(1, required_ships)
            
            # Rəqib planetlərini neytrallardan üstün tuturuq
            if target["owner"] != -1:
                score *= 1.2 
                
            if score > best_score:
                best_score = score
                best_target = target
                
                # Dəqiq göndərəcəyimiz gəmi sayına görə sürəti və vaxtı yenidən hesablayırıq
                actual_speed = get_fleet_speed(required_ships)
                _, _, actual_t, actual_angle = predict_interception(
                    source["x"], source["y"], target["x"], target["y"], 
                    angular_velocity, actual_speed, is_static=target_is_static
                )
                
                actual_future_garrison = target["ships"] + (target["production"] * actual_t if target["owner"] != -1 else 0)
                final_required = int(actual_future_garrison) + 5
                
                if final_required <= deployable_ships:
                    best_action = (actual_angle, final_required)
                else:
                    best_action = (angle, deployable_ships)
                    
        # 3. Əmrlərin verilməsi
        if best_target and best_action:
            launch_angle, ships_to_send = best_action
            moves.append([source["id"], float(launch_angle), int(ships_to_send)])
            
    return moves