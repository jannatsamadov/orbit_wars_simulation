import math

def get_fleet_speed(ships: int) -> float:
    """Calculate fleet speed based on ship count using the official formula."""
    if ships <= 1:
        return 1.0
    return 1.0 + 5.0 * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5

def agent(obs):
    # ==================== OBSERVATION PARSING ====================
    if isinstance(obs, dict):
        player = obs.get("player", 0)
        angular_velocity = obs.get("angular_velocity", 0.0)
        raw_planets = obs.get("planets", [])
        raw_fleets = obs.get("fleets", [])
    else:
        player = getattr(obs, "player", 0)
        angular_velocity = getattr(obs, "angular_velocity", 0.0)
        raw_planets = getattr(obs, "planets", [])
        raw_fleets = getattr(obs, "fleets", [])
    
    # ==================== PERSISTENT STATE ====================
    if not hasattr(agent, "state"):
        agent.state = {
            "turn": 0,
            "planet_history": {},
        }
    agent.state["turn"] += 1
    turn = agent.state["turn"]
    
    # ==================== PARSE PLANETS ====================
    planets = {}
    my_planets = []
    enemy_planets = []
    neutral_planets = []
    
    for p in raw_planets:
        pid, owner, x, y, radius, ships, production = p
        planet = {
            "id": int(pid),
            "owner": int(owner),
            "x": float(x),
            "y": float(y),
            "radius": float(radius),
            "ships": float(ships),
            "production": float(production),
            "dist_sun": math.hypot(float(x) - 50.0, float(y) - 50.0)
        }
        planets[int(pid)] = planet
        
        if int(owner) == player:
            my_planets.append(planet)
        elif int(owner) == -1:
            neutral_planets.append(planet)
        else:
            enemy_planets.append(planet)
    
    # Update position history to detect orbiting planets
    for pid, p in planets.items():
        if pid not in agent.state["planet_history"]:
            agent.state["planet_history"][pid] = []
        agent.state["planet_history"][pid].append((p["x"], p["y"]))
        if len(agent.state["planet_history"][pid]) > 5:
            agent.state["planet_history"][pid].pop(0)
    
    # Detect which planets are orbiting (inner planets)
    orbiting_ids = set()
    for pid, hist in agent.state["planet_history"].items():
        if len(hist) >= 2:
            angles = []
            for x, y in hist:
                a = math.atan2(y - 50.0, x - 50.0)
                if a < 0:
                    a += 2 * math.pi
                angles.append(a)
            
            valid = True
            for i in range(1, len(angles)):
                da = angles[i] - angles[i-1]
                while da > math.pi:
                    da -= 2 * math.pi
                while da < -math.pi:
                    da += 2 * math.pi
                # Counter-clockwise orbit must show small positive angular change
                if not (0.0001 < da < angular_velocity * 2.0 + 0.2):
                    valid = False
                    break
            if valid:
                orbiting_ids.add(pid)
    
    # First-turn fallback: assume planets near the sun (but outside it) are orbiting
    if turn <= 2:
        for pid, p in planets.items():
            if 12.0 < p["dist_sun"] < 40.0:
                orbiting_ids.add(pid)
    
    # ==================== PARSE FLEETS ====================
    my_fleets = []
    enemy_fleets = []
    
    for f in raw_fleets:
        fid, owner, x, y, angle, from_pid, ships = f
        fleet = {
            "x": float(x),
            "y": float(y),
            "angle": float(angle),
            "from": int(from_pid),
            "ships": float(ships)
        }
        if int(owner) == player:
            my_fleets.append(fleet)
        else:
            enemy_fleets.append(fleet)
    
    # Estimate fleet targets by ray-casting along trajectory
    def estimate_fleet_target(fleet, max_dist=60.0):
        fx, fy, fa = fleet["x"], fleet["y"], fleet["angle"]
        for dist in [2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, max_dist]:
            px = fx + math.cos(fa) * dist
            py = fy + math.sin(fa) * dist
            for pid, p in planets.items():
                if math.hypot(px - p["x"], py - p["y"]) <= p["radius"] + 2.0:
                    return pid
        return None
    
    incoming_friendly = {}
    incoming_enemy = {}
    
    for mf in my_fleets:
        tid = estimate_fleet_target(mf)
        if tid is not None:
            incoming_friendly[tid] = incoming_friendly.get(tid, 0.0) + mf["ships"]
    
    for ef in enemy_fleets:
        tid = estimate_fleet_target(ef)
        if tid is not None:
            incoming_enemy[tid] = incoming_enemy.get(tid, 0.0) + ef["ships"]
    
    # ==================== PHYSICS HELPERS ====================
    def predict_pos(pid, t):
        """Predict planet position at time t turns in the future."""
        p = planets[pid]
        if pid in orbiting_ids:
            r = p["dist_sun"]
            a0 = math.atan2(p["y"] - 50.0, p["x"] - 50.0)
            a = a0 + angular_velocity * t
            return (50.0 + r * math.cos(a), 50.0 + r * math.sin(a))
        return (p["x"], p["y"])
    
    def path_hits_sun(x1, y1, x2, y2, sun_x=50.0, sun_y=50.0, sun_r=10.0):
        """Return True if the straight-line path intersects the Sun."""
        dx, dy = x2 - x1, y2 - y1
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return math.hypot(x1 - sun_x, y1 - sun_y) < sun_r
        
        t = ((sun_x - x1) * dx + (sun_y - y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy
        return math.hypot(closest_x - sun_x, closest_y - sun_y) < sun_r
    
    def solve_interception(sx, sy, tid, fleet_size, max_t=50.0):
        """Numerically solve for launch angle and travel time to intercept a planet."""
        v = get_fleet_speed(fleet_size)
        if v < 0.1:
            return None, float('inf')
        
        best_t, best_err = None, float('inf')
        
        # Coarse search over time horizon
        for i in range(1, int(max_t * 2) + 1):
            t = i * 0.5
            tx, ty = predict_pos(tid, t)
            dist = math.hypot(tx - sx, ty - sy)
            err = abs(v * t - dist)
            if err < best_err:
                best_err = err
                best_t = t
        
        # Fine refinement around best candidate
        if best_t is not None:
            for delta in [-0.4, -0.3, -0.2, -0.15, -0.1, -0.05, 0.0,
                          0.05, 0.1, 0.15, 0.2, 0.3, 0.4]:
                t = max(0.1, best_t + delta)
                tx, ty = predict_pos(tid, t)
                dist = math.hypot(tx - sx, ty - sy)
                err = abs(v * t - dist)
                if err < best_err:
                    best_err = err
                    best_t = t
        
        if best_t is None or best_err > 2.5:
            return None, float('inf')
        
        tx, ty = predict_pos(tid, best_t)
        if path_hits_sun(sx, sy, tx, ty):
            return None, float('inf')
        
        angle = math.atan2(ty - sy, tx - sx)
        return angle, best_t
    
    # ==================== STRATEGIC ENGINE ====================
    moves = []
    if not my_planets:
        return moves
    
    # Ships already committed from each planet this turn
    committed = {p["id"]: 0 for p in my_planets}
    
    # Threat assessment for defense
    threat = {}
    for p in my_planets:
        pid = p["id"]
        threat[pid] = incoming_enemy.get(pid, 0.0)
    
    # Build target priority list
    targets = []
    for p in planets.values():
        if p["owner"] == player:
            continue
        
        pid = p["id"]
        eff_defense = p["ships"]
        
        if p["owner"] == -1:
            # Neutral: subtract our incoming fleets
            eff_defense -= incoming_friendly.get(pid, 0.0)
        else:
            # Enemy: our fleets help wear down defense
            eff_defense -= incoming_friendly.get(pid, 0.0)
        
        eff_defense = max(0.0, eff_defense)
        
        # Strategic value scoring
        prod = p["production"]
        value = prod * 35.0 + 20.0
        if p["owner"] == -1:
            value += 15.0  # Neutral planets are easier captures
        
        # Proximity bonus: prefer planets close to our empire
        min_dist = min(math.hypot(p["x"] - mp["x"], p["y"] - mp["y"]) for mp in my_planets)
        value += 40.0 / (min_dist + 1.0)
        
        targets.append((p, eff_defense, value, min_dist))
    
    # Sort by value-to-defense ratio, penalized slightly by distance
    targets.sort(key=lambda x: (x[2] / max(x[1], 0.5)) - x[3] * 0.08, reverse=True)
    
    # -------------------- OFFENSIVE MOVES --------------------
    for target, eff_defense, value, min_dist in targets:
        tid = target["id"]
        
        # Skip neutrals already being captured by sufficient force
        if target["owner"] == -1 and incoming_friendly.get(tid, 0.0) > target["ships"]:
            continue
        
        best_score = -1e9
        best_move = None
        
        # Evaluate each source planet (prioritize high-production sources)
        for source in sorted(my_planets, key=lambda p: p["production"], reverse=True):
            sid = source["id"]
            available = source["ships"] - committed[sid]
            
            if available < 1:
                continue
            
            # Reserve ships if this planet is under attack
            local_threat = threat.get(sid, 0.0)
            if local_threat > source["ships"] * 0.5:
                reserve = int(local_threat * 0.7)
                available = max(0, available - reserve)
                if available < 1:
                    continue
            
            # Minimum ships needed to capture
            ships_needed = int(eff_defense + 1.0)
            if ships_needed < 1:
                ships_needed = 1
            
            # Candidate fleet sizes: exact, slight overkill, and speed-optimized large fleets
            candidates = set()
            if ships_needed <= available:
                candidates.add(ships_needed)
                candidates.add(int(min(available, ships_needed * 1.2)))
                candidates.add(int(min(available, ships_needed * 1.5)))
            
            # For distant targets, larger fleets move disproportionately faster
            if min_dist > 20:
                candidates.add(int(min(available, max(ships_needed, 40))))
                candidates.add(int(min(available, max(ships_needed, 80))))
            
            for fleet_size in sorted(candidates, reverse=True):
                if fleet_size < 1 or fleet_size > available:
                    continue
                
                angle, t = solve_interception(source["x"], source["y"], tid, fleet_size)
                if angle is None:
                    continue
                
                # Score = (value - overkill_penalty + speed_bonus) / (time + 1)
                overkill_penalty = max(0, fleet_size - ships_needed) * 0.25
                speed_bonus = 3.0 if fleet_size >= 40 else 0.0
                score = (value + speed_bonus - overkill_penalty) / (t + 1.0)
                
                # Penalize stripping a threatened source
                if local_threat > 0:
                    score *= 0.85
                
                # Boost for stealing high-production enemy planets
                if target["owner"] != -1 and prod >= 3:
                    score *= 1.2
                
                if score > best_score:
                    best_score = score
                    best_move = (sid, angle, fleet_size)
        
        if best_move:
            sid, angle, fleet_size = best_move
            moves.append([sid, angle, fleet_size])
            committed[sid] += fleet_size
            incoming_friendly[tid] = incoming_friendly.get(tid, 0.0) + fleet_size
    
    # -------------------- DEFENSIVE REINFORCEMENTS --------------------
    # Identify threatened planets that need help
    threatened = []
    for p in my_planets:
        pid = p["id"]
        remaining = p["ships"] - committed[pid]
        if threat.get(pid, 0.0) > remaining:
            threatened.append(p)
    
    safe_sources = [p for p in my_planets if threat.get(p["id"], 0.0) < p["ships"] * 0.3]
    
    for target in threatened:
        tid = target["id"]
        deficit = int(threat.get(tid, 0.0) - (target["ships"] - committed[tid]) + 5)
        if deficit <= 0:
            continue
        
        for source in safe_sources:
            sid = source["id"]
            if sid == tid:
                continue
            
            available = source["ships"] - committed[sid]
            if available <= 0:
                continue
            
            # Send larger reinforcements for faster travel
            send = min(available, deficit)
            if send < 25 and available >= 25:
                send = min(available, 25)
            
            angle, t = solve_interception(source["x"], source["y"], tid, send)
            if angle is not None:
                moves.append([sid, angle, send])
                committed[sid] += send
                deficit -= send
                if deficit <= 0:
                    break
    
    return moves