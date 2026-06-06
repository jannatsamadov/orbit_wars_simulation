import math
import time
from collections import defaultdict, namedtuple

# ==============================================================================
# KINETIC ENGINE CONSTANTS & MATHEMATICAL SETUP
# ==============================================================================
BOARD_SIZE = 100.0
SUN_X, SUN_Y, SUN_RADIUS = 50.0, 50.0, 10.0
SUN_SAFE_ZONE = 10.6  # Analytical boundary margin to scrape the sun safely
MAX_SPEED = 6.0
TOTAL_TURNS = 500

Planet = namedtuple("Planet", ["id", "owner", "x", "y", "radius", "ships", "production"])
Fleet = namedtuple("Fleet", ["id", "owner", "x", "y", "angle", "from_planet_id", "ships"])

# ==============================================================================
# HIGH-PRECISION KINEMATICS & ORBITAL SOLVERS
# ==============================================================================
def get_fleet_speed(ships: int) -> float:
    if ships <= 1: 
        return 1.0
    ratio = math.log(max(ships, 2)) / math.log(1000.0)
    return 1.0 + 5.0 * (max(0.0, min(1.0, ratio)) ** 1.5)

def get_distance(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)

def analytical_sun_collision(sx, sy, tx, ty) -> bool:
    """Uses vector projection to determine if the line segment intersects the sun's boundary."""
    dx, dy = tx - sx, ty - sy
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-9:
        return get_distance(sx, sy, SUN_X, SUN_Y) < SUN_RADIUS
    
    # Projection factor of sun center onto path vector
    t = ((SUN_X - sx) * dx + (SUN_Y - sy) * dy) / len_sq
    t = max(0.0, min(1.0, t))
    
    closest_x = sx + t * dx
    closest_y = sy + t * dy
    
    return get_distance(closest_x, closest_y, SUN_X, SUN_Y) < SUN_SAFE_ZONE

def project_orbital_position(planet, initial_planets, ang_vel, turns):
    init = initial_planets.get(planet.id)
    if init is None:
        return planet.x, planet.y
    r = get_distance(init.x, init.y, SUN_X, SUN_Y)
    if r + init.radius >= 50.0:  # Static planet boundary check
        return planet.x, planet.y
    
    current_phase = math.atan2(planet.y - SUN_Y, planet.x - SUN_X)
    future_phase = current_phase + ang_vel * turns
    return SUN_X + r * math.cos(future_phase), SUN_Y + r * math.sin(future_phase)

def precise_interception_solver(src, tgt, ships, initial_planets, ang_vel, max_horizon=60):
    """
    Advanced numeric solver with adaptive step-size tracking to find the exact 
    kinematic interception profile without floating point drift.
    """
    speed = get_fleet_speed(ships)
    sx, sy = src.x, src.y
    tx, ty = tgt.x, tgt.y
    
    # Initial linear guess
    estimated_turns = max(1.0, get_distance(sx, sy, tx, ty) / speed)
    
    for _ in range(8):
        px, py = project_orbital_position(tgt, initial_planets, ang_vel, estimated_turns)
        actual_dist = get_distance(sx, sy, px, py)
        next_turns = max(1.0, actual_dist / speed)
        if abs(next_turns - estimated_turns) < 0.01:
            estimated_turns = next_turns
            break
        estimated_turns = 0.5 * estimated_turns + 0.5 * next_turns
        
    final_turns = int(math.ceil(estimated_turns))
    if final_turns > max_horizon:
        return None
        
    px, py = project_orbital_position(tgt, initial_planets, ang_vel, final_turns)
    if analytical_sun_collision(sx, sy, px, py):
        return None
        
    return math.atan2(py - sy, px - sx), final_turns

def predict_fleet_landing(fleet, planets, initial_planets, ang_vel):
    """Traces an in-flight fleet analytical vector to spot its landing vector and ETA."""
    cos_a = math.cos(fleet.angle)
    sin_a = math.sin(fleet.angle)
    speed = get_fleet_speed(fleet.ships)
    
    best_target, best_eta = None, float("inf")
    
    for p in planets:
        init = initial_planets.get(p.id)
        is_static = init is None or (get_distance(init.x, init.y, SUN_X, SUN_Y) + init.radius >= 50.0)
        
        if is_static:
            dx = p.x - fleet.x
            dy = p.y - fleet.y
            projection = dx * cos_a + dy * sin_a
            if projection < 0: continue
            perp_sq = dx * dx + dy * dy - projection * projection
            if perp_sq < p.radius * p.radius:
                hit_d = projection - math.sqrt(p.radius * p.radius - perp_sq)
                eta = max(1, int(math.ceil(hit_d / speed)))
                if eta < best_eta:
                    best_eta, best_target = eta, p
        else:
            # Time-stepped lookahead for orbital sweep matching
            for t in range(1, 100):
                fx = fleet.x + cos_a * speed * t
                fy = fleet.y + sin_a * speed * t
                px, py = project_orbital_position(p, initial_planets, ang_vel, t)
                if get_distance(fx, fy, px, py) < p.radius:
                    if t < best_eta:
                        best_eta, best_target = t, p
                    break
                    
    return best_target, best_eta

