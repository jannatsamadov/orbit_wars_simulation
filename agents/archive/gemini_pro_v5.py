import math
from collections import defaultdict, namedtuple

# ==============================================================================
# 1. KINEMATIC ENGINE & HELPER CLASSES
# ==============================================================================
BOARD_SIZE = 100.0
SUN_X, SUN_Y, SUN_RADIUS = 50.0, 50.0, 10.0

Planet = namedtuple("Planet", ["id", "owner", "x", "y", "radius", "ships", "production"])
Fleet = namedtuple("Fleet", ["id", "owner", "x", "y", "angle", "from_planet_id", "ships"])

def get_fleet_speed(ships: int) -> float:
    if ships <= 1: return 1.0
    return min(6.0, 1.0 + 5.0 * (math.log(max(ships, 1)) / math.log(1000.0)) ** 1.5)

def get_distance(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)

def is_sun_collision(sx, sy, tx, ty) -> bool:
    dx, dy = tx - sx, ty - sy
    l2 = dx * dx + dy * dy
    if l2 < 1e-9:
        return get_distance(sx, sy, SUN_X, SUN_Y) < SUN_RADIUS
    t = max(0.0, min(1.0, ((SUN_X - sx) * dx + (SUN_Y - sy) * dy) / l2))
    return get_distance(sx + t * dx, sy + t * dy, SUN_X, SUN_Y) < (SUN_RADIUS + 0.5)

def project_orbit(x, y, ang_vel, turns, is_orbital):
    if not is_orbital or ang_vel == 0.0:
        return x, y
    r = get_distance(x, y, SUN_X, SUN_Y)
    phase = math.atan2(y - SUN_Y, x - SUN_X) + ang_vel * turns
    return SUN_X + r * math.cos(phase), SUN_Y + r * math.sin(phase)

def calculate_interception(sx, sy, tx, ty, ang_vel, ships, is_orbital):
    speed = get_fleet_speed(ships)
    est_t = max(1.0, get_distance(sx, sy, tx, ty) / speed)
    
    for _ in range(5):
        px, py = project_orbit(tx, ty, ang_vel, est_t, is_orbital)
        est_t = max(1.0, get_distance(sx, sy, px, py) / speed)
        
    px, py = project_orbit(tx, ty, ang_vel, int(math.ceil(est_t)), is_orbital)
    
    if is_sun_collision(sx, sy, px, py):
        return None
    return math.atan2(py - sy, px - sx), int(math.ceil(est_t))

# ==============================================================================
# 2. STATE SIMULATOR (COMBAT & VULTURE ENGINE)
# ==============================================================================
def simulate_planet_timeline(target, arrivals, max_horizon=50):
    """
    Simulates the exact state of a planet turn-by-turn.
    Returns a timeline dictionary: turn -> (owner, ships)
    """
    timeline = {}
    by_turn = defaultdict(list)
    for eta, owner, ships in arrivals:
        if ships > 0:
            by_turn[eta].append((owner, ships))
            
    current_owner = target.owner
    current_ships = float(target.ships)
    prod = int(target.production)
    
    for t in range(1, max_horizon + 1):
        if current_owner != -1:
            current_ships += prod
            
        if t in by_turn:
            forces = defaultdict(float)
            for o, s in by_turn[t]:
                forces[o] += s
                
            sorted_forces = sorted(forces.items(), key=lambda x: -x[1])
            top_o, top_s = sorted_forces[0]
            
            survivor_s = top_s
            survivor_o = top_o
            if len(sorted_forces) > 1:
                if top_s == sorted_forces[1][1]:
                    survivor_s, survivor_o = 0.0, -1
                else:
                    survivor_s = top_s - sorted_forces[1][1]
                    
            if survivor_s > 0:
                if current_owner == survivor_o:
                    current_ships += survivor_s
                else:
                    current_ships -= survivor_s
                    if current_ships < 0:
                        current_owner = survivor_o
                        current_ships = -current_ships
                        
        timeline[t] = (current_owner, max(0, int(current_ships)))
        
    return timeline

