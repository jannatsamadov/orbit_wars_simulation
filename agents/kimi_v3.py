import math
from collections import defaultdict

def get_fleet_speed(ships: int) -> float:
    if ships <= 1:
        return 1.0
    return 1.0 + 5.0 * (math.log(max(ships, 1)) / math.log(1000.0)) ** 1.5

def agent(obs):
    # ==================== OBSERVATION PARSING ====================
    if isinstance(obs, dict):
        player = obs.get("player", 0)
        ang_vel = obs.get("angular_velocity", 0.0)
        planets_raw = obs.get("planets", []) or []
        fleets_raw = obs.get("fleets", []) or []
    else:
        player = getattr(obs, "player", 0)
        ang_vel = getattr(obs, "angular_velocity", 0.0)
        planets_raw = getattr(obs, "planets", []) or []
        fleets_raw = getattr(obs, "fleets", []) or []
    
    moves = []
    if not planets_raw:
        return moves
    
    # ==================== PLANET PARSING ====================
    planets = {}
    my_planets = []
    enemy_planets = []
    neutral_planets = []
    
    for p in planets_raw:
        pid, owner, x, y, radius, ships, prod = p
        planet = {
            "id": int(pid), "owner": int(owner),
            "x": float(x), "y": float(y),
            "radius": float(radius), "ships": float(ships),
            "production": float(prod),
            "r_sun": math.hypot(float(x) - 50.0, float(y) - 50.0)
        }
        planets[planet["id"]] = planet
        if planet["owner"] == player:
            my_planets.append(planet)
        elif planet["owner"] == -1:
            neutral_planets.append(planet)
        else:
            enemy_planets.append(planet)
    
    if not my_planets:
        return moves
    
    # ==================== ORBIT DETECTION ====================
    if not hasattr(agent, "orbiting"):
        agent.orbiting = set()
        for pid, p in planets.items():
            if 12.0 < p["r_sun"] < 40.0:
                agent.orbiting.add(pid)
    orbiting = agent.orbiting
    
    # ==================== PHYSICS HELPERS ====================
    def predict_pos(pid, t):
        p = planets[pid]
        if pid in orbiting:
            a0 = math.atan2(p["y"] - 50.0, p["x"] - 50.0)
            a = a0 + ang_vel * t
            return (50.0 + p["r_sun"] * math.cos(a), 50.0 + p["r_sun"] * math.sin(a))
        return (p["x"], p["y"])
    
    def hits_sun(x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        l2 = dx*dx + dy*dy
        if l2 < 1e-9:
            return math.hypot(x1 - 50.0, y1 - 50.0) < 10.5
        t = max(0.0, min(1.0, ((50.0 - x1)*dx + (50.0 - y1)*dy) / l2))
        return math.hypot(x1 + t*dx - 50.0, y1 + t*dy - 50.0) < 10.5
    
    def intercept(sx, sy, tid, n_ships, max_t=55):
        v = get_fleet_speed(n_ships)
        if v < 0.1:
            return None
        
        # Binary search for optimal interception time
        lo, hi = 0.2, max_t
        best_err, best_t = float('inf'), None
        for _ in range(24):
            mid = (lo + hi) / 2.0
            tx, ty = predict_pos(tid, mid)
            d = math.hypot(tx - sx, ty - sy)
            err = v * mid - d
            if abs(err) < best_err:
                best_err = abs(err)
                best_t = mid
            if err > 0:
                hi = mid
            else:
                lo = mid
        
        if best_t is None or best_err > 1.5:
            return None
        
        tx, ty = predict_pos(tid, best_t)
        if hits_sun(sx, sy, tx, ty):
            return None
        
        return math.atan2(ty - sy, tx - sx), best_t
    
    # ==================== THREAT ASSESSMENT ====================
    incoming_enemy = defaultdict(float)
    for f in fleets_raw:
        fid, owner, fx, fy, fangle, from_pid, fships = f
        if int(owner) == player or int(owner) == -1:
            continue
        
        # Fast raycast to estimate target
        best_pid, best_t = None, float('inf')
        for pid, p in planets.items():
            dx = p["x"] - fx
            dy = p["y"] - fy
            proj = dx * math.cos(fangle) + dy * math.sin(fangle)
            if proj < 0:
                continue
            perp = abs(dx * math.sin(fangle) - dy * math.cos(fangle))
            if perp < p["radius"] + 2.0:
                t = proj / get_fleet_speed(int(fships))
                if t < best_t:
                    best_t, best_pid = t, pid
        if best_pid is not None:
            incoming_enemy[best_pid] += float(fships)
    
    # ==================== AVAILABLE SHIPS CALCULATION ====================
    # Minimal defense: only keep what is needed to survive known threats
    threatened = {}
    for p in my_planets:
        pid = p["id"]
        threat = incoming_enemy.get(pid, 0.0)
        if threat > 0:
            # Keep enough to absorb threat + small margin
            keep = int(threat) + 2
        else:
            # Non-threatened planets keep almost nothing (5% or 3 ships)
            keep = min(3, int(p["ships"] * 0.05))
        threatened[pid] = keep
    
    available = {}
    for p in my_planets:
        pid = p["id"]
        keep = threatened.get(pid, 0)
        available[pid] = max(0, int(p["ships"]) - keep)
    
    # ==================== PRODUCTION-OBSESSED SCORING ====================
    def target_score(src, tgt, eta, ships_needed):
        """
        Production is KING. 
        Score = production^2.5 * owner_bonus / (eta^1.2 * ships_needed^0.6)
        """
        prod = tgt["production"]
        if tgt["owner"] == -1:
            owner_bonus = 1.1
        else:
            owner_bonus = 1.4  # Stealing enemy production is extremely valuable
        
        # Production exponent > 2 makes high-production planets irresistible
        raw_value = (prod ** 2.5) * owner_bonus
        
        # Time penalty: we want fast returns
        time_penalty = (eta + 1.0) ** 1.2
        
        # Cost penalty: but not too harsh (we're willing to pay for production)
        cost_penalty = (ships_needed + 1.0) ** 0.6
        
        # Distance modifiers
        dist = math.hypot(src["x"] - tgt["x"], src["y"] - tgt["y"])
        dist_mod = 1.0
        if dist < 12:
            dist_mod = 1.3  # Very close targets are great early game
        elif dist < 20:
            dist_mod = 1.15
        elif dist > 35:
            dist_mod = 0.75  # Far targets penalized unless high production
        
        # Speed bonus: large fleets move faster, making distant high-prod viable
        return raw_value * dist_mod / (time_penalty * cost_penalty)
    
    # ==================== GENERATE CANDIDATE ACTIONS ====================
    actions = []
    
    # Sort sources by production (high-prod sources act first - they regenerate faster)
    sources = sorted(my_planets, key=lambda p: p["production"], reverse=True)
    
    for src in sources:
        sid = src["id"]
        avail = available[sid]
        if avail < 5:
            continue
        
        for tgt in list(planets.values()):
            if tgt["owner"] == player:
                continue
            
            best_for_tgt = None
            
            # Test multiple fleet sizes to optimize speed vs cost tradeoff
            # Larger fleets = faster travel = earlier production gain
            test_sizes = sorted(set([
                min(avail, 8), min(avail, 15), min(avail, 25),
                min(avail, 40), min(avail, 70), min(avail, 100), avail
            ]), reverse=True)
            
            for size in test_sizes:
                if size < 5 or size > avail:
                    continue
                
                result = intercept(src["x"], src["y"], tgt["id"], size)
                if result is None:
                    continue
                angle, eta = result
                
                # Calculate exact ships needed at arrival
                if tgt["owner"] == -1:
                    needed = int(tgt["ships"]) + 1
                else:
                    needed = int(tgt["ships"]) + int(tgt["production"]) * int(math.ceil(eta)) + 1
                
                if size < needed:
                    continue
                
                score = target_score(src, tgt, eta, needed)
                
                # Slight penalty for oversending (efficiency matters)
                oversend = max(0, size - needed)
                score -= oversend * 0.015
                
                if best_for_tgt is None or score > best_for_tgt[0]:
                    best_for_tgt = (score, angle, eta, size, needed, tgt["id"])
            
            if best_for_tgt:
                actions.append((
                    best_for_tgt[0],      # score
                    sid,                  # source id
                    best_for_tgt[1],      # angle
                    best_for_tgt[2],      # eta
                    best_for_tgt[3],      # fleet size
                    best_for_tgt[4],      # needed
                    best_for_tgt[5],      # target id
                    src,                  # source object
                    planets[best_for_tgt[5]]  # target object
                ))
    
    # Sort all actions globally by score
    actions.sort(reverse=True)
    
    # ==================== COMMIT SOLO CAPTURES ====================
    committed = defaultdict(int)
    targeted = set()
    
    for score, sid, angle, eta, size, needed, tid, src, tgt in actions:
        if tid in targeted:
            continue
        
        avail = available[sid] - committed[sid]
        if avail < 5:
            continue
        
        # Determine optimal send amount
        # For close targets: send exact needed + 1
        # For far targets: larger fleet = much faster, so send more if speed gain is worth it
        raw_dist = math.hypot(src["x"] - tgt["x"], src["y"] - tgt["y"])
        
        if raw_dist < 15:
            send = min(avail, needed + 1)
        elif raw_dist < 25:
            send = min(avail, max(needed + 1, int(size * 0.8)))
        else:
            # Distant high-prod: use bigger fleet for speed
            send = min(avail, max(needed + 1, size))
        
        # Re-aim with exact ship count
        result = intercept(src["x"], src["y"], tid, send)
        if result is None:
            continue
        angle, eta = result
        
        # Recalculate needed at new ETA
        if tgt["owner"] == -1:
            needed_now = int(tgt["ships"]) + 1
        else:
            needed_now = int(tgt["ships"]) + int(tgt["production"]) * int(math.ceil(eta)) + 1
        
        if send < needed_now:
            continue
        
        moves.append([sid, float(angle), int(send)])
        committed[sid] += send
        targeted.add(tid)
    
    # ==================== COALITION CAPTURES (High-Value Targets) ====================
    # For remaining high-production targets (prod >= 3), try 2-source coalition
    remaining_high = [p for p in planets.values()
                      if p["id"] not in targeted 
                      and p["production"] >= 3 
                      and p["owner"] != player]
    
    for tgt in remaining_high:
        coalition_sources = []
        for src in my_planets:
            sid = src["id"]
            avail = available[sid] - committed[sid]
            if avail < 5:
                continue
            
            result = intercept(src["x"], src["y"], tgt["id"], avail)
            if result is None:
                continue
            angle, eta = result
            coalition_sources.append((eta, sid, avail, angle, src))
        
        if len(coalition_sources) < 2:
            continue
        
        coalition_sources.sort()  # Sort by ETA
        
        # Try best pair with similar arrival times
        for i in range(len(coalition_sources)):
            for j in range(i + 1, len(coalition_sources)):
                eta1, sid1, avail1, ang1, src1 = coalition_sources[i]
                eta2, sid2, avail2, ang2, src2 = coalition_sources[j]
                
                # Arrivals must be nearly simultaneous (within 2 turns)
                if abs(eta1 - eta2) > 2:
                    continue
                
                max_eta = max(eta1, eta2)
                if tgt["owner"] == -1:
                    needed = int(tgt["ships"]) + 1
                else:
                    needed = int(tgt["ships"]) + int(tgt["production"]) * int(math.ceil(max_eta)) + 1
                
                if avail1 + avail2 < needed:
                    continue
                
                # Split proportionally, minimum 5 each
                total_avail = avail1 + avail2
                s1 = min(avail1, max(5, int(needed * avail1 / total_avail)))
                s2 = min(avail2, max(5, needed - s1))
                
                if s1 + s2 < needed:
                    continue
                
                # Re-aim with exact amounts
                r1 = intercept(src1["x"], src1["y"], tgt["id"], s1)
                r2 = intercept(src2["x"], src2["y"], tgt["id"], s2)
                if r1 is None or r2 is None:
                    continue
                
                moves.append([sid1, float(r1[0]), int(s1)])
                moves.append([sid2, float(r2[0]), int(s2)])
                committed[sid1] += s1
                committed[sid2] += s2
                targeted.add(tgt["id"])
                break
            if tgt["id"] in targeted:
                break
    
    # ==================== HUB REINFORCEMENT ====================
    # Feed low-production planets to highest-production hub
    # This creates a "super planet" that can launch massive, fast fleets
    if len(moves) < 6:
        my_by_prod = sorted(my_planets, key=lambda p: (p["production"], p["ships"]), reverse=True)
        if len(my_by_prod) >= 2:
            hub = my_by_prod[0]
            for src in my_by_prod[1:]:
                sid = src["id"]
                avail = available[sid] - committed[sid]
                if avail < 10:
                    continue
                
                # Send 35% of available to hub
                send = int(avail * 0.35)
                if send < 8:
                    continue
                
                result = intercept(src["x"], src["y"], hub["id"], send)
                if result is None:
                    continue
                angle, eta = result
                
                # Verify path
                hx, hy = predict_pos(hub["id"], eta)
                if hits_sun(src["x"], src["y"], hx, hy):
                    continue
                
                moves.append([sid, float(angle), int(send)])
                committed[sid] += send
                if len(moves) >= 10:
                    break
    
    return moves