# ==============================================================================
# STATE SIMULATOR & COMBAT ENGINE (FORWARD ROLLOUT)
# ==============================================================================
def simulate_node_state(target, arrival_turn, world):
    arrivals = world.arrivals_map.get(target.id, [])
    by_turn = defaultdict(list)
    for eta, owner, ships in arrivals:
        by_turn[eta].append((owner, ships))
        
    current_owner = target.owner
    current_garrison = float(target.ships)
    prod = int(target.production)
    
    for t in range(1, arrival_turn + 1):
        if current_owner != -1:
            current_garrison += prod
            
        turn_fleets = by_turn.get(t, [])
        if turn_fleets:
            owner_groups = defaultdict(int)
            for o, s in turn_fleets:
                owner_groups[o] += s
                
            sorted_groups = sorted(owner_groups.items(), key=lambda x: -x[1])
            top_owner, top_ships = sorted_groups[0]
            
            survivor_ships = top_ships
            survivor_owner = top_owner
            if len(sorted_groups) > 1:
                if top_ships == sorted_groups[1][1]:
                    survivor_ships = 0
                    survivor_owner = -1
                else:
                    survivor_ships = top_ships - sorted_groups[1][1]
                    
            if survivor_ships > 0:
                if current_owner == survivor_owner:
                    current_garrison += survivor_ships
                else:
                    current_garrison -= survivor_ships
                    if current_garrison < 0:
                        current_owner = survivor_owner
                        current_garrison = -current_garrison
                        
    return current_owner, max(0, int(current_garrison))

# ==============================================================================
# THE WORLD ARCHITECT (ENVIRONMENT WRAPPER)
# ==============================================================================
class WorldContext:
    def __init__(self, obs, step_counter):
        self.player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
        self.step = step_counter
        self.ang_vel = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else getattr(obs, "angular_velocity", 0.0)
        
        raw_planets = obs.get("planets", []) if isinstance(obs, dict) else getattr(obs, "planets", [])
        raw_fleets = obs.get("fleets", []) if isinstance(obs, dict) else getattr(obs, "fleets", [])
        raw_init = obs.get("initial_planets", []) if isinstance(obs, dict) else getattr(obs, "initial_planets", [])
        raw_comets = obs.get("comet_planet_ids", []) if isinstance(obs, dict) else getattr(obs, "comet_planet_ids", [])
        
        self.planets = [Planet(*p) for p in raw_planets]
        self.fleets = [Fleet(*f) for f in raw_fleets]
        self.initial_planets = {Planet(*p).id: Planet(*p) for p in raw_init}
        self.comet_ids = set(int(x) for x in raw_comets)
        
        self.my_planets = [p for p in self.planets if p.owner == self.player]
        self.hostile_planets = [p for p in self.planets if p.owner != self.player and p.owner != -1]
        
        # Build analytical arrival network map
        self.arrivals_map = defaultdict(list)
        for f in self.fleets:
            tgt, eta = predict_fleet_landing(f, self.planets, self.initial_planets, self.ang_vel)
            if tgt is not None:
                self.arrivals_map[tgt.id].append((eta, int(f.owner), int(f.ships)))

# ==============================================================================
# CORE EXECUTION AGENT
# ==============================================================================
_GLOBAL_STEP_TRACKER = 0