# ==============================================================================
# 3. CORE AGENT LOGIC
# ==============================================================================
def agent(obs) -> list:
    player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
    step = obs.get("step", 0) if isinstance(obs, dict) else getattr(obs, "step", 0)
    ang_vel = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else getattr(obs, "angular_velocity", 0.0)
    
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else getattr(obs, "planets", [])
    raw_fleets = obs.get("fleets", []) if isinstance(obs, dict) else getattr(obs, "fleets", [])
    raw_init = obs.get("initial_planets", []) if isinstance(obs, dict) else getattr(obs, "initial_planets", [])
    
    planets = [Planet(*p) for p in raw_planets]
    fleets = [Fleet(*f) for f in raw_fleets]
    init_planets = {Planet(*p).id: Planet(*p) for p in raw_init}
    
    my_planets = [p for p in planets if p.owner == player]
    if not my_planets: return []
    
    # Identify Game Mode (1v1 vs 4P FFA)
    active_players = set([p.owner for p in planets if p.owner != -1] + [f.owner for f in fleets])
    is_ffa = len(active_players) > 2
    
    # Map Arrivals for precise simulation
    arrivals_map = defaultdict(list)
    for f in fleets:
        speed = get_fleet_speed(f.ships)
        # Fast straight-line ETA approximation for arrival mapping
        for p in planets:
            init = init_planets.get(p.id)
            is_orbital = init is not None and get_distance(init.x, init.y, SUN_X, SUN_Y) + init.radius < 45.0
            eta = max(1, int(math.ceil(get_distance(f.x, f.y, p.x, p.y) / speed)))
            arrivals_map[p.id].append((eta, int(f.owner), int(f.ships)))

    moves = []
    committed_ships = defaultdict(int)
    targeted = set()

    # Calculate Frontlines (Distances to nearest enemy)
    enemy_planets = [p for p in planets if p.owner != player and p.owner != -1]
    frontline_dist = {}
    for mp in my_planets:
        min_d = float('inf')
        for ep in enemy_planets:
            d = get_distance(mp.x, mp.y, ep.x, ep.y)
            if d < min_d: min_d = d
        frontline_dist[mp.id] = min_d

    # --------------------------------------------------------------------------
    # PHASE 1: THE VULTURE (Scavenge wars)
    # --------------------------------------------------------------------------
    for target in planets:
        if target.id in targeted or target.owner == player: continue
        
        timeline = simulate_planet_timeline(target, arrivals_map.get(target.id, []))
        
        # Look for moments of weakness (flips or near-zero garrisons due to combat)
        vulture_turn = None
        vulture_garrison = None
        
        for t in range(1, 40):
            t_owner, t_ships = timeline.get(t, (target.owner, target.ships))
            # If the planet flips to an enemy, or is neutral but heavily damaged (< 15 ships)
            if t_owner != player and t_ships < 15:
                # We want to land EXACTLY at t + 1
                vulture_turn = t + 1
                vulture_garrison = t_ships
                break
                
        if vulture_turn:
            required = vulture_garrison + 3
            
            # Find the best source to snipe this
            for src in sorted(my_planets, key=lambda p: frontline_dist[p.id], reverse=True):
                avail = src.ships - committed_ships[src.id]
                if avail < required: continue
                
                is_orb = init_planets.get(target.id) is not None and get_distance(init_planets[target.id].x, init_planets[target.id].y, SUN_X, SUN_Y) + init_planets[target.id].radius < 45.0
                aim = calculate_interception(src.x, src.y, target.x, target.y, ang_vel, required, is_orb)
                
                if aim:
                    angle, travel_time = aim
                    if travel_time == vulture_turn:
                        moves.append([int(src.id), float(angle), int(required)])
                        committed_ships[src.id] += required
                        targeted.add(target.id)
                        break # Successfully sniped

    # --------------------------------------------------------------------------
    # PHASE 2: SAFE EXPANSION & ECO-TURTLING
    # --------------------------------------------------------------------------
    for src in sorted(my_planets, key=lambda p: p.ships, reverse=True):
        avail = src.ships - committed_ships[src.id]
        
        # Defense logic based on Game Mode
        is_frontline = frontline_dist[src.id] < 30.0
        if is_ffa:
            # 4P: Extreme caution. Hold high reserves on frontlines.
            reserve = int(src.production * 5) if is_frontline else int(src.production * 1)
        else:
            # 1v1: Aggressive. Minimum reserves.
            reserve = int(src.production * 2) if is_frontline else 0
            
        deployable = avail - reserve
        if deployable < 10: continue
        
        best_target = None
        best_score = -float('inf')
        best_action = None
        
        for target in planets:
            if target.owner == player or target.id in targeted: continue
            
            is_orb = init_planets.get(target.id) is not None and get_distance(init_planets[target.id].x, init_planets[target.id].y, SUN_X, SUN_Y) + init_planets[target.id].radius < 45.0
            aim = calculate_interception(src.x, src.y, target.x, target.y, ang_vel, deployable, is_orb)
            if not aim: continue
            angle, travel_t = aim
            
            timeline = simulate_planet_timeline(target, arrivals_map.get(target.id, []), max_horizon=travel_t)
            arr_owner, arr_ships = timeline.get(travel_t, (target.owner, target.ships))
            
            required = arr_ships + (4 if target.owner != -1 else 1)
            if required > deployable: continue
            
            # Risk Analysis
            distance_to_enemy = min([get_distance(target.x, target.y, ep.x, ep.y) for ep in enemy_planets] + [100.0])
            
            # In FFA, aggressively penalize attacking enemies directly in the early game.
            # Prioritize taking safe neutrals far away from enemies.
            if is_ffa and step < 150:
                if target.owner != -1: continue # Do not poke the bear early
                if distance_to_enemy < 20.0: continue # Do not expand into hot zones
                
            value = (target.production + 1.0) ** 2
            cost = max(1, required)
            time_penalty = float(travel_t)
            
            score = value / (cost * time_penalty)
            
            # 1v1 Aggression Bonus
            if not is_ffa and target.owner != -1:
                score *= 2.0
                
            if score > best_score:
                best_score = score
                best_target = target
                
                # Re-calculate exact speed for the required ships to avoid wandering
                exact_aim = calculate_interception(src.x, src.y, target.x, target.y, ang_vel, required, is_orb)
                if exact_aim:
                    best_action = (exact_aim[0], required)
                    
        if best_target and best_action:
            angle, req_ships = best_action
            moves.append([int(src.id), float(angle), int(req_ships)])
            committed_ships[src.id] += req_ships
            targeted.add(best_target.id)

    # --------------------------------------------------------------------------
    # PHASE 3: SUPPLY CHAIN (Backline -> Frontline Feeder)
    # --------------------------------------------------------------------------
    # Backline planets safely funnel surplus to the front to create massive defensive/offensive walls
    for src in my_planets:
        avail = src.ships - committed_ships[src.id]
        if frontline_dist[src.id] > 35.0 and avail > 20: # Deep backline
            feed_amount = int(avail * 0.5)
            
            # Find closest friendly frontline
            closest_front = None
            min_dist = float('inf')
            for mp in my_planets:
                if mp.id == src.id: continue
                if frontline_dist[mp.id] < 25.0: # Is a frontline
                    d = get_distance(src.x, src.y, mp.x, mp.y)
                    if d < min_dist:
                        min_dist = d
                        closest_front = mp
                        
            if closest_front:
                is_orb = init_planets.get(closest_front.id) is not None and get_distance(init_planets[closest_front.id].x, init_planets[closest_front.id].y, SUN_X, SUN_Y) + init_planets[closest_front.id].radius < 45.0
                aim = calculate_interception(src.x, src.y, closest_front.x, closest_front.y, ang_vel, feed_amount, is_orb)
                if aim:
                    angle, _ = aim
                    moves.append([int(src.id), float(angle), int(feed_amount)])
                    committed_ships[src.id] += feed_amount

    return moves