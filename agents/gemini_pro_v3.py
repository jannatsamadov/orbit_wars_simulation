import math

# ==========================================
# 1. KINEMATICS & PHYSICS ENGINE
# ==========================================
SUN_X, SUN_Y, SUN_R = 50.0, 50.0, 10.0
INNER_ORBIT_MAX = 42.0

def get_fleet_speed(ships: int) -> float:
    if ships <= 1: return 1.0
    return min(6.0, 1.0 + 5.0 * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5)

def check_sun_collision(sx: float, sy: float, tx: float, ty: float) -> bool:
    dx, dy = tx - sx, ty - sy
    l2 = dx * dx + dy * dy
    if l2 < 1e-9: return False
    
    t = max(0.0, min(1.0, ((SUN_X - sx) * dx + (SUN_Y - sy) * dy) / l2))
    proj_x = sx + t * dx
    proj_y = sy + t * dy
    return math.hypot(proj_x - SUN_X, proj_y - SUN_Y) < (SUN_R + 0.5)

def predict_position(x, y, angular_velocity, turns):
    dist_sun = math.hypot(x - SUN_X, y - SUN_Y)
    # Orbit edən planetləri tapmaq (Daxili planetlər və Kometalar)
    if dist_sun > SUN_R and dist_sun <= INNER_ORBIT_MAX and abs(angular_velocity) > 1e-9:
        theta = math.atan2(y - SUN_Y, x - SUN_X) + angular_velocity * turns
        return SUN_X + dist_sun * math.cos(theta), SUN_Y + dist_sun * math.sin(theta)
    return x, y

def get_intercept(sx, sy, tx, ty, w, fleet_size, iters=5):
    speed = get_fleet_speed(fleet_size)
    px, py = tx, ty
    t = math.hypot(px - sx, py - sy) / speed if speed > 0 else 999.0
    
    for _ in range(iters):
        px, py = predict_position(tx, ty, w, t)
        t = math.hypot(px - sx, py - sy) / speed
        
    px, py = predict_position(tx, ty, w, t)
    angle = math.atan2(py - sy, px - sx)
    return px, py, t, angle

# ==========================================
# 2. STRATEGIC EVALUATION ENGINE
# ==========================================
def calculate_required_ships(target, travel_turns):
    _, owner, _, _, _, ships, prod = target
    # Hədəf neytral deyilsə, uçuş vaxtı ərzində gəmi istehsal edəcək
    future_ships = ships + (prod * travel_turns if owner != -1 else 0)
    return int(future_ships) + 3 # +3 Təhlükəsizlik marjası (Kritik vuruşlar üçün)

def compute_roi_score(source, target, travel_turns, required_ships, my_player):
    _, owner, _, _, _, ships, prod = target
    
    # Qazancın hesablanması (Return on Investment)
    # Neytral planetlər ucuzdur, amma rəqibi vurmaq həm ona ziyan, həm bizə xeyirdir (2x swing)
    owner_multiplier = 1.0
    if owner == -1:
        owner_multiplier = 1.2 # Neytrallar ilkin inkişaf üçün yaxşıdır
    elif owner != my_player:
        owner_multiplier = 1.8 # Düşməni zəiflətmək prioritetdir
        
    value = prod * owner_multiplier
    cost = max(1, required_ships)
    time_penalty = max(1.0, travel_turns) ** 1.2
    
    return (value / cost) / time_penalty