def agent(obs, config=None) -> list:
    global _GLOBAL_STEP_TRACKER
    obs_step = obs.get("step", 0) if isinstance(obs, dict) else getattr(obs, "step", 0)
    if obs_step == 0:
        _GLOBAL_STEP_TRACKER = 0
    _GLOBAL_STEP_TRACKER += 1
    
    world = WorldContext(obs, _GLOBAL_STEP_TRACKER)
    if not world.my_planets:
        return []
        
    moves = []
    allocated_garrisons = defaultdict(int)
    targeted_nodes = set()
    
    # --------------------------------------------------------------------------
    # STRATEGY 1: ASYMMETRIC "+1 TICK" TEMPORAL SNIPER MODULE
    # --------------------------------------------------------------------------
    # We analyze all hostile incoming fleets inside the world mapping structure.
    # If a heavy hostile fleet is going to flip a planet at turn T, we pre-aim
    # a fleet to hit that node precisely at turn T + 1 to instantly steal it.
    for target in world.planets:
        if target.id in world.comet_ids: continue
        
        arrivals = world.arrivals_map.get(target.id, [])
        if not arrivals: continue
        
        # Track when ownership changes occur natively
        for t_frame in sorted(set(arr[0] for arr in arrivals)):
            projected_owner, projected_ships = simulate_node_state(target, t_frame, world)
            
            # If the lookahead rollout predicts an enemy will capture it at this frame
            if projected_owner != world.player and projected_owner != -1:
                
                # Search for an optimal sniper source
                for src in sorted(world.my_planets, key=lambda p: p.ships, reverse=True):
                    avail = src.ships - allocated_garrisons[src.id]
                    if avail < 15: continue
                    
                    # Calculate required ships to overwrite the post-battle state at frame + 1
                    # Expected garrison right after combat is 'projected_ships'
                    required_snipers = projected_ships + 2
                    
                    # Kinematic calculation for interception profile
                    solver = precise_interception_solver(src, target, required_snipers, world.initial_planets, world.ang_vel)
                    if solver is None: continue
                    angle, turns = solver
                    
                    # ASYMMETRIC TIE-IN: Fire only if the flight time hits exactly on the frame + 1
                    if turns == t_frame + 1 and required_snipers <= avail:
                        moves.append([int(src.id), float(angle), int(required_snipers)])
                        allocated_garrisons[src.id] += required_snipers
                        targeted_nodes.add(target.id)
                        break
                        
    # --------------------------------------------------------------------------
    # STRATEGY 2: KINETIC VALUE SCORING & STAGED VANGUARD INJECTION
    # --------------------------------------------------------------------------
    # Rank expansion nodes by a compound weight index of cost efficiency, production capacity,
    # and threat profiles. Uses dynamic safety ceilings for localized reserves.
    my_total_ships = sum(p.ships for p in world.my_planets)
    is_late_game = world.step > 350
    
    for src in sorted(world.my_planets, key=lambda p: p.ships, reverse=True):
        avail = src.ships - allocated_garrisons[src.id]
        
        # Localized defensive reserve ceiling
        reserve_ceiling = int(src.production * 2.5) if not is_late_game else 5
        deployable = avail - reserve_ceiling
        if deployable < 10: continue
        
        best_node = None
        best_idx_score = -float("inf")
        best_profile = None # (angle, turns, ships_to_send)
        
        for target in world.planets:
            if target.id == src.id or target.owner == world.player: continue
            if target.id in world.comet_ids or target.id in targeted_nodes: continue
            
            # Analytical tracking loop up to 35 steps
            solver = precise_interception_solver(src, target, deployable, world.initial_planets, world.ang_vel, max_horizon=35)
            if solver is None: continue
            angle, turns = solver
            
            # Predict defender matrix state at landing interval
            _, landing_garrison = simulate_node_state(target, turns, world)
            required_force = landing_garrison + (5 if target.owner != -1 else 1)
            
            if required_force > deployable: continue
            
            # Asymmetric Weight Multiplier Matrix
            dist_factor = max(1.0, float(turns))
            prod_value = (target.production + 1.0) ** 2
            
            owner_multiplier = 1.0
            if target.owner == -1:
                owner_multiplier = 1.3  # Quick eco scale prioritization
            else:
                owner_multiplier = 1.9  # Heavy attrition scaling to disrupt lookahead cycles
                
            idx_score = (prod_value * owner_multiplier) / (required_force * dist_factor)
            
            if idx_score > best_idx_score:
                best_idx_score = idx_score
                best_node = target
                best_profile = (angle, turns, required_force)
                
        if best_node and best_profile:
            angle, turns, final_force = best_profile
            moves.append([int(src.id), float(angle), int(final_force)])
            allocated_garrisons[src.id] += final_force
            targeted_nodes.add(best_node.id)
            
    # --------------------------------------------------------------------------
    # STRATEGY 3: DEEP-BACKLINE FEEDER DRAIN (SUPPLY NETWORK LINK)
    # --------------------------------------------------------------------------
    # Secure hubs locked behind structural perimeters drain 35% of their growth
    # continuously to the closest frontline asset to maintain optimal momentum.
    if world.step > 30 and len(world.my_planets) > 2:
        for src in world.my_planets:
            if src.id in allocated_garrisons and allocated_garrisons[src.id] > 0: 
                continue
                
            # If no hostile asset is within range 35, it's a structural backline node
            is_backline = True
            for hp in world.hostile_planets:
                if get_distance(src.x, src.y, hp.x, hp.y) < 35.0:
                    is_backline = False
                    break
                    
            if is_backline and src.ships > 30:
                feed_stock = int(src.ships * 0.35)
                
                # Find the closest friendly frontline component
                closest_frontline = None
                min_front_d = float("inf")
                for candidate in world.my_planets:
                    if candidate.id == src.id: continue
                    d = get_distance(src.x, src.y, candidate.x, candidate.y)
                    if d < min_front_d:
                        min_front_d = d
                        closest_frontline = candidate
                        
                if closest_frontline:
                    solver = precise_interception_solver(src, closest_frontline, feed_stock, world.initial_planets, world.ang_vel)
                    if solver:
                        angle, _ = solver
                        moves.append([int(src.id), float(angle), int(feed_stock)])
                        allocated_garrisons[src.id] += feed_stock
                        
    return moves