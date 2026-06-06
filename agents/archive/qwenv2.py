import math

class Planet:
    def __init__(self, data):
        self.id = data[0]
        self.owner = data[1]
        self.x = data[2]
        self.y = data[3]
        self.radius = data[4]
        self.ships = data[5]
        self.production = data[6]
        self.r = math.hypot(self.x - 50, self.y - 50)
        self.theta = math.atan2(self.y - 50, self.x - 50)
        self.is_orbiting = False

class Fleet:
    def __init__(self, data):
        self.id = data[0]
        self.owner = data[1]
        self.x = data[2]
        self.y = data[3]
        self.angle = data[4]
        self.from_planet_id = data[5]
        self.ships = data[6]

def get_fleet_speed(ships: int) -> float:
    if ships <= 1: 
        return 1.0
    return 1.0 + (6.0 - 1.0) * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5

def agent(obs):
    # Persistent state tracking across turns
    if not hasattr(agent, "turn"):
        agent.turn = 0
        agent.planet_is_orbiting = {}
        agent.prev_positions = {}
        
    # Safe parsing for dictionary or object observation formats
    player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
    ang_vel = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else getattr(obs, "angular_velocity", 0.0)
    
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else getattr(obs, "planets", [])
    raw_fleets = obs.get("fleets", []) if isinstance(obs, dict) else getattr(obs, "fleets", [])
    
    planets = []
    for data in raw_planets:
        p = Planet(data)
        if p.id in agent.prev_positions:
            px, py = agent.prev_positions[p.id]
            if math.hypot(p.x - px, p.y - py) > 0.001:
                agent.planet_is_orbiting[p.id] = True
            else:
                agent.planet_is_orbiting[p.id] = False
        else:
            # Turn 0 Fallback: Assume inner planets orbit if within radius 35 and angular velocity exists
            if abs(ang_vel) > 1e-6 and p.r < 35.0:
                agent.planet_is_orbiting[p.id] = True
            else:
                agent.planet_is_orbiting[p.id] = False
        agent.prev_positions[p.id] = (p.x, p.y)
        p.is_orbiting = agent.planet_is_orbiting.get(p.id, False)
        planets.append(p)
        
    fleets = [Fleet(data) for data in raw_fleets]
    planet_dict = {p.id: p for p in planets}
    
    # Mathematical Position Prediction
    def predict_pos(pid, t):
        if agent.planet_is_orbiting.get(pid, False):
            p = planet_dict[pid]
            theta = p.theta + ang_vel * t
            return 50 + p.r * math.cos(theta), 50 + p.r * math.sin(theta)
        else:
            p = planet_dict[pid]
            return p.x, p.y

    # Fleet Destination Interception
    def predict_fleet_dest(fleet):
        v = get_fleet_speed(fleet.ships)
        vx = v * math.cos(fleet.angle)
        vy = v * math.sin(fleet.angle)
        
        for t in range(1, 150):
            fx = fleet.x + vx * t
            fy = fleet.y + vy * t
            
            if math.hypot(fx - 50, fy - 50) < 10.0:
                return None # Destroyed by the Sun
                
            for p in planets:
                if p.id == fleet.from_planet_id: continue
                px, py = predict_pos(p.id, t)
                
                if math.hypot(fx - px, fy - py) <= p.radius + 1.0:
                    return (p.id, float(t))
        return None

    # Precompute Incoming Fleets
    incoming = {p.id: [] for p in planets}
    for f in fleets:
        dest_info = predict_fleet_dest(f)
        if dest_info:
            dest_pid, arr_t = dest_info
            if dest_pid in incoming:
                incoming[dest_pid].append((arr_t, f.owner, f.ships))
                
    # Binary Search for Exact Arrival Time
    def calc_arrival_time(p_src, p_dest, ships):
        v = get_fleet_speed(ships)
        low, high = 0.0, 200.0
        for _ in range(30):
            mid = (low + high) / 2
            px, py = predict_pos(p_dest.id, mid)
            d = math.hypot(p_src.x - px, p_src.y - py)
            if v * mid < d: low = mid
            else: high = mid
        return (low + high) / 2

    # Exact Line-Segment to Circle Intersection (Sun Collision)
    def intersects_sun(x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        fx, fy = x1 - 50, y1 - 50
        a = dx*dx + dy*dy
        if a == 0: return False
        b = 2 * (fx*dx + fy*dy)
        c = fx*fx + fy*fy - 100.0
        disc = b*b - 4*a*c
        if disc < 0: return False
        disc = math.sqrt(disc)
        t1 = (-b - disc) / (2*a)
        t2 = (-b + disc) / (2*a)
        return t1 <= 1.0 and t2 >= 0.0

    # Threat Level Calculation (Defense Requirement)
    def get_threat_level(p):
        events = [(arr_t, owner, f_ships) for arr_t, owner, f_ships in incoming[p.id]]
        events.sort(key=lambda x: x[0])
        
        curr = p.ships
        last_t = 0
        max_deficit = 0
        
        for arr_t, owner, f_ships in events:
            curr += (arr_t - last_t) * p.production
            last_t = arr_t
            if owner == player or (owner == -1 and p.owner == player):
                curr += f_ships
            else:
                curr -= f_ships
                if curr < 0:
                    deficit = -curr + 1
                    if deficit > max_deficit: max_deficit = deficit
                    curr = 0
        return max_deficit

    # Garrison Simulation for Attack Targeting
    def get_enemy_ships_at(p_dest, t_arrival):
        events = [(arr_t, owner, f_ships) for arr_t, owner, f_ships in incoming[p_dest.id] if arr_t <= t_arrival]
        events.sort(key=lambda x: x[0])
        
        curr = p_dest.ships
        last_t = 0
        captured = False
        
        for arr_t, owner, f_ships in events:
            if not captured:
                curr += (arr_t - last_t) * p_dest.production
            if owner == player:
                curr -= f_ships
                if curr < 0:
                    captured = True
                    curr = 0
            else:
                if not captured:
                    curr += f_ships
            last_t = arr_t
            
        if captured: return 0
        curr += (t_arrival - last_t) * p_dest.production
        return max(0, curr)
        
    moves = []
    my_planets = [p for p in planets if p.owner == player]
    
    # Advanced Target Selection and Momentum Strategy
    for p_src in my_planets:
        threat = get_threat_level(p_src)
        max_send = p_src.ships - threat
        if max_send <= 0: continue # Preserve ships for defense
        
        best_score = -1.0
        best_action = None
        
        for p_dest in planets:
            if p_dest.id == p_src.id: continue
            
            # Binary Search for Minimum Ships Required (ROI Efficiency)
            low, high = 1, max_send
            min_S = None
            
            while low <= high:
                mid = (low + high) // 2
                t = calc_arrival_time(p_src, p_dest, mid)
                px, py = predict_pos(p_dest.id, t)
                
                if intersects_sun(p_src.x, p_src.y, px, py):
                    low = mid + 1
                    continue
                    
                if p_dest.owner != player:
                    req = max(0, get_enemy_ships_at(p_dest, t)) + 1
                else:
                    req = get_threat_level(p_dest)
                    if req == 0: 
                        req = float('inf') # Safe planet, don't reinforce
                    
                if mid >= req:
                    min_S = mid
                    high = mid - 1
                else:
                    low = mid + 1
                    
            if min_S is not None:
                if p_dest.owner != player:
                    score = p_dest.production / min_S
                else:
                    score = (p_dest.production + 10.0) / min_S
                    
                if score > best_score:
                    best_score = score
                    best_action = (p_dest.id, min_S)
                    
        # Fallback: Consolidate Forces to Closest Safe Friendly Planet
        if best_action is None and max_send > 0:
            friends = []
            for p_friend in my_planets:
                if p_friend.id == p_src.id: continue
                t = calc_arrival_time(p_src, p_friend, max_send)
                px, py = predict_pos(p_friend.id, t)
                if not intersects_sun(p_src.x, p_src.y, px, py):
                    d = math.hypot(p_src.x - p_friend.x, p_src.y - p_friend.y)
                    friends.append((d, p_friend.id))
            
            if friends:
                friends.sort(key=lambda x: x[0])
                best_action = (friends[0][1], max_send)
                
        if best_action:
            dest_id, ships = best_action
            t = calc_arrival_time(p_src, planet_dict[dest_id], ships)
            px, py = predict_pos(dest_id, t)
            angle = math.atan2(py - p_src.y, px - p_src.x)
            moves.append([p_src.id, angle, ships])
            
    agent.turn += 1
    return moves