# ==========================================
# 3. MAIN AGENT
# ==========================================
def agent(obs) -> list:
    player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
    w = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else getattr(obs, "angular_velocity", 0.0)
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else getattr(obs, "planets", [])
    
    my_planets = [p for p in raw_planets if p[1] == player]
    enemy_planets = [p for p in raw_planets if p[1] not in (player, -1)]
    targets = [p for p in raw_planets if p[1] != player]
    
    moves = []
    if not my_planets or not targets:
        return moves

    # Qlobal "Cəbhə Xətti" analizi (Frontline vs Backline)
    # Hər bir planetimizin ən yaxın düşmənə olan məsafəsini tapırıq
    frontline_threshold = 40.0 
    planet_roles = {} # pid -> is_frontline
    
    if enemy_planets:
        for mp in my_planets:
            min_dist_to_enemy = min(math.hypot(mp[2] - ep[2], mp[3] - ep[3]) for ep in enemy_planets)
            planet_roles[mp[0]] = min_dist_to_enemy < frontline_threshold
    else:
        planet_roles = {mp[0]: True for mp in my_planets}

    # Planetlərimizi əlçatan gəmi sayına görə sıralayırıq
    my_planets.sort(key=lambda p: p[5], reverse=True)
    
    # Göndərilən gəmilərin izlənməsi
    pending_deployments = {p[0]: 0 for p in my_planets}

    for source in my_planets:
        pid, _, sx, sy, _, ships, prod = source
        available_ships = int(ships) - pending_deployments[pid]
        
        # Cəbhə planetləri ehtiyat saxlayır (müdafiə üçün), Arxa planetlər hər şeyi göndərir
        is_frontline = planet_roles.get(pid, True)
        reserve = int(prod * 2) if is_frontline else 0
        deployable = available_ships - reserve
        
        if deployable <= 5:
            continue
            
        best_target = None
        best_score = -float('inf')
        best_action = None # (angle, send_amount)
        
        # 1. HÜCUM VƏ İŞĞAL FAZASI
        for target in targets:
            tx, ty = target[2], target[3]
            
            # İlkin təxmin üçün bütün gəmiləri göndərdiyimizi fərz edirik
            px, py, eta, _ = get_intercept(sx, sy, tx, ty, w, deployable)
            
            if check_sun_collision(sx, sy, px, py):
                continue
                
            required = calculate_required_ships(target, eta)
            if required > deployable:
                continue # Gücümüz çatmırsa, boşuna özümüzü yormuruq
                
            score = compute_roi_score(source, target, eta, required, player)
            
            if score > best_score:
                # Dəqiq göndəriləcək gəmi sayı ilə yenidən hesablayırıq
                actual_px, actual_py, actual_eta, actual_angle = get_intercept(sx, sy, tx, ty, w, required)
                final_req = calculate_required_ships(target, actual_eta)
                
                if final_req <= deployable and not check_sun_collision(sx, sy, actual_px, actual_py):
                    best_score = score
                    best_target = target
                    best_action = (actual_angle, final_req)

        # Əgər uğurlu bir hücum hədəfi tapıldısa, əmri ver
        if best_target and best_action:
            angle, send_amount = best_action
            moves.append([int(pid), float(angle), int(send_amount)])
            pending_deployments[pid] += send_amount
            deployable -= send_amount

        # 2. SUPPLY CHAIN (TƏCHİZAT) FAZASI - Arxa cəbhədən cəbhəyə transfer
        # Əgər planet "Backline" (Arxa cəbhə) sayılırsa və hələ də gəmisi qalıbsa, onu ən yaxın cəbhə planetinə göndər
        if not is_frontline and deployable > 10:
            best_friend = None
            min_friend_dist = float('inf')
            friend_angle = 0.0
            
            for friend in my_planets:
                fid = friend[0]
                if fid == pid or not planet_roles.get(fid, False): 
                    continue # Özünə və ya başqa arxa cəbhəyə göndərmə
                    
                fx, fy = friend[2], friend[3]
                fpx, fpy, feta, fangle = get_intercept(sx, sy, fx, fy, w, deployable)
                
                dist = math.hypot(sx - fpx, sy - fpy)
                if dist < min_friend_dist and not check_sun_collision(sx, sy, fpx, fpy):
                    min_friend_dist = dist
                    best_friend = friend
                    friend_angle = fangle
                    
            if best_friend:
                moves.append([int(pid), float(friend_angle), int(deployable)])
                pending_deployments[pid] += deployable

    return moves