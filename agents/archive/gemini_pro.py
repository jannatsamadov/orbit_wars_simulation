import math

# ==========================================
# PHYSICS & MECHANICS HELPER FUNCTIONS
# ==========================================

def get_fleet_speed(ships: int) -> float:
    """Calculates fleet speed based on the logarithmic scaling formula."""
    if ships <= 1: 
        return 1.0
    return min(6.0, 1.0 + (6.0 - 1.0) * (math.log(max(ships, 1)) / math.log(1000)) ** 1.5)

def check_sun_collision(x1: float, y1: float, x2: float, y2: float) -> bool:
    """
    Determines if a fleet traveling straight from (x1, y1) to (x2, y2) 
    intersects the Sun at (50.0, 50.0) with radius 10.0.
    Uses point-to-line segment distance constraint.
    """
    sun_x, sun_y = 50.0, 50.0
    sun_radius = 10.0
    
    # Vector from point 1 to point 2
    dx = x2 - x1
    dy = y2 - y1
    l2 = dx * dx + dy * dy
    
    if l2 == 0:
        # Source and destination are the exact same point
        return math.dist((x1, y1), (sun_x, sun_y)) < sun_radius
        
    # t is the projection of the Sun's center onto the line segment, clamped to [0, 1]
    t = max(0.0, min(1.0, ((sun_x - x1) * dx + (sun_y - y1) * dy) / l2))
    
    # Closest point on the segment to the Sun
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    
    # Distance from Sun to closest point
    dist_to_sun = math.dist((proj_x, proj_y), (sun_x, sun_y))
    return dist_to_sun < sun_radius

def predict_interception(source_x: float, source_y: float, target_x: float, target_y: float, 
                         angular_velocity: float, speed: float) -> float:
    """
    Predicts the future position of an orbiting planet based on angular velocity 
    and returns the required firing angle. Uses iterative approximation.
    Assumes rotation is around the Sun at (50.0, 50.0).
    """
    if angular_velocity == 0.0:
        return math.atan2(target_y - source_y, target_x - source_x)
        
    sun_x, sun_y = 50.0, 50.0
    radius = math.dist((sun_x, sun_y), (target_x, target_y))
    current_angle = math.atan2(target_y - sun_y, target_x - sun_x)
    
    # Iterative approximation for time of flight and angle convergence
    pred_x, pred_y = target_x, target_y
    for _ in range(4):
        dist = math.dist((source_x, source_y), (pred_x, pred_y))
        time_to_reach = dist / speed
        
        # Calculate new position of the target planet
        future_angle = current_angle + (angular_velocity * time_to_reach)
        pred_x = sun_x + radius * math.cos(future_angle)
        pred_y = sun_y + radius * math.sin(future_angle)
        
    return math.atan2(pred_y - source_y, pred_x - source_x)


# ==========================================
# MAIN AGENT FUNCTION
# ==========================================

def agent(obs) -> list:
    """
    Main agent function compatible with both dict-style and object-style observation spaces.
    Outputs a list of moves: [from_planet_id, angle_in_radians, num_ships]
    """
    # 1. Safe parsing of the environment
    player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
    angular_velocity = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else getattr(obs, "angular_velocity", 0.0)
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else getattr(obs, "planets", [])
    raw_fleets = obs.get("fleets", []) if isinstance(obs, dict) else getattr(obs, "fleets", [])
    
    # Categorize planets for easier logic parsing
    my_planets = []
    other_planets = []
    
    # Planet structure: [id, owner, x, y, radius, ships, production]
    for p in raw_planets:
        p_data = {
            "id": p[0], "owner": p[1], "x": p[2], "y": p[3], 
            "radius": p[4], "ships": p[5], "production": p[6]
        }
        if p_data["owner"] == player:
            my_planets.append(p_data)
        else:
            other_planets.append(p_data)
            
    moves = []
    
    # 2. Execution Loop (Replace with your custom strategic logic)
    if not other_planets:
        return moves
        
    for source in my_planets:
        # Example validation: Avoid sending fleets if ships are too low to matter
        if source["ships"] <= 5:
            continue
            
        ships_to_send = source["ships"]
        speed = get_fleet_speed(ships_to_send)
        
        # Basic targeting: iterate through potential targets
        for target in other_planets:
            
            # Predict intercept angle factoring in angular velocity
            angle = predict_interception(
                source["x"], source["y"], 
                target["x"], target["y"], 
                angular_velocity, speed
            )
            
            # Project where we are aiming to check for Sun collision.
            # Using an arbitrarily large distance (200 is > board diagonal) to trace the exact flight path.
            proj_x = source["x"] + math.cos(angle) * 200.0
            proj_y = source["y"] + math.sin(angle) * 200.0
            
            # Verify the intended path survives the Sun
            if not check_sun_collision(source["x"], source["y"], proj_x, proj_y):
                
                # Append formatted move
                moves.append([source["id"], float(angle), int(ships_to_send)])
                break 
                
    return moves